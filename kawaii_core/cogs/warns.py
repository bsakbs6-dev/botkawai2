from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands, tasks

from kawaii_core.config import CONFIG
from kawaii_core.database.repository import StaffRepository
from kawaii_core.domain.enums import PositionRank
from kawaii_core.domain.hierarchy import HierarchyService
from kawaii_core.services.warn_service import WarnService


class WarnsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.cleanup_warns_task.start()

    def cog_unload(self) -> None:
        self.cleanup_warns_task.cancel()

    @tasks.loop(minutes=10)
    async def cleanup_warns_task(self) -> None:
        for guild in self.bot.guilds:
            try:
                await WarnService.process_expired_warns(guild)
            except Exception:
                pass

    @cleanup_warns_task.before_loop
    async def before_cleanup(self) -> None:
        await self.bot.wait_until_ready()

    warn_group = app_commands.Group(name="warn", description="Управление выговорами сотрудников стаффа")

    @warn_group.command(name="add", description="Выдать выговор сотруднику")
    @app_commands.describe(member="Сотрудник стаффа", reason="Причина выговора")
    async def warn_add(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        invoker = interaction.user
        if not isinstance(invoker, discord.Member):
            return

        invoker_profile = HierarchyService.resolve_profile(invoker)
        if invoker_profile.rank < PositionRank.MASTER:
            await interaction.followup.send(
                "❌ Выдавать выговоры могут только Мастера и выше.",
                ephemeral=True,
            )
            return

        success, message = await WarnService.issue_warn(
            actor=invoker,
            target=member,
            reason=reason.strip(),
        )

        if not success:
            await interaction.followup.send(f"❌ {message}", ephemeral=True)
            return

        await interaction.followup.send(f"✅ {message}", ephemeral=True)

    @warn_group.command(name="remove", description="Снять выговор с сотрудника")
    @app_commands.describe(member="Сотрудник стаффа", warn_id="ID выговора (если не указан, снимется последний)")
    async def warn_remove(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        warn_id: Optional[int] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        invoker = interaction.user
        if not isinstance(invoker, discord.Member):
            return

        invoker_profile = HierarchyService.resolve_profile(invoker)
        if invoker_profile.rank < PositionRank.MASTER:
            await interaction.followup.send(
                "❌ Снимать выговоры могут только Мастера и выше.",
                ephemeral=True,
            )
            return

        success, message = await WarnService.remove_warn(
            actor=invoker,
            target=member,
            warn_id=warn_id,
        )

        if not success:
            await interaction.followup.send(f"❌ {message}", ephemeral=True)
            return

        await interaction.followup.send(f"✅ {message}", ephemeral=True)

    @warn_group.command(name="list", description="Список выговоров сотрудника")
    @app_commands.describe(member="Сотрудник (по умолчанию — вы)")
    async def warn_list(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        invoker = interaction.user
        if not isinstance(invoker, discord.Member):
            return

        target = member if member is not None else invoker

        invoker_roles = {r.id for r in invoker.roles}
        is_staff = (
            CONFIG.base_staff_role_id in invoker_roles
            or CONFIG.owner_role_id in invoker_roles
        )
        if not is_staff:
            await interaction.followup.send(
                "❌ Вы не состоите в стаффе для просмотра выговоров.",
                ephemeral=True,
            )
            return

        warns = await StaffRepository.get_all_warns(interaction.guild_id, target.id)  # type: ignore[arg-type]
        if not warns:
            await interaction.followup.send(
                f"ℹ️ У сотрудника {target.mention} нет выговоров в истории.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"История выговоров • {target.display_name}",
            color=CONFIG.primary_color,
        )

        lines = []
        for w in warns:
            status = "🔴 Активен" if w.is_active else "⚪ Снят/Истек"
            created_ts = int(w.created_at.timestamp())
            expires_ts = int(w.expires_at.timestamp())
            lines.append(
                f"**#{w.id}** [{status}]\n"
                f"• Выдал: <@{w.issuer_id}>\n"
                f"• Причина: {w.reason}\n"
                f"• Получен: <t:{created_ts}:d> (<t:{created_ts}:t>)\n"
                f"• Срок: <t:{expires_ts}:R>\n"
            )

        embed.description = "\n".join(lines)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # Alias /unwarn as top-level command
    @app_commands.command(name="unwarn", description="Снять выговор с сотрудника")
    @app_commands.describe(member="Сотрудник", warn_id="ID выговора (необязательно)")
    async def unwarn_shortcut(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        warn_id: Optional[int] = None,
    ) -> None:
        await self.warn_remove.callback(self, interaction, member, warn_id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WarnsCog(bot))
