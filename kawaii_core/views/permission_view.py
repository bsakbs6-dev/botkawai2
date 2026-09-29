import discord

from kawaii_core.config import CONFIG, PERMISSIONS_BANNER_PATH
from kawaii_core.database.repository import SecurityRepository
from kawaii_core.domain.enums import GuardPermission
from kawaii_core.domain.models import UserGuardPermissions


def build_permissions_embed(target: discord.Member, perms: UserGuardPermissions) -> tuple[discord.Embed, discord.File]:
    embed = discord.Embed(
        title="Панель редактирования прав безопасности",
        color=CONFIG.primary_color,
    )
    file = discord.File(str(PERMISSIONS_BANNER_PATH), filename="permissions_banner.jpg")
    embed.set_image(url="attachment://permissions_banner.jpg")

    def status_emoji(val: bool) -> str:
        return "🟩 Разрешено" if val else "🟥 Запрещено (Защита активна)"

    embed.description = (
        f"Настройка исключений системы безопасности для {target.mention} (`{target.id}`)\n\n"
        f"**Управление ролями:**\n"
        f"• **{GuardPermission.MANAGE_ROLES_PKM.title_ru}**: {status_emoji(perms.manage_roles_pkm)}\n"
        f"• **{GuardPermission.EDIT_ROLES.title_ru}**: {status_emoji(perms.edit_roles)}\n"
        f"• **{GuardPermission.CREATE_ROLES.title_ru}**: {status_emoji(perms.create_roles)}\n"
        f"• **{GuardPermission.DELETE_ROLES.title_ru}**: {status_emoji(perms.delete_roles)}\n\n"
        f"**Модерация участников:**\n"
        f"• **{GuardPermission.BAN_MEMBERS.title_ru}**: {status_emoji(perms.ban_members)}\n"
        f"• **{GuardPermission.KICK_MEMBERS.title_ru}**: {status_emoji(perms.kick_members)}\n"
        f"• **{GuardPermission.TIMEOUT_MEMBERS.title_ru}**: {status_emoji(perms.timeout_members)}\n\n"
        f"**Каналы, сервер и боты:**\n"
        f"• **{GuardPermission.CREATE_CHANNELS.title_ru}**: {status_emoji(perms.create_channels)}\n"
        f"• **{GuardPermission.EDIT_CHANNELS.title_ru}**: {status_emoji(perms.edit_channels)}\n"
        f"• **{GuardPermission.DELETE_CHANNELS.title_ru}**: {status_emoji(perms.delete_channels)}\n"
        f"• **{GuardPermission.EDIT_SERVER.title_ru}**: {status_emoji(perms.edit_server)}\n"
        f"• **{GuardPermission.MANAGE_WEBHOOKS.title_ru}**: {status_emoji(perms.manage_webhooks)}\n"
        f"• **{GuardPermission.ADD_BOTS.title_ru}**: {status_emoji(perms.add_bots)}\n\n"
        f"*Нажмите на соответствующую кнопку ниже, чтобы переключить доступ.*"
    )
    embed.set_footer(text="Kawaii World • Security Guard System")
    return embed, file


class PermissionToggleView(discord.ui.View):
    def __init__(self, owner: discord.Member, target: discord.Member, perms: UserGuardPermissions):
        super().__init__(timeout=300)
        self.owner = owner
        self.target = target
        self.perms = perms
        self._build_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("❌ Панель доступна только владельцу сервера.", ephemeral=True)
            return False
        return True

    def _build_buttons(self) -> None:
        self.clear_items()

        # Group into 4 action rows
        grouped_permissions = [
            # Row 0: Roles
            (
                0,
                [
                    (GuardPermission.MANAGE_ROLES_PKM, "Роли (ПКМ)"),
                    (GuardPermission.EDIT_ROLES, "Правка ролей"),
                    (GuardPermission.CREATE_ROLES, "Создание ролей"),
                    (GuardPermission.DELETE_ROLES, "Удаление ролей"),
                ],
            ),
            # Row 1: Moderation
            (
                1,
                [
                    (GuardPermission.BAN_MEMBERS, "Бан участников"),
                    (GuardPermission.KICK_MEMBERS, "Кик участников"),
                    (GuardPermission.TIMEOUT_MEMBERS, "Мут/Таймаут"),
                ],
            ),
            # Row 2: Channels
            (
                2,
                [
                    (GuardPermission.CREATE_CHANNELS, "+ Каналы"),
                    (GuardPermission.EDIT_CHANNELS, "Правка каналов"),
                    (GuardPermission.DELETE_CHANNELS, "Удаление каналов"),
                ],
            ),
            # Row 3: Server, Webhooks & Bots
            (
                3,
                [
                    (GuardPermission.EDIT_SERVER, "Настройки сервера"),
                    (GuardPermission.MANAGE_WEBHOOKS, "Вебхуки"),
                    (GuardPermission.ADD_BOTS, "Добавление ботов"),
                ],
            ),
        ]

        for row_idx, perms in grouped_permissions:
            for perm, short_label in perms:
                is_enabled = getattr(self.perms, perm.value, False)
                btn = discord.ui.Button(
                    label=short_label,
                    style=discord.ButtonStyle.success if is_enabled else discord.ButtonStyle.danger,
                    custom_id=f"perm_{perm.value}",
                    row=row_idx,
                )
                btn.callback = self._create_toggle_callback(perm)
                self.add_item(btn)

    def _create_toggle_callback(self, perm: GuardPermission):
        async def callback(interaction: discord.Interaction) -> None:
            new_val = await SecurityRepository.toggle_permission(
                user_id=self.target.id,
                guild_id=self.target.guild.id,
                permission=perm,
            )
            setattr(self.perms, perm.value, new_val)
            self._build_buttons()
            embed, _ = build_permissions_embed(self.target, self.perms)
            await interaction.response.edit_message(embed=embed, view=self)

        return callback
