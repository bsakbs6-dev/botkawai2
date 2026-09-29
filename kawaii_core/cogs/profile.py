from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from kawaii_core.config import CONFIG
from kawaii_core.database.repository import StaffRepository
from kawaii_core.domain.hierarchy import HierarchyService
from kawaii_core.views.profile_view import StaffProfileView, build_profile_embed


class ProfileCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="profile",
        description="Просмотр и управление профилем сотрудника стаффа",
    )
    @app_commands.describe(member="Сотрудник, чей профиль вы хотите посмотреть (по умолчанию — ваш)")
    async def profile_command(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        invoker = interaction.user
        if not isinstance(invoker, discord.Member):
            await interaction.followup.send("❌ Команда доступна только на сервере.", ephemeral=True)
            return

        target = member if member is not None else invoker

        active_warns = await StaffRepository.get_active_warns(interaction.guild_id, target.id)  # type: ignore[arg-type]
        punishments = await StaffRepository.get_punishments_count(target.id)
        blacklist_rec = await StaffRepository.get_active_blacklist(interaction.guild_id, target.id)  # type: ignore[arg-type]
        profile = HierarchyService.resolve_profile(target, len(active_warns), punishments, blacklist_rec)

        embed, file = build_profile_embed(target, profile)
        view = StaffProfileView(invoker=invoker, target=target, target_profile=profile)

        msg = await interaction.followup.send(
            embed=embed,
            file=file,
            view=view,
            ephemeral=True,
        )
        view.message = msg


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProfileCog(bot))
