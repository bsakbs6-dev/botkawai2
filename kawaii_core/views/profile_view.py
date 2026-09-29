from typing import Optional, Union
import discord

from kawaii_core.config import CONFIG, PROFILE_BANNER_PATH
from kawaii_core.database.repository import StaffRepository
from kawaii_core.domain.enums import BranchType, PositionRank
from kawaii_core.domain.hierarchy import HierarchyService
from kawaii_core.domain.models import StaffProfile
from kawaii_core.services.blacklist_service import BlacklistService
from kawaii_core.services.staff_service import StaffService
from kawaii_core.services.warn_service import WarnService


def build_profile_embed(target: discord.Member, profile: StaffProfile) -> tuple[discord.Embed, discord.File]:
    embed = discord.Embed(
        title="Профиль сотрудника",
        color=CONFIG.primary_color,
    )

    file = discord.File(str(PROFILE_BANNER_PATH), filename="profile_banner.jpg")
    embed.set_image(url="attachment://profile_banner.jpg")

    embed.description = f"Информация о сотруднике {target.mention}\n"

    branch_display = profile.branch.value
    if profile.branch == BranchType.NONE:
        branch_display = "Не состоит"

    embed.add_field(name="🌿 Стоит на ветке", value=f"**{branch_display}**", inline=True)
    embed.add_field(name="💼 Должность", value=f"**{profile.position_title}**", inline=True)
    embed.add_field(
        name="⚠️ Выговоров",
        value=f"**{profile.active_warns}/{CONFIG.max_active_warns}**",
        inline=True,
    )
    embed.add_field(name="⚖️ Выданных наказаний", value=f"**{profile.total_punishments}**", inline=True)
    embed.add_field(name="🆔 ID Пользователя", value=f"`{target.id}`", inline=True)

    if profile.is_blacklisted and profile.blacklist_record:
        b = profile.blacklist_record
        created_ts = int(b.created_at.timestamp())
        embed.add_field(
            name="🚫 Статус ЧСКП",
            value=(
                f"**В ЧЕРНОМ СПИСКЕ**\n"
                f"• **Причина:** {b.reason}\n"
                f"• **Внес:** <@{b.issuer_id}> (`{b.issuer_rank_title}`)\n"
                f"• **Дата внесения:** <t:{created_ts}:d>"
            ),
            inline=False,
        )

    embed.set_footer(text="Kawaii World • Staff Management System")
    return embed, file


class WarnReasonModal(discord.ui.Modal, title="Выдача выговора"):
    reason_input = discord.ui.TextInput(
        label="Причина выговора",
        style=discord.TextStyle.paragraph,
        placeholder="Укажите подробную причину выдачи выговора...",
        required=True,
        max_length=500,
    )

    def __init__(self, target: discord.Member, parent_view: "StaffProfileView"):
        super().__init__()
        self.target = target
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        reason = self.reason_input.value.strip()
        success, message = await WarnService.issue_warn(
            actor=interaction.user,  # type: ignore[arg-type]
            target=self.target,
            reason=reason,
        )

        if not success:
            await interaction.followup.send(f"❌ {message}", ephemeral=True)
            return

        await self.parent_view.refresh_view()
        await interaction.followup.send(f"✅ {message}", ephemeral=True)


class BlacklistReasonModal(discord.ui.Modal, title="Внесение в ЧСКП"):
    reason_input = discord.ui.TextInput(
        label="Причина занесения в ЧСКП",
        style=discord.TextStyle.paragraph,
        placeholder="Укажите подробную причину внесения в Черный Список Стаффа...",
        required=True,
        max_length=500,
    )

    def __init__(self, target: discord.Member, parent_view: "StaffProfileView"):
        super().__init__()
        self.target = target
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        reason = self.reason_input.value.strip()
        success, message = await BlacklistService.add_to_blacklist(
            actor=interaction.user,  # type: ignore[arg-type]
            target=self.target,
            reason=reason,
        )

        if not success:
            await interaction.followup.send(f"❌ {message}", ephemeral=True)
            return

        await self.parent_view.refresh_view()
        await interaction.followup.send(f"✅ {message}", ephemeral=True)


class UnblacklistReasonModal(discord.ui.Modal, title="Вынесение из ЧСКП"):
    reason_input = discord.ui.TextInput(
        label="Причина вынесения из ЧСКП",
        style=discord.TextStyle.paragraph,
        placeholder="Укажите подробную причину вынесения из Черного Списка...",
        required=True,
        max_length=500,
    )

    def __init__(self, target: discord.Member, parent_view: "StaffProfileView"):
        super().__init__()
        self.target = target
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        reason = self.reason_input.value.strip()
        success, message = await BlacklistService.remove_from_blacklist(
            actor=interaction.user,  # type: ignore[arg-type]
            target=self.target,
            reason=reason,
        )

        if not success:
            await interaction.followup.send(f"❌ {message}", ephemeral=True)
            return

        await self.parent_view.refresh_view()
        await interaction.followup.send(f"✅ {message}", ephemeral=True)


class BranchSelect(discord.ui.Select):
    def __init__(self, target: discord.Member, parent_view: "StaffProfileView"):
        options = [
            discord.SelectOption(
                label="Модерация",
                value=BranchType.MODERATION.value,
                description="Назначить в ветку модерации (Модератор)",
                emoji="🛡️",
            ),
            discord.SelectOption(
                label="Саппорты",
                value=BranchType.SUPPORT.value,
                description="Назначить в ветку саппортов (Саппорт)",
                emoji="💬",
            ),
            discord.SelectOption(
                label="Эвентеры",
                value=BranchType.EVENTERS.value,
                description="Назначить в ветку эвентеров (Эвентер)",
                emoji="🎉",
            ),
        ]
        super().__init__(placeholder="Выберите ветку для назначения...", min_values=1, max_values=1, options=options)
        self.target = target
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        selected_branch = BranchType(self.values[0])
        success, message = await StaffService.appoint_member(
            actor=interaction.user,  # type: ignore[arg-type]
            target=self.target,
            branch=selected_branch,
        )
        if not success:
            await interaction.edit_original_response(content=f"❌ {message}", view=None)
            return

        await self.parent_view.refresh_view()
        await interaction.edit_original_response(content=f"✅ {message}", view=None)


class PromoteSelect(discord.ui.Select):
    def __init__(
        self,
        target: discord.Member,
        branch: BranchType,
        available_ranks: list[PositionRank],
        parent_view: "StaffProfileView",
    ):
        options = []
        for rank in available_ranks:
            label = rank.display_name
            if rank == PositionRank.RANK_1:
                branch_titles = {
                    BranchType.MODERATION: "Модератор",
                    BranchType.SUPPORT: "Саппорт",
                    BranchType.EVENTERS: "Эвентер",
                }
                label = f"Рядовой ({branch_titles.get(branch, 'Рядовой')})"

            options.append(
                discord.SelectOption(
                    label=label,
                    value=str(rank.value),
                    description=f"Повысить до должности {label}",
                    emoji="🔼",
                )
            )

        super().__init__(
            placeholder="Выберите должность для повышения...",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.target = target
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        selected_rank = PositionRank(int(self.values[0]))
        success, message = await StaffService.promote_member(
            actor=interaction.user,  # type: ignore[arg-type]
            target=self.target,
            target_rank=selected_rank,
        )
        if not success:
            await interaction.edit_original_response(content=f"❌ {message}", view=None)
            return

        await self.parent_view.refresh_view()
        await interaction.edit_original_response(content=f"✅ {message}", view=None)


class DemoteSelect(discord.ui.Select):
    def __init__(
        self,
        target: discord.Member,
        branch: BranchType,
        available_ranks: list[PositionRank],
        parent_view: "StaffProfileView",
    ):
        options = []
        for rank in available_ranks:
            label = rank.display_name
            if rank == PositionRank.RANK_1:
                branch_titles = {
                    BranchType.MODERATION: "Модератор",
                    BranchType.SUPPORT: "Саппорт",
                    BranchType.EVENTERS: "Эвентер",
                }
                label = f"Рядовой ({branch_titles.get(branch, 'Рядовой')})"

            options.append(
                discord.SelectOption(
                    label=label,
                    value=str(rank.value),
                    description=f"Понизить до должности {label}",
                    emoji="🔽",
                )
            )

        super().__init__(
            placeholder="Выберите должность для понижения...",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.target = target
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        selected_rank = PositionRank(int(self.values[0]))
        success, message = await StaffService.demote_member(
            actor=interaction.user,  # type: ignore[arg-type]
            target=self.target,
            target_rank=selected_rank,
        )
        if not success:
            await interaction.edit_original_response(content=f"❌ {message}", view=None)
            return

        await self.parent_view.refresh_view()
        await interaction.edit_original_response(content=f"✅ {message}", view=None)


class AdminAppointSelect(discord.ui.Select):
    def __init__(
        self,
        target: discord.Member,
        is_owner: bool,
        parent_view: "StaffProfileView",
    ):
        options = []
        if is_owner:
            options.append(
                discord.SelectOption(
                    label="Стафф Администратор",
                    value="staff_admin",
                    description="Назначить в высшее руководство проекта",
                    emoji="👑",
                )
            )

        options.append(
            discord.SelectOption(
                label="Администратор Модерации",
                value="admin_moderation",
                description="Главный администратор ветки Модерации",
                emoji="🛡️",
            )
        )
        options.append(
            discord.SelectOption(
                label="Администратор Саппортов",
                value="admin_support",
                description="Главный администратор ветки Саппортов",
                emoji="💬",
            )
        )
        options.append(
            discord.SelectOption(
                label="Администратор Эвентеров",
                value="admin_eventers",
                description="Главный администратор ветки Эвентеров",
                emoji="🎉",
            )
        )

        super().__init__(
            placeholder="Выберите руководящую должность...",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.target = target
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        selected_type = self.values[0]
        success, message = await StaffService.admin_appoint(
            actor=interaction.user,  # type: ignore[arg-type]
            target=self.target,
            appoint_type=selected_type,
        )
        if not success:
            await interaction.edit_original_response(content=f"❌ {message}", view=None)
            return

        await self.parent_view.refresh_view()
        await interaction.edit_original_response(content=f"✅ {message}", view=None)


class ConfirmDismissView(discord.ui.View):
    def __init__(self, actor: discord.Member, target: discord.Member, parent_view: "StaffProfileView"):
        super().__init__(timeout=60)
        self.actor = actor
        self.target = target
        self.parent_view = parent_view

    @discord.ui.button(label="Подтвердить снятие", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.actor.id:
            await interaction.response.send_message("❌ Это действие доступно только инициатору.", ephemeral=True)
            return

        await interaction.response.defer()
        success, message = await StaffService.dismiss_member(
            actor=self.actor,
            target=self.target,
            reason=f"Снятие сотрудником {self.actor}",
        )
        if not success:
            await interaction.edit_original_response(content=f"❌ {message}", view=None)
            return

        await self.parent_view.refresh_view()
        await interaction.edit_original_response(content=f"✅ {message}", view=None)

    @discord.ui.button(label="Отмена", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.actor.id:
            await interaction.response.send_message("❌ Это действие доступно только инициатору.", ephemeral=True)
            return
        await interaction.response.edit_message(content="Операция снятия отменена.", view=None)


class StaffProfileView(discord.ui.View):
    def __init__(
        self,
        invoker: discord.Member,
        target: discord.Member,
        target_profile: Optional[StaffProfile] = None,
    ):
        super().__init__(timeout=300)
        self.invoker = invoker
        self.target = target
        self.target_profile = target_profile or HierarchyService.resolve_profile(target)
        self.message: Optional[Union[discord.Message, discord.WebhookMessage]] = None
        self._build_components()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker.id:
            await interaction.response.send_message("❌ Это меню открыто другим пользователем.", ephemeral=True)
            return False
        return True

    def _build_components(self) -> None:
        self.clear_items()

        invoker_profile = HierarchyService.resolve_profile(self.invoker)
        target_profile = self.target_profile

        # 1. Повысить
        can_prom, _ = HierarchyService.can_promote(invoker_profile, target_profile)
        if can_prom:
            btn_promote = discord.ui.Button(
                label="Повысить",
                style=discord.ButtonStyle.success,
                emoji="🔼",
                custom_id="btn_promote",
            )
            btn_promote.callback = self._on_promote_clicked
            self.add_item(btn_promote)

        # 2. Понизить
        can_dem, _ = HierarchyService.can_demote(invoker_profile, target_profile)
        if can_dem:
            btn_demote = discord.ui.Button(
                label="Понизить",
                style=discord.ButtonStyle.secondary,
                emoji="🔽",
                custom_id="btn_demote",
            )
            btn_demote.callback = self._on_demote_clicked
            self.add_item(btn_demote)

        # 3. Назначить
        if not target_profile.is_staff or target_profile.branch == BranchType.NONE:
            can_app_any = invoker_profile.rank >= PositionRank.MASTER
            if can_app_any:
                btn_appoint = discord.ui.Button(
                    label="Назначить",
                    style=discord.ButtonStyle.primary,
                    emoji="➕",
                    custom_id="btn_appoint",
                )
                btn_appoint.callback = self._on_appoint_clicked
                self.add_item(btn_appoint)

        # 3.1. Админ-постановка (доступна Владельцу и Стафф Администратору)
        is_owner = invoker_profile.is_supreme or invoker_profile.rank == PositionRank.OWNER
        is_staff_admin = invoker_profile.rank == PositionRank.STAFF_ADMIN

        if (is_owner or is_staff_admin) and target_profile.rank != PositionRank.OWNER:
            if not (is_staff_admin and not is_owner and target_profile.rank == PositionRank.STAFF_ADMIN):
                btn_admin_appoint = discord.ui.Button(
                    label="Админ-постановка",
                    style=discord.ButtonStyle.primary,
                    emoji="👑",
                    custom_id="btn_admin_appoint",
                )
                btn_admin_appoint.callback = self._on_admin_appoint_clicked
                self.add_item(btn_admin_appoint)

        # 4. Снять
        can_dism, _ = HierarchyService.can_dismiss(invoker_profile, target_profile)
        if can_dism:
            btn_dismiss = discord.ui.Button(
                label="Снять",
                style=discord.ButtonStyle.danger,
                emoji="🚪",
                custom_id="btn_dismiss",
            )
            btn_dismiss.callback = self._on_dismiss_clicked
            self.add_item(btn_dismiss)

        # 5. Выдать выговор
        can_wrn, _ = HierarchyService.can_warn(invoker_profile, target_profile)
        if can_wrn:
            btn_warn = discord.ui.Button(
                label="Выдать выговор",
                style=discord.ButtonStyle.danger,
                emoji="⚠️",
                custom_id="btn_warn",
            )
            btn_warn.callback = self._on_warn_clicked
            self.add_item(btn_warn)

        # 6. Снять выговор
        if target_profile.active_warns > 0 and invoker_profile.rank >= PositionRank.MASTER:
            btn_unwarn = discord.ui.Button(
                label="Снять выговор",
                style=discord.ButtonStyle.secondary,
                emoji="🛡️",
                custom_id="btn_unwarn",
            )
            btn_unwarn.callback = self._on_unwarn_clicked
            self.add_item(btn_unwarn)

        # 7. Список выговоров (доступен всегда)
        btn_list_warns = discord.ui.Button(
            label="Список выговоров",
            style=discord.ButtonStyle.secondary,
            emoji="📜",
            custom_id="btn_list_warns",
        )
        btn_list_warns.callback = self._on_list_warns_clicked
        self.add_item(btn_list_warns)

        # 8. ЧСКП (Внести / Вынести)
        if target_profile.is_blacklisted:
            btn_unblacklist = discord.ui.Button(
                label="Вынести из ЧСКП",
                style=discord.ButtonStyle.secondary,
                emoji="🕊️",
                custom_id="btn_unblacklist",
            )
            btn_unblacklist.callback = self._on_unblacklist_clicked
            self.add_item(btn_unblacklist)
        else:
            can_bl = False
            if invoker_profile.is_supreme or invoker_profile.rank >= PositionRank.MASTER:
                if target_profile.rank != PositionRank.OWNER and self.invoker.id != self.target.id:
                    if target_profile.is_staff and target_profile.rank != PositionRank.NONE:
                        can_bl = invoker_profile.rank > target_profile.rank or invoker_profile.is_supreme
                        if (
                            invoker_profile.rank == PositionRank.STAFF_ADMIN
                            and target_profile.rank == PositionRank.STAFF_ADMIN
                            and not invoker_profile.is_supreme
                        ):
                            can_bl = False
                    else:
                        can_bl = True

            if can_bl:
                btn_blacklist = discord.ui.Button(
                    label="Внести в ЧСКП",
                    style=discord.ButtonStyle.danger,
                    emoji="🚫",
                    custom_id="btn_blacklist",
                )
                btn_blacklist.callback = self._on_blacklist_clicked
                self.add_item(btn_blacklist)

    async def refresh_view(self, interaction: Optional[discord.Interaction] = None) -> None:
        try:
            target_member = await self.target.guild.fetch_member(self.target.id)
            self.target = target_member
        except Exception:
            target_member = self.target.guild.get_member(self.target.id) or self.target
            self.target = target_member

        active_warns = await StaffRepository.get_active_warns(self.target.guild.id, self.target.id)
        punishments = await StaffRepository.get_punishments_count(self.target.id)
        bl_record = await StaffRepository.get_active_blacklist(self.target.guild.id, self.target.id)
        self.target_profile = HierarchyService.resolve_profile(self.target, len(active_warns), punishments, bl_record)

        self._build_components()
        embed, _ = build_profile_embed(self.target, self.target_profile)

        try:
            if self.message:
                await self.message.edit(embed=embed, view=self)
            elif interaction and interaction.message:
                await interaction.message.edit(embed=embed, view=self)
            elif interaction and not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=self)
        except Exception:
            pass

    async def _on_promote_clicked(self, interaction: discord.Interaction) -> None:
        invoker_profile = HierarchyService.resolve_profile(self.invoker)
        target_profile = self.target_profile

        allowed, err_msg = HierarchyService.can_promote(invoker_profile, target_profile)
        if not allowed:
            await interaction.response.send_message(f"❌ {err_msg}", ephemeral=True)
            return

        available = HierarchyService.get_available_promotions(invoker_profile, target_profile)
        if not available:
            await interaction.response.send_message(
                "❌ Нет доступных должностей для повышения сотрудника с вашими правами.",
                ephemeral=True,
            )
            return

        view = discord.ui.View(timeout=60)
        view.add_item(
            PromoteSelect(
                target=self.target,
                branch=target_profile.branch,
                available_ranks=available,
                parent_view=self,
            )
        )
        await interaction.response.send_message(
            f"Выберите новую должность для повышения сотрудника {self.target.mention}:",
            view=view,
            ephemeral=True,
        )

    async def _on_demote_clicked(self, interaction: discord.Interaction) -> None:
        invoker_profile = HierarchyService.resolve_profile(self.invoker)
        target_profile = self.target_profile

        allowed, err_msg = HierarchyService.can_demote(invoker_profile, target_profile)
        if not allowed:
            await interaction.response.send_message(f"❌ {err_msg}", ephemeral=True)
            return

        available = HierarchyService.get_available_demotions(invoker_profile, target_profile)
        if not available:
            await interaction.response.send_message(
                "❌ Нет доступных должностей для понижения сотрудника с вашими правами.",
                ephemeral=True,
            )
            return

        # Если сотрудник на должности Мастер (или доступна ровно 1 должность понижения) — сразу понижает до Рядового
        if target_profile.rank == PositionRank.MASTER or len(available) == 1:
            await interaction.response.defer(ephemeral=True)
            success, message = await StaffService.demote_member(
                actor=interaction.user,  # type: ignore[arg-type]
                target=self.target,
                target_rank=available[0],
            )
            if not success:
                await interaction.followup.send(f"❌ {message}", ephemeral=True)
                return

            await self.refresh_view(interaction)
            await interaction.followup.send(f"✅ {message}", ephemeral=True)
            return

        # Если сотрудник Куратор или выше — открывается выбор должностей для понижения
        view = discord.ui.View(timeout=60)
        view.add_item(
            DemoteSelect(
                target=self.target,
                branch=target_profile.branch,
                available_ranks=available,
                parent_view=self,
            )
        )
        await interaction.response.send_message(
            f"Выберите новую должность для понижения сотрудника {self.target.mention}:",
            view=view,
            ephemeral=True,
        )

    async def _on_appoint_clicked(self, interaction: discord.Interaction) -> None:
        invoker_profile = HierarchyService.resolve_profile(self.invoker)

        if invoker_profile.rank >= PositionRank.STAFF_ADMIN:
            view = discord.ui.View()
            view.add_item(BranchSelect(target=self.target, parent_view=self))
            await interaction.response.send_message(
                f"Выберите ветку для постановки на должность пользователя {self.target.mention}:",
                view=view,
                ephemeral=True,
            )
        else:
            await interaction.response.defer(ephemeral=True)
            success, message = await StaffService.appoint_member(
                actor=interaction.user,  # type: ignore[arg-type]
                target=self.target,
                branch=invoker_profile.branch,
            )
            if not success:
                await interaction.followup.send(f"❌ {message}", ephemeral=True)
                return

            await self.refresh_view(interaction)
            await interaction.followup.send(f"✅ {message}", ephemeral=True)

    async def _on_admin_appoint_clicked(self, interaction: discord.Interaction) -> None:
        invoker_profile = HierarchyService.resolve_profile(self.invoker)
        is_owner = invoker_profile.is_supreme or invoker_profile.rank == PositionRank.OWNER
        is_staff_admin = invoker_profile.rank == PositionRank.STAFF_ADMIN

        if not (is_owner or is_staff_admin):
            await interaction.response.send_message(
                "❌ Админ-постановка доступна только Владельцу и Стафф Администратору.",
                ephemeral=True,
            )
            return

        view = discord.ui.View(timeout=60)
        view.add_item(
            AdminAppointSelect(
                target=self.target,
                is_owner=is_owner,
                parent_view=self,
            )
        )
        await interaction.response.send_message(
            f"Выберите руководящую должность для назначения пользователя {self.target.mention}:",
            view=view,
            ephemeral=True,
        )

    async def _on_dismiss_clicked(self, interaction: discord.Interaction) -> None:
        confirm_view = ConfirmDismissView(
            actor=interaction.user,  # type: ignore[arg-type]
            target=self.target,
            parent_view=self,
        )
        await interaction.response.send_message(
            f"Вы уверены, что хотите снять сотрудника {self.target.mention} со стаффа?",
            view=confirm_view,
            ephemeral=True,
        )

    async def _on_warn_clicked(self, interaction: discord.Interaction) -> None:
        modal = WarnReasonModal(target=self.target, parent_view=self)
        await interaction.response.send_modal(modal)

    async def _on_unwarn_clicked(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        success, message = await WarnService.remove_warn(
            actor=interaction.user,  # type: ignore[arg-type]
            target=self.target,
        )
        if not success:
            await interaction.followup.send(f"❌ {message}", ephemeral=True)
            return

        await self.refresh_view(interaction)
        await interaction.followup.send(f"✅ {message}", ephemeral=True)

    async def _on_list_warns_clicked(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        warns = await StaffRepository.get_all_warns(self.target.guild.id, self.target.id)
        if not warns:
            await interaction.followup.send(
                f"ℹ️ У сотрудника {self.target.mention} нет выговоров в истории.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"История выговоров • {self.target.display_name}",
            color=CONFIG.primary_color,
        )

        lines = []
        for idx, w in enumerate(warns, 1):
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

    async def _on_blacklist_clicked(self, interaction: discord.Interaction) -> None:
        modal = BlacklistReasonModal(target=self.target, parent_view=self)
        await interaction.response.send_modal(modal)

    async def _on_unblacklist_clicked(self, interaction: discord.Interaction) -> None:
        invoker_profile = HierarchyService.resolve_profile(self.invoker)
        if not invoker_profile.is_supreme and invoker_profile.rank < PositionRank.MASTER:
            await interaction.response.send_message(
                "❌ Выносить из ЧСКП могут только Мастера и выше.",
                ephemeral=True,
            )
            return

        record = await StaffRepository.get_active_blacklist(self.target.guild.id, self.target.id)
        if not record:
            await interaction.response.send_message(
                "❌ Пользователь не находится в активном ЧСКП.",
                ephemeral=True,
            )
            return

        if invoker_profile.rank < record.issuer_rank_weight and not invoker_profile.is_supreme:
            await interaction.response.send_message(
                f"❌ ЧСКП был выдан должностью выше вашей ({record.issuer_rank_title}). "
                f"Обратитесь к <@{record.issuer_id}> или высшей администрации для вынесения.",
                ephemeral=True,
            )
            return

        modal = UnblacklistReasonModal(target=self.target, parent_view=self)
        await interaction.response.send_modal(modal)
