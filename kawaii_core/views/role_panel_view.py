import logging
import re
from typing import List, Optional, Tuple
import unicodedata
import discord

from kawaii_core.config import CONFIG

logger = logging.getLogger("kawaii_bot.roles")


def extract_emoji_and_label(text: str) -> Tuple[Optional[str], str]:
    """
    Извлекает первый эмодзи (Discord custom emoji <:name:id> или Unicode) из строки, если он есть.
    Возвращает (emoji, cleaned_label).
    """
    cleaned = text.strip()
    if not cleaned:
        return None, ""

    # 1. Проверка на кастомный эмодзи Discord: <:name:id> или <a:name:id>
    custom_m = re.match(r"^(<a?:[a-zA-Z0-9_]+:\d+>)\s*(.*)$", cleaned)
    if custom_m:
        emoji_str, rest = custom_m.group(1), custom_m.group(2).strip()
        return emoji_str, rest if rest else emoji_str

    # 2. Проверка на стандартный Unicode-эмодзи в начале строки
    first_char = cleaned[0]
    cat = unicodedata.category(first_char)
    if ord(first_char) >= 0x1F000 or cat in ("So", "Sk") or 0x2600 <= ord(first_char) <= 0x27BF:
        idx = 1
        while idx < len(cleaned) and (
            ord(cleaned[idx]) in (0xFE0F, 0xFE0E, 0x200D)
            or 0x1F3FB <= ord(cleaned[idx]) <= 0x1F3FF
            or ord(cleaned[idx]) >= 0x1F000
        ):
            idx += 1
        emoji_str = cleaned[:idx]
        rest = cleaned[idx:].strip()
        return emoji_str, rest if rest else emoji_str

    return None, cleaned


class SubRoleToggleButton(discord.ui.Button):
    def __init__(
        self,
        role_id: int,
        label: str,
        emoji: Optional[str] = None,
        has_role: bool = False,
        category: str = "default",
    ):
        style = discord.ButtonStyle.success if has_role else discord.ButtonStyle.danger
        super().__init__(
            style=style,
            label=label,
            emoji=emoji,
            custom_id=f"role_sub_toggle:{role_id}:{category}",
        )
        self.role_id = role_id
        self.role_name = label
        self.category = category
        self.has_role = has_role

    async def callback(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        member = interaction.user

        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ Действие доступно только на сервере.", ephemeral=True)
            return

        role = guild.get_role(self.role_id)
        if role is None:
            try:
                role = await guild.fetch_role(self.role_id)
            except discord.NotFound:
                await interaction.response.send_message("❌ Роль не найдена на сервере.", ephemeral=True)
                return
            except discord.HTTPException as exc:
                logger.error("Failed to fetch role %d: %s", self.role_id, exc)
                await interaction.response.send_message("❌ Ошибка при получении роли.", ephemeral=True)
                return

        action_status = ""
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Снятие роли через интерактивное меню")
                self.style = discord.ButtonStyle.danger
                self.has_role = False
                action_status = f"🔄 Роль **{role.name}** снята."
            else:
                await member.add_roles(role, reason="Выдача роли через интерактивное меню")
                self.style = discord.ButtonStyle.success
                self.has_role = True
                action_status = f"✅ Вам выдана роль **{role.name}**."
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ У бота недостаточно прав для управления этой ролью. Убедитесь, что роль бота находится выше этой роли в списке ролей сервера.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as exc:
            logger.error("Error toggling role %d for user %d: %s", self.role_id, member.id, exc)
            await interaction.response.send_message("❌ Произошла ошибка при изменении ролей.", ephemeral=True)
            return

        if hasattr(self.view, "build_embed"):
            embed = self.view.build_embed(last_action=action_status)  # type: ignore[union-attr]
        else:
            embed = None

        try:
            if not interaction.response.is_done():
                if embed:
                    await interaction.response.edit_message(embed=embed, view=self.view)
                else:
                    await interaction.response.edit_message(view=self.view)
            else:
                if embed:
                    await interaction.edit_original_response(embed=embed, view=self.view)
                else:
                    await interaction.edit_original_response(view=self.view)
        except discord.HTTPException as exc:
            logger.debug("Failed to edit response in SubRoleToggleButton callback: %s", exc)


class DynamicCategoryRolesView(discord.ui.View):
    """
    Динамическое эфемерное представление для конкретной папки ролей.
    Цвета кнопок соответствуют наличию роли у пользователя:
    - 🟩 Зелёный (success) — роль есть
    - 🟥 Красный (danger) — роли нет
    """
    def __init__(self, member: discord.Member, category: dict, buttons: List[dict]):
        super().__init__(timeout=600)
        self.member_id = member.id
        self.category = category
        self.buttons_data = buttons
        user_role_ids = {r.id for r in member.roles}

        cat_id_str = str(category["id"])

        for item in buttons[:25]:
            role_id = item["role_id"]
            has_role = role_id in user_role_ids
            raw_label = item["label"]
            emoji = item.get("emoji")

            if not emoji:
                parsed_emoji, clean_label = extract_emoji_and_label(raw_label)
                if parsed_emoji:
                    emoji = parsed_emoji
                    label = clean_label
                else:
                    label = raw_label
            else:
                label = raw_label

            self.add_item(
                SubRoleToggleButton(
                    role_id=role_id,
                    label=label,
                    emoji=emoji,
                    has_role=has_role,
                    category=cat_id_str,
                )
            )

    def build_embed(self, last_action: Optional[str] = None) -> discord.Embed:
        cat_name = self.category.get("name", "Роли")
        cat_emoji = self.category.get("emoji") or "📁"
        embed = discord.Embed(
            title=f"{cat_emoji} Папка: {cat_name} • Kawaii World",
            description=(
                f"Выберите интересующие вас роли в категории **{cat_name}**!\n\n"
                "🟩 **Зелёная кнопка** — роль у вас есть (нажмите, чтобы снять).\n"
                "🟥 **Красная кнопка** — роли у вас нет (нажмите, чтобы получить).\n"
            ),
            color=CONFIG.primary_color,
        )
        if last_action:
            embed.add_field(name="Последнее действие", value=last_action, inline=False)
        embed.set_footer(text="Kawaii World • Меню выбора ролей")
        return embed


class GameRolesView(discord.ui.View):
    """Для обратной совместимости со статическими вызовами."""
    def __init__(self, member: discord.Member):
        super().__init__(timeout=600)
        self.member_id = member.id
        user_role_ids = {r.id for r in member.roles}
        for item in CONFIG.game_roles:
            has_role = item["id"] in user_role_ids
            self.add_item(
                SubRoleToggleButton(
                    role_id=item["id"],
                    label=item["name"],
                    emoji=item["emoji"],
                    has_role=has_role,
                    category="games",
                )
            )

    def build_embed(self, last_action: Optional[str] = None) -> discord.Embed:
        embed = discord.Embed(
            title="🎮 Папка: Игровые роли • Kawaii World",
            description=(
                "Выберите интересующие вас игры, чтобы получать уведомления и находить напарников!\n\n"
                "🟩 **Зелёная кнопка** — роль у вас есть (нажмите, чтобы снять).\n"
                "🟥 **Красная кнопка** — роли у вас нет (нажмите, чтобы получить).\n"
            ),
            color=CONFIG.primary_color,
        )
        if last_action:
            embed.add_field(name="Последнее действие", value=last_action, inline=False)
        embed.set_footer(text="Kawaii World • Меню выбора ролей")
        return embed


class NotificationRolesView(discord.ui.View):
    """Для обратной совместимости со статическими вызовами."""
    def __init__(self, member: discord.Member):
        super().__init__(timeout=600)
        self.member_id = member.id
        user_role_ids = {r.id for r in member.roles}
        for item in CONFIG.notification_roles:
            has_role = item["id"] in user_role_ids
            self.add_item(
                SubRoleToggleButton(
                    role_id=item["id"],
                    label=item["name"],
                    emoji=item["emoji"],
                    has_role=has_role,
                    category="notifications",
                )
            )

    def build_embed(self, last_action: Optional[str] = None) -> discord.Embed:
        embed = discord.Embed(
            title="🔔 Папка: Роли уведомлений • Kawaii World",
            description=(
                "Выберите категории уведомлений, которые вы хотите получать:\n\n"
                "🟩 **Зелёная кнопка** — уведомления включены (нажмите, чтобы выключить).\n"
                "🟥 **Красная кнопка** — уведомления выключены (нажмите, чтобы включить).\n"
            ),
            color=CONFIG.primary_color,
        )
        if last_action:
            embed.add_field(name="Последнее действие", value=last_action, inline=False)
        embed.set_footer(text="Kawaii World • Меню выбора ролей")
        return embed


class RoleMainPanelView(discord.ui.View):
    """
    Главная персистентная панель с синими папками категорий (ButtonStyle.primary).
    """
    def __init__(self, categories: Optional[List[dict]] = None):
        super().__init__(timeout=None)
        if categories:
            for idx, cat in enumerate(categories[:25]):
                cat_id = cat["id"]
                name = cat["name"]
                emoji = cat.get("emoji") or "📁"
                btn = discord.ui.Button(
                    label=name,
                    emoji=emoji,
                    style=discord.ButtonStyle.primary,
                    custom_id=f"role_folder:{cat_id}",
                    row=min(idx // 5, 4),
                )
                self.add_item(btn)
        else:
            # Дефолтные папки для глобальной регистрации в setup_hook бота
            self.add_item(
                discord.ui.Button(
                    label="Игры",
                    emoji="📁",
                    style=discord.ButtonStyle.primary,
                    custom_id="role_folder:games",
                    row=0,
                )
            )
            self.add_item(
                discord.ui.Button(
                    label="Уведомления",
                    emoji="📁",
                    style=discord.ButtonStyle.primary,
                    custom_id="role_folder:notifications",
                    row=0,
                )
            )


# Сохраняем обратную совместимость с предыдущим именем
RolePanelView = RoleMainPanelView
