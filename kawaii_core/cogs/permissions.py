import discord
from discord import app_commands
from discord.ext import commands

from kawaii_core.config import CONFIG
from kawaii_core.database.repository import SecurityRepository
from kawaii_core.views.permission_view import PermissionToggleView, build_permissions_embed


class PermissionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="permission",
        description="Настройка исключений системы защиты и прав безопасности пользователя",
    )
    @app_commands.describe(member="Пользователь, для которого настраиваются права")
    async def permission_command(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        invoker = interaction.user
        if not isinstance(invoker, discord.Member):
            return

        invoker_roles = {r.id for r in invoker.roles}
        is_owner = CONFIG.owner_role_id in invoker_roles

        if not is_owner:
            await interaction.followup.send(
                "❌ Данная команда доступна исключительно Владельцу сервера.",
                ephemeral=True,
            )
            return

        perms = await SecurityRepository.get_permissions(member.id, interaction.guild_id)  # type: ignore[arg-type]
        embed, file = build_permissions_embed(member, perms)
        view = PermissionToggleView(owner=invoker, target=member, perms=perms)

        await interaction.followup.send(
            embed=embed,
            file=file,
            view=view,
            ephemeral=True,
        )

    @app_commands.command(
        name="permissions",
        description="Настройка исключений системы защиты и прав безопасности пользователя",
    )
    @app_commands.describe(member="Пользователь, для которого настраиваются права")
    async def permissions_command(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        await self.permission_command(interaction, member)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PermissionsCog(bot))
