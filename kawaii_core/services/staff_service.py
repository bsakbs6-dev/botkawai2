from typing import Optional, Set
import discord

from kawaii_core.config import CONFIG, BranchRoleConfig
from kawaii_core.database.repository import StaffRepository
from kawaii_core.domain.enums import BranchType, PositionRank
from kawaii_core.domain.hierarchy import HierarchyService
from kawaii_core.services.log_service import AuditLogger


class StaffService:
    @staticmethod
    def _get_branch_config(branch: BranchType) -> Optional[BranchRoleConfig]:
        if branch == BranchType.MODERATION:
            return CONFIG.moderation
        elif branch == BranchType.SUPPORT:
            return CONFIG.support
        elif branch == BranchType.EVENTERS:
            return CONFIG.eventers
        return None

    @classmethod
    async def appoint_member(
        cls,
        actor: discord.Member,
        target: discord.Member,
        branch: BranchType,
    ) -> tuple[bool, str]:
        actor_profile = HierarchyService.resolve_profile(actor)
        target_profile = HierarchyService.resolve_profile(target)

        allowed, err_msg = HierarchyService.can_appoint(actor_profile, target_profile, branch)
        if not allowed:
            return False, err_msg

        if await StaffRepository.is_user_blacklisted(target.guild.id, target.id):
            return False, "Пользователь находится в Черном Списке Команды Проекта (ЧСКП) и не может быть назначен на должность."

        branch_cfg = cls._get_branch_config(branch)
        if branch_cfg is None:
            return False, "Не удалось определить конфигурацию ветки."

        guild = target.guild

        # Снимаем любые роли других веток, квалификаторов и должностей
        roles_to_remove: Set[discord.Role] = set()
        for r_id in (
            CONFIG.all_rank_role_ids
            | CONFIG.all_qualifier_role_ids
            | (CONFIG.all_branch_role_ids - {branch_cfg.branch_role_id})
        ):
            role = guild.get_role(r_id)
            if role and role in target.roles:
                roles_to_remove.add(role)

        # Выдаем базовую роль стаффа, роль выбранной ветки и роль 1-го ранга
        base_role = guild.get_role(CONFIG.base_staff_role_id)
        b_role = guild.get_role(branch_cfg.branch_role_id)
        r1_role = guild.get_role(branch_cfg.rank_1_role_id)

        roles_to_add: Set[discord.Role] = {
            r for r in (base_role, b_role, r1_role) if r is not None and r not in target.roles
        }

        roles_to_remove_filtered = [
            r for r in roles_to_remove if r and (guild.me is None or r < guild.me.top_role)
        ]
        roles_to_add_filtered = [
            r for r in roles_to_add if r and (guild.me is None or r < guild.me.top_role)
        ]

        if roles_to_remove_filtered:
            try:
                await target.remove_roles(
                    *roles_to_remove_filtered,
                    reason=f"Назначение: {actor} назначил {target} в ветку {branch.value}",
                )
            except Exception:
                for r in roles_to_remove_filtered:
                    try:
                        await target.remove_roles(r)
                    except Exception:
                        pass

        if roles_to_add_filtered:
            try:
                await target.add_roles(
                    *roles_to_add_filtered,
                    reason=f"Назначение: {actor} назначил {target} в ветку {branch.value}",
                )
            except Exception:
                for r in roles_to_add_filtered:
                    try:
                        await target.add_roles(r)
                    except Exception:
                        pass

        titles = {
            BranchType.MODERATION: "Модератор",
            BranchType.SUPPORT: "Саппорт",
            BranchType.EVENTERS: "Эвентер",
        }
        position_title = titles.get(branch, "Рядовой")

        await AuditLogger.log_appointment(
            guild=guild,
            actor=actor,
            target=target,
            branch=branch,
            position_name=position_title,
        )
        await StaffRepository.increment_punishments(actor.id, delta=0)
        return True, f"Сотрудник {target.mention} успешно назначен на должность **{position_title}** ({branch.value})."

    @classmethod
    async def promote_member(
        cls,
        actor: discord.Member,
        target: discord.Member,
        target_rank: Optional[PositionRank] = None,
    ) -> tuple[bool, str]:
        actor_profile = HierarchyService.resolve_profile(actor)
        target_profile = HierarchyService.resolve_profile(target)

        allowed, err_msg = HierarchyService.can_promote(actor_profile, target_profile)
        if not allowed:
            return False, err_msg

        if await StaffRepository.is_user_blacklisted(target.guild.id, target.id):
            return False, "Пользователь находится в Черном Списке Команды Проекта (ЧСКП)."

        available = HierarchyService.get_available_promotions(actor_profile, target_profile)
        if not available:
            return False, "Нет доступных должностей для повышения сотрудника."

        if target_rank is not None:
            if target_rank not in available:
                return False, f"Вы не можете повысить сотрудника до должности {target_rank.display_name}."
            new_rank = target_rank
        else:
            new_rank = available[0]

        branch_cfg = cls._get_branch_config(target_profile.branch)
        if branch_cfg is None:
            return False, "Не удалось определить конфигурацию ветки сотрудника."

        current_rank = target_profile.rank
        guild = target.guild

        rank_to_role = {
            PositionRank.RANK_1: branch_cfg.rank_1_role_id,
            PositionRank.MASTER: CONFIG.rank_2_master_id,
            PositionRank.CURATOR: CONFIG.rank_3_curator_id,
            PositionRank.DEPUTY_ADMIN: CONFIG.rank_4_deputy_admin_id,
            PositionRank.ADMIN: CONFIG.rank_5_admin_id,
        }

        roles_to_remove: Set[discord.Role] = set()
        roles_to_add: Set[discord.Role] = set()

        for r_id in rank_to_role.values():
            role = guild.get_role(r_id)
            if role and role in target.roles:
                roles_to_remove.add(role)

        qualifier_role = guild.get_role(branch_cfg.master_qualifier_role_id)

        if new_rank == PositionRank.RANK_1:
            if qualifier_role and qualifier_role in target.roles:
                roles_to_remove.add(qualifier_role)
            r1 = guild.get_role(branch_cfg.rank_1_role_id)
            if r1:
                roles_to_add.add(r1)
        else:
            if qualifier_role:
                roles_to_add.add(qualifier_role)
            new_role = guild.get_role(rank_to_role[new_rank])
            if new_role:
                roles_to_add.add(new_role)

        roles_to_remove_filtered = [r for r in roles_to_remove if r and (target.guild.me is None or r < target.guild.me.top_role)]
        roles_to_add_filtered = [r for r in roles_to_add if r and (target.guild.me is None or r < target.guild.me.top_role)]

        if roles_to_remove_filtered:
            try:
                await target.remove_roles(*roles_to_remove_filtered, reason=f"Повышение: {actor} повысил {target} до {new_rank.display_name}")
            except Exception:
                for r in roles_to_remove_filtered:
                    try:
                        await target.remove_roles(r)
                    except Exception:
                        pass

        if roles_to_add_filtered:
            try:
                await target.add_roles(*roles_to_add_filtered, reason=f"Повышение: {actor} повысил {target} до {new_rank.display_name}")
            except Exception:
                for r in roles_to_add_filtered:
                    try:
                        await target.add_roles(r)
                    except Exception:
                        pass

        await AuditLogger.log_promotion(
            guild=guild,
            actor=actor,
            target=target,
            old_rank=current_rank,
            new_rank=new_rank,
            branch=target_profile.branch,
        )
        await StaffRepository.increment_punishments(actor.id, delta=0)
        return True, f"Сотрудник {target.mention} успешно повышен до должности **{new_rank.display_name}**."

    @classmethod
    async def demote_member(
        cls,
        actor: discord.Member,
        target: discord.Member,
        target_rank: Optional[PositionRank] = None,
    ) -> tuple[bool, str]:
        actor_profile = HierarchyService.resolve_profile(actor)
        target_profile = HierarchyService.resolve_profile(target)

        allowed, err_msg = HierarchyService.can_demote(actor_profile, target_profile)
        if not allowed:
            return False, err_msg

        available = HierarchyService.get_available_demotions(actor_profile, target_profile)
        if not available:
            return False, "Нет доступных должностей для понижения сотрудника."

        if target_rank is not None:
            if target_rank not in available:
                return False, f"Вы не можете понизить сотрудника до должности {target_rank.display_name}."
            new_rank = target_rank
        else:
            new_rank = available[0]

        branch_cfg = cls._get_branch_config(target_profile.branch)
        if branch_cfg is None:
            return False, "Не удалось определить конфигурацию ветки сотрудника."

        current_rank = target_profile.rank
        guild = target.guild

        rank_to_role = {
            PositionRank.RANK_1: branch_cfg.rank_1_role_id,
            PositionRank.MASTER: CONFIG.rank_2_master_id,
            PositionRank.CURATOR: CONFIG.rank_3_curator_id,
            PositionRank.DEPUTY_ADMIN: CONFIG.rank_4_deputy_admin_id,
            PositionRank.ADMIN: CONFIG.rank_5_admin_id,
        }

        roles_to_remove: Set[discord.Role] = set()
        roles_to_add: Set[discord.Role] = set()

        for r_id in rank_to_role.values():
            role = guild.get_role(r_id)
            if role and role in target.roles:
                roles_to_remove.add(role)

        qualifier_role = guild.get_role(branch_cfg.master_qualifier_role_id)

        if new_rank == PositionRank.RANK_1:
            if qualifier_role and qualifier_role in target.roles:
                roles_to_remove.add(qualifier_role)
            r1 = guild.get_role(branch_cfg.rank_1_role_id)
            if r1:
                roles_to_add.add(r1)
        else:
            if qualifier_role:
                roles_to_add.add(qualifier_role)
            new_role = guild.get_role(rank_to_role[new_rank])
            if new_role:
                roles_to_add.add(new_role)

        roles_to_remove_filtered = [r for r in roles_to_remove if r and (target.guild.me is None or r < target.guild.me.top_role)]
        roles_to_add_filtered = [r for r in roles_to_add if r and (target.guild.me is None or r < target.guild.me.top_role)]

        if roles_to_remove_filtered:
            try:
                await target.remove_roles(*roles_to_remove_filtered, reason=f"Понижение: {actor} понизил {target} до {new_rank.display_name}")
            except Exception:
                for r in roles_to_remove_filtered:
                    try:
                        await target.remove_roles(r)
                    except Exception:
                        pass

        if roles_to_add_filtered:
            try:
                await target.add_roles(*roles_to_add_filtered, reason=f"Понижение: {actor} понизил {target} до {new_rank.display_name}")
            except Exception:
                for r in roles_to_add_filtered:
                    try:
                        await target.add_roles(r)
                    except Exception:
                        pass

        await AuditLogger.log_demotion(
            guild=guild,
            actor=actor,
            target=target,
            old_rank=current_rank,
            new_rank=new_rank,
            branch=target_profile.branch,
        )
        return True, f"Сотрудник {target.mention} успешно понижен до должности **{new_rank.display_name}**."

    @staticmethod
    def build_dismissal_dm_embed(
        guild: discord.Guild,
        target: discord.Member,
        reason: str,
        actor_name: str,
        warn_count: Optional[int] = None,
        max_warns: Optional[int] = None,
    ) -> discord.Embed:
        embed = discord.Embed(
            title="🥀 Снятие с должности • Kawaii World",
            description=(
                f"Вы были сняты со всех должностей команды проекта **{guild.name}**."
            ),
            color=CONFIG.danger_color,
            timestamp=discord.utils.utcnow(),
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(
            name="👤 Сотрудник",
            value=f"{target.mention} (`{target.display_name}`)",
            inline=False,
        )
        embed.add_field(
            name="📋 Причина",
            value=f"```{reason}```",
            inline=False,
        )
        if warn_count is not None and max_warns is not None:
            embed.add_field(
                name="⚠️ Активные выговоры",
                value=f"**{warn_count}** из **{max_warns}** (Превышен лимит)",
                inline=True,
            )
        embed.add_field(
            name="🛡️ Инициатор",
            value=actor_name,
            inline=True,
        )
        embed.add_field(
            name="🔒 Статус",
            value="Все должности, ветки и доступы команды проекта были аннулированы.",
            inline=False,
        )
        embed.set_footer(
            text=f"{guild.name} • Staff Management",
            icon_url=guild.icon.url if guild.icon else None,
        )
        return embed

    @classmethod
    async def dismiss_member(
        cls,
        actor: discord.Member,
        target: discord.Member,
        reason: Optional[str] = None,
        force: bool = False,
    ) -> tuple[bool, str]:
        # If not forced and not the bot itself, check staff hierarchy
        if not force and actor.id != target.guild.me.id:
            actor_profile = HierarchyService.resolve_profile(actor)
            target_profile = HierarchyService.resolve_profile(target)

            allowed, err_msg = HierarchyService.can_dismiss(actor_profile, target_profile)
            if not allowed:
                return False, err_msg

        roles_to_strip = (
            {CONFIG.base_staff_role_id}
            | CONFIG.all_branch_role_ids
            | CONFIG.all_qualifier_role_ids
            | CONFIG.all_rank_role_ids
        )

        me = target.guild.me
        roles_to_remove = [
            r for r in target.roles
            if r.id in roles_to_strip and (me is None or r < me.top_role)
        ]

        if roles_to_remove:
            try:
                await target.remove_roles(
                    *roles_to_remove,
                    reason=f"Снятие со стаффа: {actor}. Причина: {reason or 'Не указана'}",
                )
            except discord.Forbidden:
                for r in roles_to_remove:
                    try:
                        await target.remove_roles(r, reason=f"Снятие со стаффа: {actor}")
                    except Exception:
                        pass
            except Exception:
                pass

        await AuditLogger.log_dismissal(
            guild=target.guild,
            actor=actor,
            target=target,
            reason=reason,
        )

        # Send DM notification if this was a manual staff dismissal
        if actor.id != target.guild.me.id:
            try:
                dm_embed = cls.build_dismissal_dm_embed(
                    guild=target.guild,
                    target=target,
                    reason=reason or "Решение руководства стаффа",
                    actor_name=actor.mention,
                )
                await target.send(embed=dm_embed)
            except Exception:
                pass

        return True, f"Сотрудник {target.mention} был успешно снят со стаффа."

    @classmethod
    async def admin_appoint(
        cls,
        actor: discord.Member,
        target: discord.Member,
        appoint_type: str,
    ) -> tuple[bool, str]:
        actor_profile = HierarchyService.resolve_profile(actor)
        target_profile = HierarchyService.resolve_profile(target)

        is_owner = actor_profile.is_supreme or actor_profile.rank == PositionRank.OWNER
        is_staff_admin = actor_profile.rank == PositionRank.STAFF_ADMIN

        if not (is_owner or is_staff_admin):
            return False, "У вас недостаточно прав для использования админ-постановки."

        if target_profile.rank == PositionRank.OWNER:
            return False, "Нельзя изменять должность владельца проекта."

        if await StaffRepository.is_user_blacklisted(target.guild.id, target.id):
            return False, "Пользователь находится в Черном Списке Команды Проекта (ЧСКП) и не может быть назначен на должность."

        guild = target.guild

        if appoint_type == "staff_admin":
            if not is_owner:
                return False, "Назначать Стафф Администраторов может только Владелец проекта."

            roles_to_remove: Set[discord.Role] = set()
            for r_id in (
                CONFIG.all_rank_role_ids
                | CONFIG.all_qualifier_role_ids
                | CONFIG.all_branch_role_ids
            ):
                role = guild.get_role(r_id)
                if role and role in target.roles:
                    roles_to_remove.add(role)

            base_role = guild.get_role(CONFIG.base_staff_role_id)
            sa1 = guild.get_role(CONFIG.staff_admin_primary_role_id)
            sa2 = guild.get_role(CONFIG.staff_admin_secondary_role_id)

            roles_to_add = {r for r in (base_role, sa1, sa2) if r is not None}
            final_roles = (set(target.roles) - roles_to_remove) | roles_to_add

            await target.edit(
                roles=list(final_roles),
                reason=f"Админ-постановка: {actor} назначил {target} на должность Стафф Администратора",
            )
            await AuditLogger.log_appointment(
                guild=guild,
                actor=actor,
                target=target,
                branch=BranchType.STAFF,
                position_name="Стафф Администратор",
            )
            return True, f"Сотрудник {target.mention} успешно назначен на должность **Стафф Администратор**."

        branch_map = {
            "admin_moderation": (BranchType.MODERATION, CONFIG.moderation),
            "admin_support": (BranchType.SUPPORT, CONFIG.support),
            "admin_eventers": (BranchType.EVENTERS, CONFIG.eventers),
        }

        if appoint_type not in branch_map:
            return False, "Неизвестный тип руководящей должности."

        branch_type, branch_cfg = branch_map[appoint_type]

        roles_to_remove = set()
        for r_id in (
            CONFIG.all_rank_role_ids
            | CONFIG.all_qualifier_role_ids
            | (CONFIG.all_branch_role_ids - {branch_cfg.branch_role_id})
        ):
            role = guild.get_role(r_id)
            if role and role in target.roles:
                roles_to_remove.add(role)

        base_role = guild.get_role(CONFIG.base_staff_role_id)
        b_role = guild.get_role(branch_cfg.branch_role_id)
        qual_role = guild.get_role(branch_cfg.master_qualifier_role_id)
        admin_role = guild.get_role(CONFIG.rank_5_admin_id)

        roles_to_add = {r for r in (base_role, b_role, qual_role, admin_role) if r is not None}
        final_roles = (set(target.roles) - roles_to_remove) | roles_to_add

        await target.edit(
            roles=list(final_roles),
            reason=f"Админ-постановка: {actor} назначил {target} Администратором ветки {branch_type.value}",
        )
        await AuditLogger.log_appointment(
            guild=guild,
            actor=actor,
            target=target,
            branch=branch_type,
            position_name=f"Администратор ({branch_type.value})",
        )
        return True, f"Сотрудник {target.mention} успешно назначен на должность **Администратор** ветки **{branch_type.value}**."
