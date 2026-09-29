import asyncio
from datetime import datetime, timedelta, timezone
import html as html_lib
import json
import logging
import re
from typing import List, Optional, Tuple
import aiohttp
import discord

from kawaii_core.config import CONFIG

logger = logging.getLogger("kawaii_bot.events")

try:
    from zoneinfo import ZoneInfo
    MOSCOW_TZ = ZoneInfo("Europe/Moscow")
except Exception:
    MOSCOW_TZ = timezone(timedelta(hours=3), name="Europe/Moscow")


class EventService:
    @staticmethod
    def parse_event_datetime(date_time_str: str) -> Tuple[bool, Optional[int], str]:
        """
        Парсит строку даты и времени формата 'ДД.ММ.ГГГГ ЧЧ:ММ' в таймзоне Europe/Moscow.
        Возвращает (success, unix_timestamp, error_message).
        """
        cleaned = date_time_str.strip()
        try:
            dt = datetime.strptime(cleaned, "%d.%m.%Y %H:%M")
        except ValueError:
            return (
                False,
                None,
                "❌ Неверный формат даты и времени. Используйте формат `ДД.ММ.ГГГГ ЧЧ:ММ` (например: `29.09.2026 20:00`).",
            )

        # Привязываем московскую таймзону (UTC+3)
        dt = dt.replace(tzinfo=MOSCOW_TZ)
        unix_ts = int(dt.timestamp())
        now_ts = int(datetime.now(timezone.utc).timestamp())

        if unix_ts <= now_ts:
            return (
                False,
                None,
                "❌ Время проведения мероприятия должно быть в будущем.",
            )

        return True, unix_ts, ""

    @staticmethod
    async def fetch_kinopoisk_data(url: str) -> Tuple[bool, Optional[dict], str]:
        """
        Загружает и парсит данные о фильме/сериале по ссылке на Кинопоиск.
        Использует aiohttp с User-Agent Discordbot для извлечения OpenGraph и JSON-LD.
        """
        match = re.search(r"(?:film|series)/(\d+)", url)
        if not match:
            return (
                False,
                None,
                "❌ Не удалось распознать ссылку на фильм/сериал Кинопоиска. Ссылка должна быть вида: `https://www.kinopoisk.ru/film/301/`.",
            )

        item_id = match.group(1)
        clean_url = f"https://www.kinopoisk.ru/film/{item_id}/"

        user_agents = [
            "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)",
            "TelegramBot (like TwitterBot)",
            "Twitterbot/1.0",
            "VKShare; +http://vk.com/dev/Share",
            "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        ]

        html = ""
        last_error = ""

        for ua in user_agents:
            headers = {
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            }
            try:
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.get(clean_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        if resp.status == 200:
                            content = await resp.text(errors="ignore")
                            if len(content) > 5000:  # Проверка, что вернулась полноценная страница
                                html = content
                                break
                        elif resp.status == 429:
                            last_error = "HTTP 429 (Слишком много запросов)"
                            continue
                        else:
                            last_error = f"HTTP {resp.status}"
            except Exception as exc:
                last_error = str(exc)
                continue

        if not html:
            return False, None, f"❌ Не удалось получить данные о фильме с Кинопоиска ({last_error})."

        og_title = re.search(r'<meta property="og:title" content="([^"]+)"', html)
        og_desc = re.search(r'<meta property="og:description" content="([^"]+)"', html)
        og_img = re.search(r'<meta property="og:image" content="([^"]+)"', html)

        json_ld_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
        json_ld = {}
        if json_ld_match:
            try:
                json_ld = json.loads(json_ld_match.group(1))
            except Exception:
                pass

        raw_title = json_ld.get("name") or (og_title.group(1) if og_title else "Без названия")
        orig_title = json_ld.get("alternativeHeadline") or json_ld.get("alternateName") or ""

        year_match = re.search(r"\((\d{4})\)", og_title.group(1) if og_title else "")
        year = year_match.group(1) if year_match else ""

        full_title = raw_title
        if orig_title and orig_title != raw_title:
            full_title += f" ({orig_title})"
        if year and year not in full_title:
            full_title += f", {year}"

        desc = json_ld.get("description") or (og_desc.group(1) if og_desc else "Описание отсутствует.")
        desc = html_lib.unescape(desc)

        poster = og_img.group(1) if og_img else json_ld.get("image")
        rating_obj = json_ld.get("aggregateRating") or {}
        rating_val = rating_obj.get("ratingValue")
        rating_count = rating_obj.get("ratingCount")

        genres_raw = json_ld.get("genre") or []
        if isinstance(genres_raw, list):
            genres_str = ", ".join(g.capitalize() for g in genres_raw)
        else:
            genres_str = str(genres_raw)

        return True, {
            "title": full_title,
            "raw_title": raw_title,
            "orig_title": orig_title,
            "year": year,
            "description": desc,
            "poster_url": poster,
            "rating": round(float(rating_val), 1) if rating_val else None,
            "rating_count": rating_count,
            "genres": genres_str,
            "url": clean_url,
        }, ""

    @staticmethod
    def build_announcement_embed(
        title: str,
        description: str,
        event_timestamp: int,
        organizer: discord.Member,
        voice_channel: Optional[discord.VoiceChannel] = None,
        target_role: Optional[discord.Role] = None,
        event_id: Optional[int] = None,
        image_url: Optional[str] = None,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=f"🎉 Новое мероприятие: {title}",
            description=description,
            color=CONFIG.primary_color,
            timestamp=datetime.fromtimestamp(event_timestamp, tz=timezone.utc),
        )

        embed.add_field(
            name="📅 Дата и время",
            value=f"<t:{event_timestamp}:F>\n(<t:{event_timestamp}:R>)",
            inline=True,
        )

        if voice_channel:
            embed.add_field(
                name="🔊 Голосовой канал",
                value=voice_channel.mention,
                inline=True,
            )

        embed.add_field(
            name="👑 Организатор",
            value=organizer.mention,
            inline=True,
        )

        if target_role:
            embed.add_field(
                name="🔔 Оповещение",
                value=target_role.mention,
                inline=True,
            )

        if event_id is not None:
            embed.add_field(
                name="🆔 ID мероприятия",
                value=f"`#{event_id}`",
                inline=False,
            )

        if image_url and (image_url.startswith("http://") or image_url.startswith("https://")):
            embed.set_image(url=image_url)

        if organizer.display_avatar:
            embed.set_author(name=f"Организатор: {organizer.display_name}", icon_url=organizer.display_avatar.url)

        guild = organizer.guild
        icon_url = guild.icon.url if guild and guild.icon else None
        embed.set_footer(text="Kawaii World • Мероприятия", icon_url=icon_url)
        return embed

    @staticmethod
    def build_film_announcement_embed(
        film_data: dict,
        event_timestamp: int,
        organizer: discord.Member,
        voice_channel: Optional[discord.VoiceChannel] = None,
        target_role: Optional[discord.Role] = None,
        event_id: Optional[int] = None,
    ) -> discord.Embed:
        desc = film_data.get("description", "*Описание отсутствует.*")
        if len(desc) > 900:
            desc = desc[:900] + "..."

        embed = discord.Embed(
            title=f"🎬 Кинопоказ: {film_data['title']}",
            description=desc,
            color=CONFIG.primary_color,
            timestamp=datetime.fromtimestamp(event_timestamp, tz=timezone.utc),
        )

        embed.add_field(
            name="📅 Дата и время",
            value=f"<t:{event_timestamp}:F>\n(<t:{event_timestamp}:R>)",
            inline=True,
        )

        if voice_channel:
            embed.add_field(
                name="🔊 Голосовой канал",
                value=voice_channel.mention,
                inline=True,
            )

        embed.add_field(
            name="👑 Организатор",
            value=organizer.mention,
            inline=True,
        )

        if film_data.get("rating"):
            rc = f" ({film_data['rating_count']:,} оценок)".replace(",", " ") if film_data.get("rating_count") else ""
            embed.add_field(
                name="⭐ Рейтинг Кинопоиска",
                value=f"**{film_data['rating']} / 10**{rc}",
                inline=True,
            )

        if film_data.get("genres"):
            embed.add_field(
                name="🎭 Жанр",
                value=film_data["genres"],
                inline=True,
            )

        if target_role:
            embed.add_field(
                name="🔔 Оповещение",
                value=target_role.mention,
                inline=True,
            )

        if film_data.get("url"):
            embed.add_field(
                name="🔗 Кинопоиск",
                value=f"[Страница на Кинопоиске]({film_data['url']})",
                inline=False,
            )

        if event_id is not None:
            embed.add_field(
                name="🆔 ID события",
                value=f"`#{event_id}`",
                inline=False,
            )

        poster = film_data.get("poster_url")
        if poster and (poster.startswith("http://") or poster.startswith("https://")):
            embed.set_image(url=poster)

        if organizer.display_avatar:
            embed.set_author(name=f"Организатор: {organizer.display_name}", icon_url=organizer.display_avatar.url)

        guild = organizer.guild
        icon_url = guild.icon.url if guild and guild.icon else None
        embed.set_footer(text="Kawaii World • Кинотеатр", icon_url=icon_url)
        return embed

    @staticmethod
    def build_reminder_message(
        title: str,
        event_timestamp: int,
        organizer_id: int,
        remaining_time_str: str,
        voice_channel_id: Optional[int] = None,
        target_role_id: Optional[int] = None,
        event_id: Optional[int] = None,
    ) -> Tuple[str, discord.Embed]:
        role_mention = f"<@&{target_role_id}>" if target_role_id else ""
        content = role_mention if role_mention else ""

        desc_lines = [
            f"Через **{remaining_time_str}** начинается «**{title}**»!\n",
            f"📅 **Дата и время:** <t:{event_timestamp}:F> (<t:{event_timestamp}:R>)",
            f"👑 **Организатор:** <@{organizer_id}>",
        ]
        if voice_channel_id:
            desc_lines.append(f"🔊 **Голосовой канал:** <#{voice_channel_id}>")
        if target_role_id:
            desc_lines.append(f"🔔 **Роль:** <@&{target_role_id}>")

        embed = discord.Embed(
            title="🔔 Напоминание об ивенте!",
            description="\n".join(desc_lines),
            color=CONFIG.primary_color,
            timestamp=datetime.fromtimestamp(event_timestamp, tz=timezone.utc),
        )
        if event_id:
            embed.set_footer(text=f"Kawaii World • Мероприятие #{event_id}")
        return content, embed

    @staticmethod
    def build_start_notification(
        title: str,
        event_timestamp: int,
        organizer_id: int,
        voice_channel_id: Optional[int] = None,
        target_role_id: Optional[int] = None,
        event_id: Optional[int] = None,
    ) -> Tuple[Optional[str], discord.Embed]:
        """
        Формирует уведомление в момент наступления события (когда ивент начинается).
        Упоминает целевую роль, если она была задана.
        """
        role_mention = f"<@&{target_role_id}>" if target_role_id else None
        is_film = title.startswith("🎬")
        category_name = "Кинопоказ" if is_film else "Мероприятие"
        icon = "🎬" if is_film else "🎉"

        clean_title = title[2:].strip() if title.startswith("🎬") else title

        desc_lines = [
            f"{icon} **{category_name} «{clean_title}» начинается прямо сейчас!**\n",
            f"📅 **Время начала:** <t:{event_timestamp}:F>",
            f"👑 **Организатор:** <@{organizer_id}>",
        ]
        if voice_channel_id:
            desc_lines.append(f"🔊 **Голосовой канал:** <#{voice_channel_id}>")
        if target_role_id:
            desc_lines.append(f"🔔 **Оповещение:** <@&{target_role_id}>")

        embed = discord.Embed(
            title=f"{icon} {category_name} начался! • {clean_title}" if is_film else f"{icon} {category_name} началось! • {clean_title}",
            description="\n".join(desc_lines),
            color=CONFIG.primary_color,
            timestamp=datetime.fromtimestamp(event_timestamp, tz=timezone.utc),
        )
        footer_text = f"Kawaii World • {category_name} #{event_id}" if event_id else f"Kawaii World • {category_name}"
        embed.set_footer(text=footer_text)
        return role_mention, embed

    @staticmethod
    def build_events_list_embed(events: List[dict], guild: discord.Guild) -> discord.Embed:
        embed = discord.Embed(
            title="📋 Список предстоящих мероприятий • Kawaii World",
            color=CONFIG.primary_color,
            timestamp=datetime.now(timezone.utc),
        )

        if not events:
            embed.description = "*На данный момент нет запланированных активных мероприятий.*"
            return embed

        lines = []
        for idx, ev in enumerate(events, 1):
            ts = ev["event_timestamp"]
            title = ev["title"]
            ev_id = ev["id"]
            org_id = ev["organizer_id"]
            chan_id = ev["channel_id"]
            voice_id = ev.get("voice_channel_id")
            role_id = ev.get("target_role_id")

            voice_str = f" | 🔊 <#{voice_id}>" if voice_id else ""
            role_str = f" | Роль: <@&{role_id}>" if role_id else ""

            lines.append(
                f"**#{ev_id}. {title}**\n"
                f"• 📅 <t:{ts}:F> (<t:{ts}:R>)\n"
                f"• 👑 Организатор: <@{org_id}>\n"
                f"• 📢 Канал: <#{chan_id}>{voice_str}{role_str}\n"
            )

        embed.description = "\n".join(lines)
        icon_url = guild.icon.url if guild and guild.icon else None
        embed.set_footer(text=f"Всего мероприятий: {len(events)}", icon_url=icon_url)
        return embed

    @staticmethod
    def build_cancellation_embed(title: str, event_id: int, cancelled_by: discord.Member) -> discord.Embed:
        embed = discord.Embed(
            title=f"❌ Мероприятие отменено • #{event_id}",
            description=f"Мероприятие «**{title}**» (ID: `#{event_id}`) было отменено организатором / администрацией.",
            color=CONFIG.danger_color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Отменил", value=cancelled_by.mention, inline=True)
        return embed
