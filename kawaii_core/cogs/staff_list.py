from datetime import datetime, timezone
from typing import List, Optional
import discord
from discord import app_commands
from discord.ext import commands

from kawaii_core.config import BLACKLIST_BANNER_PATH, CONFIG, STAFF_BANNER_PATH
from kawaii_core.database.repository import StaffRepository
from kawaii_core.domain.enums import BranchType, PositionRank


def _format_members(members: List[discord.Member]) -> str:
    if not members:
        return "*Вакантно*"
    sorted_members = sorted(members, key=lambda m: m.display_name.lower())
    return ", ".join(m.mention for m in sorted_members)


async def build_blacklist_embed(guild: discord.Guild) -> tuple[discord.Embed, Optional[discord.File]]:
    records = await StaffRepository.get_all_active_blacklist(guild.id)
    embed = discord.Embed(
        title="🚫 Черный Список Команды Проекта (ЧСКП) • Kawaii World",
        color=CONFIG.danger_color,
        timestamp=datetime.now(timezone.utc),
    )

    file: Optional[discord.File] = None
    if BLACKLIST_BANNER_PATH.exists():
        file = discord.File(str(BLACKLIST_BANNER_PATH), filename="blacklist_banner.jpg")
        embed.set_image(url="attachment://blacklist_banner.jpg")

    if not records:
        embed.description = "*На данный момент в Черном Списке Команды Проекта нет записей.*"
    else:
        lines = []
        for idx, rec in enumerate(records, 1):
            created_ts = int(rec.created_at.timestamp())
            lines.append(
                f"**#{idx} • <@{rec.target_id}>** (`{rec.target_id}`)\n"
                f"• **Причина:** {rec.reason}\n"
                f"• **Внес:** <@{rec.issuer_id}> (`{rec.issuer_rank_title}`)\n"
                f"• **Дата внесения:** <t:{created_ts}:d> (<t:{created_ts}:t>)\n"
            )
        embed.description = "\n".join(lines)

    footer_icon = guild.icon.url if guild.icon else None
    embed.set_footer(
        text=f"Kawaii World • Всего в ЧСКП: {len(records)} чел.",
        icon_url=footer_icon,
    )
    return embed, file


class StaffListView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Посмотреть ЧСКП",
        style=discord.ButtonStyle.secondary,
        emoji="🚫",
        custom_id="btn_view_blacklist",
    )
    async def view_blacklist(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        invoker = interaction.user
        if not isinstance(invoker, discord.Member) or interaction.guild is None:
            await interaction.response.send_message("❌ Действие доступно только на сервере.", ephemeral=True)
            return

        invoker_roles = {r.id for r in invoker.roles}
        is_owner = CONFIG.owner_role_id in invoker_roles
        is_staff = CONFIG.base_staff_role_id in invoker_roles
        is_staff_admin = CONFIG.staff_admin_primary_role_id in invoker_roles

        if not (is_staff or is_owner or is_staff_admin):
            await interaction.response.send_message(
                "❌ Просмотр ЧСКП доступен только сотрудникам стаффа.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        embed, file = await build_blacklist_embed(interaction.guild)
        if file:
            await interaction.followup.send(embed=embed, file=file, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)


class StaffListCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="staff-list",
        description="Просмотр актуального состава команды проекта Kawaii World",
    )
    @app_commands.describe(hidden="Скрыть сообщение от других пользователей (по умолчанию: Нет)")
    async def staff_list_command(
        self,
        interaction: discord.Interaction,
        hidden: bool = False,
    ) -> None:
        invoker = interaction.user
        if not isinstance(invoker, discord.Member) or interaction.guild is None:
            await interaction.response.send_message("❌ Команда доступна только на сервере.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=hidden)
        guild = interaction.guild

        if not guild.chunked:
            try:
                await guild.chunk()
            except Exception:
                pass

        relevant_role_ids = (
            {CONFIG.base_staff_role_id, CONFIG.owner_role_id, CONFIG.staff_admin_primary_role_id, CONFIG.staff_admin_secondary_role_id}
            | CONFIG.all_branch_role_ids
            | CONFIG.all_qualifier_role_ids
            | CONFIG.all_rank_role_ids
        )

        all_staff_members: set[discord.Member] = set()
        for r_id in relevant_role_ids:
            role = guild.get_role(r_id)
            if role:
                all_staff_members.update(role.members)

        owners: list[discord.Member] = []
        staff_admins: list[discord.Member] = []

        moderation_staff: dict[PositionRank, list[discord.Member]] = {
            PositionRank.ADMIN: [],
            PositionRank.DEPUTY_ADMIN: [],
            PositionRank.CURATOR: [],
            PositionRank.MASTER: [],
            PositionRank.RANK_1: [],
        }

        support_staff: dict[PositionRank, list[discord.Member]] = {
            PositionRank.ADMIN: [],
            PositionRank.DEPUTY_ADMIN: [],
            PositionRank.CURATOR: [],
            PositionRank.MASTER: [],
            PositionRank.RANK_1: [],
        }

        eventers_staff: dict[PositionRank, list[discord.Member]] = {
            PositionRank.ADMIN: [],
            PositionRank.DEPUTY_ADMIN: [],
            PositionRank.CURATOR: [],
            PositionRank.MASTER: [],
            PositionRank.RANK_1: [],
        }

        for member in all_staff_members:
            role_ids = {r.id for r in member.roles}

            if CONFIG.owner_role_id in role_ids:
                if member not in owners:
                    owners.append(member)

            if CONFIG.staff_admin_primary_role_id in role_ids or CONFIG.staff_admin_secondary_role_id in role_ids:
                if member not in staff_admins:
                    staff_admins.append(member)

            # Moderation
            if CONFIG.moderation.branch_role_id in role_ids:
                has_qual = CONFIG.moderation.master_qualifier_role_id in role_ids
                if has_qual:
                    if CONFIG.rank_5_admin_id in role_ids:
                        moderation_staff[PositionRank.ADMIN].append(member)
                    elif CONFIG.rank_4_deputy_admin_id in role_ids:
                        moderation_staff[PositionRank.DEPUTY_ADMIN].append(member)
                    elif CONFIG.rank_3_curator_id in role_ids:
                        moderation_staff[PositionRank.CURATOR].append(member)
                    elif CONFIG.rank_2_master_id in role_ids:
                        moderation_staff[PositionRank.MASTER].append(member)
                elif CONFIG.moderation.rank_1_role_id in role_ids:
                    moderation_staff[PositionRank.RANK_1].append(member)

            # Support
            if CONFIG.support.branch_role_id in role_ids:
                has_qual = CONFIG.support.master_qualifier_role_id in role_ids
                if has_qual:
                    if CONFIG.rank_5_admin_id in role_ids:
                        support_staff[PositionRank.ADMIN].append(member)
                    elif CONFIG.rank_4_deputy_admin_id in role_ids:
                        support_staff[PositionRank.DEPUTY_ADMIN].append(member)
                    elif CONFIG.rank_3_curator_id in role_ids:
                        support_staff[PositionRank.CURATOR].append(member)
                    elif CONFIG.rank_2_master_id in role_ids:
                        support_staff[PositionRank.MASTER].append(member)
                elif CONFIG.support.rank_1_role_id in role_ids:
                    support_staff[PositionRank.RANK_1].append(member)

            # Eventers
            if CONFIG.eventers.branch_role_id in role_ids:
                has_qual = CONFIG.eventers.master_qualifier_role_id in role_ids
                if has_qual:
                    if CONFIG.rank_5_admin_id in role_ids:
                        eventers_staff[PositionRank.ADMIN].append(member)
                    elif CONFIG.rank_4_deputy_admin_id in role_ids:
                        eventers_staff[PositionRank.DEPUTY_ADMIN].append(member)
                    elif CONFIG.rank_3_curator_id in role_ids:
                        eventers_staff[PositionRank.CURATOR].append(member)
                    elif CONFIG.rank_2_master_id in role_ids:
                        eventers_staff[PositionRank.MASTER].append(member)
                elif CONFIG.eventers.rank_1_role_id in role_ids:
                    eventers_staff[PositionRank.RANK_1].append(member)

        embed = discord.Embed(
            title="🌸 Состав Команды Проекта • Kawaii World",
            color=CONFIG.primary_color,
            timestamp=datetime.now(timezone.utc),
        )

        file: Optional[discord.File] = None
        if STAFF_BANNER_PATH.exists():
            file = discord.File(str(STAFF_BANNER_PATH), filename="staff_banner.jpg")
            embed.set_image(url="attachment://staff_banner.jpg")

        description_lines = [
            "### 👑 Высшая Администрация",
            f"> 👑 **Владелец:** {_format_members(owners)}",
            f"> 🎖️ **Стафф Администрация:** {_format_members(staff_admins)}",
            "",
            "---",
            "### 🛡️ Ветка Модерации",
            f"> ⚔️ **Администратор:** {_format_members(moderation_staff[PositionRank.ADMIN])}",
            f"> 💠 **Зам.Администратора:** {_format_members(moderation_staff[PositionRank.DEPUTY_ADMIN])}",
            f"> 🔮 **Куратор:** {_format_members(moderation_staff[PositionRank.CURATOR])}",
            f"> 🎗️ **Мастер:** {_format_members(moderation_staff[PositionRank.MASTER])}",
            f"> 🛡️ **Модераторы:** {_format_members(moderation_staff[PositionRank.RANK_1])}",
            "",
            "---",
            "### 💬 Ветка Саппортов",
            f"> ⚔️ **Администратор:** {_format_members(support_staff[PositionRank.ADMIN])}",
            f"> 💠 **Зам.Администратора:** {_format_members(support_staff[PositionRank.DEPUTY_ADMIN])}",
            f"> 🔮 **Куратор:** {_format_members(support_staff[PositionRank.CURATOR])}",
            f"> 🎗️ **Мастер:** {_format_members(support_staff[PositionRank.MASTER])}",
            f"> 💬 **Саппорты:** {_format_members(support_staff[PositionRank.RANK_1])}",
            "",
            "---",
            "### 🎉 Ветка Эвентеров",
            f"> ⚔️ **Администратор:** {_format_members(eventers_staff[PositionRank.ADMIN])}",
            f"> 💠 **Зам.Администратора:** {_format_members(eventers_staff[PositionRank.DEPUTY_ADMIN])}",
            f"> 🔮 **Куратор:** {_format_members(eventers_staff[PositionRank.CURATOR])}",
            f"> 🎗️ **Мастер:** {_format_members(eventers_staff[PositionRank.MASTER])}",
            f"> 🎉 **Эвентеры:** {_format_members(eventers_staff[PositionRank.RANK_1])}",
        ]

        embed.description = "\n".join(description_lines)

        footer_icon = guild.icon.url if guild.icon else None
        embed.set_footer(
            text=f"Kawaii World • Всего сотрудников в штате: {len(all_staff_members)}",
            icon_url=footer_icon,
        )

        view = StaffListView()
        if file:
            await interaction.followup.send(embed=embed, file=file, view=view, ephemeral=hidden)
        else:
            await interaction.followup.send(embed=embed, view=view, ephemeral=hidden)

    @app_commands.command(
        name="blacklist-staff",
        description="Просмотр Черного Списка Команды Проекта (ЧСКП)",
    )
    @app_commands.describe(hidden="Скрыть сообщение от других пользователей (по умолчанию: Нет)")
    async def blacklist_staff_command(
        self,
        interaction: discord.Interaction,
        hidden: bool = False,
    ) -> None:
        invoker = interaction.user
        if not isinstance(invoker, discord.Member) or interaction.guild is None:
            await interaction.response.send_message("❌ Команда доступна только на сервере.", ephemeral=True)
            return

        invoker_roles = {r.id for r in invoker.roles}
        is_owner = CONFIG.owner_role_id in invoker_roles
        is_staff = CONFIG.base_staff_role_id in invoker_roles
        is_staff_admin = CONFIG.staff_admin_primary_role_id in invoker_roles

        if not (is_staff or is_owner or is_staff_admin):
            await interaction.response.send_message(
                "❌ Данная команда доступна только сотрудникам стаффа.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=hidden)
        embed, file = await build_blacklist_embed(interaction.guild)
        if file:
            await interaction.followup.send(embed=embed, file=file, ephemeral=hidden)
        else:
            await interaction.followup.send(embed=embed, ephemeral=hidden)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StaffListCog(bot))
