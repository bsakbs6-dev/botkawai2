import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands, tasks

from kawaii_core.config import CONFIG
from kawaii_core.database.repository import EventRepository
from kawaii_core.domain.enums import BranchType, PositionRank
from kawaii_core.domain.hierarchy import HierarchyService
from kawaii_core.services.event_service import EventService

logger = logging.getLogger("kawaii_bot.events")


def can_manage_events(member: discord.Member) -> bool:
    """
    Проверяет права доступа к созданию мероприятий в соответствии с иерархией бота:
    1. Владелец / Стафф-Администратор (is_supreme или rank >= STAFF_ADMIN)
    2. Ветка EVENTERS и ранг >= RANK_1 (Эвентер, Мастер ветки, Куратор, Зам.Администратора, Администратор)
    3. Наличие роли ветки CONFIG.eventers.branch_role_id ('Отвечает | Eventers')
    """
    profile = HierarchyService.resolve_profile(member)
    if profile.is_supreme or profile.rank >= PositionRank.STAFF_ADMIN:
        return True
    if profile.branch == BranchType.EVENTERS and profile.rank >= PositionRank.RANK_1:
        return True
    if CONFIG.eventers.branch_role_id in profile.raw_role_ids:
        return True
    return False


def can_cancel_event(member: discord.Member, organizer_id: int) -> bool:
    """
    Отменять мероприятие может только его автор (организатор) или руководство (Куратор+).
    """
    if member.id == organizer_id:
        return True
    profile = HierarchyService.resolve_profile(member)
    if profile.is_supreme or profile.rank >= PositionRank.STAFF_ADMIN or profile.rank >= PositionRank.CURATOR:
        return True
    return False


class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.reminders_loop.start()

    def cog_unload(self) -> None:
        self.reminders_loop.cancel()

    event_group = app_commands.Group(
        name="event",
        description="Управление мероприятиями и напоминаниями сервера",
    )

    film_group = app_commands.Group(
        name="film",
        description="Управление совместными кинопоказами и фильмами",
    )

    @event_group.command(
        name="create",
        description="Создать и анонсировать новое мероприятие",
    )
    @app_commands.describe(
        title="Название мероприятия (до 100 символов)",
        description="Подробное описание мероприятия и правила участия",
        date_time="Дата и время в формате ДД.ММ.ГГГГ ЧЧ:ММ (МСК, например: 29.09.2026 20:00)",
        voice_channel="Голосовой канал, в котором будет проходить ивент",
        image_url="Опциональная ссылка на баннер мероприятия (URL картинки)",
        channel="Канал для публикации анонса (по умолчанию канал мероприятий)",
        role_to_mention="Роль для упоминания (например, Ивенты)",
    )
    async def event_create(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        date_time: str,
        voice_channel: Optional[discord.VoiceChannel] = None,
        image_url: Optional[str] = None,
        channel: Optional[discord.TextChannel] = None,
        role_to_mention: Optional[discord.Role] = None,
    ) -> None:
        member = interaction.user
        guild = interaction.guild
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ Команда доступна только на сервере.", ephemeral=True)
            return

        # 1. Защита от таймаута Discord (defer предотвращает 10062 Unknown interaction)
        await interaction.response.defer(ephemeral=True)

        # 2. Проверка прав (Eventer+)
        if not can_manage_events(member):
            await interaction.followup.send(
                "❌ Создание мероприятий доступно только должности Eventer и выше.",
                ephemeral=True,
            )
            return

        # 3. Валидация заголовка
        title_clean = title.strip()
        if len(title_clean) > 100:
            await interaction.followup.send(
                "❌ Название мероприятия не должно превышать 100 символов.",
                ephemeral=True,
            )
            return

        # 4. Валидация роли для упоминания (Anti-MassPing)
        if role_to_mention and role_to_mention.is_default():
            await interaction.followup.send(
                "❌ Запрещено использовать @everyone или @here в качестве роли для упоминания.",
                ephemeral=True,
            )
            return

        # 5. Валидация даты и времени (МСК)
        valid, unix_ts, err_msg = EventService.parse_event_datetime(date_time)
        if not valid or unix_ts is None:
            await interaction.followup.send(err_msg, ephemeral=True)
            return

        # 6. Определение канала публикации
        target_channel = channel or guild.get_channel(CONFIG.default_events_channel_id) or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.followup.send(
                "❌ Не удалось определить текстовый канал для публикации мероприятия.",
                ephemeral=True,
            )
            return

        # 7. Сохранение мероприятия в БД
        event_id = await EventRepository.create_event(
            guild_id=guild.id,
            title=title_clean,
            description=description.strip(),
            event_timestamp=unix_ts,
            image_url=image_url.strip() if image_url else None,
            organizer_id=member.id,
            channel_id=target_channel.id,
            target_role_id=role_to_mention.id if role_to_mention else None,
            voice_channel_id=voice_channel.id if voice_channel else None,
            reminded_start=0,
        )

        # 8. Публикация карточки анонса в целевой канал (без мгновенного пинга роли)
        embed = EventService.build_announcement_embed(
            title=title_clean,
            description=description.strip(),
            event_timestamp=unix_ts,
            organizer=member,
            voice_channel=voice_channel,
            target_role=role_to_mention,
            event_id=event_id,
            image_url=image_url.strip() if image_url else None,
        )

        try:
            await target_channel.send(
                content=None,
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.Forbidden:
            await interaction.followup.send(
                f"⚠️ Мероприятие сохранено в базе (#{event_id}), но у бота нет прав для отправки сообщений в канал {target_channel.mention}.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as exc:
            logger.error("Failed to post event announcement: %s", exc)
            await interaction.followup.send(
                f"⚠️ Ошибка при отправке анонса в канал: {exc}",
                ephemeral=True,
            )
            return

        # 9. Подтверждение инициатору
        voice_info = f"\n🔊 Голосовой канал: {voice_channel.mention}" if voice_channel else ""
        role_info = f"\n🔔 Оповещение участников ({role_to_mention.mention}) будет отправлено в момент начала мероприятия." if role_to_mention else ""
        await interaction.followup.send(
            f"✅ Мероприятие «**{title_clean}**» (ID: `#{event_id}`) успешно создано и опубликовано в канале {target_channel.mention}!\n"
            f"📅 Начало: <t:{unix_ts}:F> (<t:{unix_ts}:R>){voice_info}{role_info}",
            ephemeral=True,
        )

    @film_group.command(
        name="create",
        description="Запланировать кинопоказ по ссылке на фильм с Кинопоиска",
    )
    @app_commands.describe(
        kinopoisk_url="Ссылка на страницу фильма на Кинопоиске (например: https://www.kinopoisk.ru/film/301/)",
        date_time="Дата и время кинопоказа (ДД.ММ.ГГГГ ЧЧ:ММ, например: 29.09.2026 21:00)",
        voice_channel="Голосовой канал, в котором будет проходить совместный просмотр",
        channel="Канал для публикации анонса (по умолчанию канал мероприятий)",
        role_to_mention="Роль для упоминания (например, Ивенты)",
    )
    async def film_create(
        self,
        interaction: discord.Interaction,
        kinopoisk_url: str,
        date_time: str,
        voice_channel: Optional[discord.VoiceChannel] = None,
        channel: Optional[discord.TextChannel] = None,
        role_to_mention: Optional[discord.Role] = None,
    ) -> None:
        member = interaction.user
        guild = interaction.guild
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ Команда доступна только на сервере.", ephemeral=True)
            return

        # 1. Защита от таймаута (парсинг сайта может занять 1-2 секунды)
        await interaction.response.defer(ephemeral=True)

        # 2. Проверка прав (Eventer+)
        if not can_manage_events(member):
            await interaction.followup.send(
                "❌ Создание кинопоказов доступно только должности Eventer и выше.",
                ephemeral=True,
            )
            return

        # 3. Валидация роли для упоминания (Anti-MassPing)
        if role_to_mention and role_to_mention.is_default():
            await interaction.followup.send(
                "❌ Запрещено использовать @everyone или @here в качестве роли для упоминания.",
                ephemeral=True,
            )
            return

        # 4. Валидация даты и времени
        valid, unix_ts, err_msg = EventService.parse_event_datetime(date_time)
        if not valid or unix_ts is None:
            await interaction.followup.send(err_msg, ephemeral=True)
            return

        # 5. Парсинг данных с Кинопоиска
        success, film_data, kp_err = await EventService.fetch_kinopoisk_data(kinopoisk_url)
        if not success or film_data is None:
            await interaction.followup.send(kp_err, ephemeral=True)
            return

        # 6. Определение канала публикации
        target_channel = channel or guild.get_channel(CONFIG.default_events_channel_id) or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.followup.send(
                "❌ Не удалось определить текстовый канал для публикации анонса.",
                ephemeral=True,
            )
            return

        # 7. Сохранение в БД
        event_title = f"🎬 {film_data['title']}"
        event_id = await EventRepository.create_event(
            guild_id=guild.id,
            title=event_title,
            description=film_data.get("description", ""),
            event_timestamp=unix_ts,
            image_url=film_data.get("poster_url"),
            organizer_id=member.id,
            channel_id=target_channel.id,
            target_role_id=role_to_mention.id if role_to_mention else None,
            voice_channel_id=voice_channel.id if voice_channel else None,
            reminded_start=0,
        )

        # 8. Формирование и публикация карточки кинопоказа (без мгновенного пинга роли)
        embed = EventService.build_film_announcement_embed(
            film_data=film_data,
            event_timestamp=unix_ts,
            organizer=member,
            voice_channel=voice_channel,
            target_role=role_to_mention,
            event_id=event_id,
        )

        try:
            await target_channel.send(
                content=None,
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.Forbidden:
            await interaction.followup.send(
                f"⚠️ Кинопоказ сохранен в базе (#{event_id}), но у бота нет прав для отправки сообщений в канал {target_channel.mention}.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as exc:
            logger.error("Failed to post film announcement: %s", exc)
            await interaction.followup.send(
                f"⚠️ Ошибка при отправке карточки фильма в канал: {exc}",
                ephemeral=True,
            )
            return

        # 9. Ответ пользователю
        voice_info = f"\n🔊 Голосовой канал: {voice_channel.mention}" if voice_channel else ""
        role_info = f"\n🔔 Оповещение участников ({role_to_mention.mention}) будет отправлено в момент начала кинопоказа." if role_to_mention else ""
        await interaction.followup.send(
            f"✅ Кинопоказ «**{film_data['title']}**» (ID: `#{event_id}`) успешно запланирован и опубликован в {target_channel.mention}!\n"
            f"📅 Начало: <t:{unix_ts}:F> (<t:{unix_ts}:R>){voice_info}{role_info}",
            ephemeral=True,
        )

    @event_group.command(
        name="list",
        description="Посмотреть список активных запланированных мероприятий",
    )
    async def event_list(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("❌ Команда доступна только на сервере.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        events = await EventRepository.get_active_events(guild.id)
        embed = EventService.build_events_list_embed(events, guild)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @event_group.command(
        name="cancel",
        description="Отменить запланированное мероприятие или кинопоказ",
    )
    @app_commands.describe(event_id="Идентификатор мероприятия (число)")
    async def event_cancel(self, interaction: discord.Interaction, event_id: int) -> None:
        member = interaction.user
        guild = interaction.guild
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ Команда доступна только на сервере.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        event = await EventRepository.get_event(event_id)
        if not event or event.get("guild_id") != guild.id:
            await interaction.followup.send(f"❌ Мероприятие с ID `#{event_id}` не найдено.", ephemeral=True)
            return

        if event.get("is_cancelled"):
            await interaction.followup.send(f"ℹ️ Мероприятие `#{event_id}` уже было отменено ранее.", ephemeral=True)
            return

        # Проверка прав (автор или Куратор/Админ)
        if not can_cancel_event(member, event["organizer_id"]):
            await interaction.followup.send(
                "❌ Отменить мероприятие может только его организатор или руководство (Куратор и выше).",
                ephemeral=True,
            )
            return

        success = await EventRepository.cancel_event(event_id)
        if not success:
            await interaction.followup.send("❌ Не удалось отменить мероприятие.", ephemeral=True)
            return

        # Уведомление в канал мероприятия
        channel = guild.get_channel(event["channel_id"])
        if isinstance(channel, discord.TextChannel):
            try:
                cancel_embed = EventService.build_cancellation_embed(event["title"], event_id, member)
                await channel.send(embed=cancel_embed)
            except Exception as exc:
                logger.warning("Failed to send cancellation message to channel %d: %s", event["channel_id"], exc)

        await interaction.followup.send(
            f"✅ Мероприятие `#{event_id}` («**{event['title']}**») успешно отменено.",
            ephemeral=True,
        )

    @tasks.loop(seconds=30)
    async def reminders_loop(self) -> None:
        """
        Фоновый цикл проверки наступления мероприятий и отправки уведомлений.
        Оповещение с упоминанием роли отправляется строго в момент наступления события (время начала).
        """
        try:
            upcoming = await EventRepository.get_upcoming_events()
            if not upcoming:
                return

            now_ts = int(discord.utils.utcnow().timestamp())

            for event in upcoming:
                event_ts = event["event_timestamp"]
                time_diff = event_ts - now_ts

                # Если время мероприятия еще не наступило (в будущем)
                if time_diff > 0:
                    continue

                # Если уже было отправлено оповещение о начале
                if event.get("reminded_start") == 1:
                    continue

                # Помечаем в БД, что оповещение обработано
                await EventRepository.mark_reminded(event["id"], "start")

                # Если мероприятие началось более 2 часов назад (например, бот был оффлайн) — не спамим
                if now_ts - event_ts > 7200:
                    logger.info("Event #%d was scheduled >2h ago. Skipped notification without spam.", event["id"])
                    continue

                guild = self.bot.get_guild(event["guild_id"])
                if not guild:
                    continue

                channel = guild.get_channel(event["channel_id"])
                if not isinstance(channel, discord.TextChannel):
                    continue

                await self._dispatch_start_notification(channel, event)

        except Exception as exc:
            logger.error("Error in reminders_loop: %s", exc, exc_info=True)

    async def _dispatch_start_notification(self, channel: discord.TextChannel, event: dict) -> None:
        content, embed = EventService.build_start_notification(
            title=event["title"],
            event_timestamp=event["event_timestamp"],
            organizer_id=event["organizer_id"],
            voice_channel_id=event.get("voice_channel_id"),
            target_role_id=event.get("target_role_id"),
            event_id=event["id"],
        )
        try:
            await channel.send(
                content=content,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(roles=True, everyone=False, users=False),
            )
            logger.info("Sent start notification for event #%d to channel %d", event["id"], channel.id)
        except discord.Forbidden:
            logger.warning("Forbidden: Cannot send start notification for event #%d in channel %d", event["id"], channel.id)
        except Exception as exc:
            logger.error("Error sending start notification for event #%d: %s", event["id"], exc)

    @reminders_loop.before_loop
    async def before_reminders_loop(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EventsCog(bot))
