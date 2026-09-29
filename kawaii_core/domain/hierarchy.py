from typing import Optional, Set
import discord

from kawaii_core.config import CONFIG, BranchRoleConfig
from kawaii_core.domain.enums import BranchType, PositionRank
from kawaii_core.domain.models import BlacklistRecord, StaffProfile, WarnRecord


class HierarchyService:
    @staticmethod
    def resolve_profile(
        member: discord.Member,
        active_warns: int = 0,
        punishments: int = 0,
        blacklist_record: Optional[BlacklistRecord] = None,
    ) -> StaffProfile:
        role_ids: Set[int] = {role.id for role in member.roles}
        is_bl = blacklist_record is not None

        if CONFIG.owner_role_id in role_ids:
            return StaffProfile(
                user_id=member.id,
                guild_id=member.guild.id,
                is_staff=True,
                branch=BranchType.STAFF,
                rank=PositionRank.OWNER,
                position_title="Владелец",
                active_warns=active_warns,
                total_punishments=punishments,
                raw_role_ids=role_ids,
                is_blacklisted=is_bl,
                blacklist_record=blacklist_record,
            )

        is_staff_admin = (
            CONFIG.staff_admin_primary_role_id in role_ids
            and CONFIG.staff_admin_secondary_role_id in role_ids
        )
        if is_staff_admin:
            return StaffProfile(
                user_id=member.id,
                guild_id=member.guild.id,
                is_staff=True,
                branch=BranchType.STAFF,
                rank=PositionRank.STAFF_ADMIN,
                position_title="Стафф Администратор",
                active_warns=active_warns,
                total_punishments=punishments,
                raw_role_ids=role_ids,
                is_blacklisted=is_bl,
                blacklist_record=blacklist_record,
            )

        if CONFIG.base_staff_role_id not in role_ids:
            return StaffProfile(
                user_id=member.id,
                guild_id=member.guild.id,
                is_staff=False,
                branch=BranchType.NONE,
                rank=PositionRank.NONE,
                position_title="Не состоит",
                active_warns=active_warns,
                total_punishments=punishments,
                raw_role_ids=role_ids,
                is_blacklisted=is_bl,
                blacklist_record=blacklist_record,
            )

        branch = BranchType.NONE
        branch_cfg: Optional[BranchRoleConfig] = None

        if CONFIG.moderation.branch_role_id in role_ids:
            branch = BranchType.MODERATION
            branch_cfg = CONFIG.moderation
        elif CONFIG.support.branch_role_id in role_ids:
            branch = BranchType.SUPPORT
            branch_cfg = CONFIG.support
        elif CONFIG.eventers.branch_role_id in role_ids:
            branch = BranchType.EVENTERS
            branch_cfg = CONFIG.eventers

        if branch == BranchType.NONE or branch_cfg is None:
            return StaffProfile(
                user_id=member.id,
                guild_id=member.guild.id,
                is_staff=True,
                branch=BranchType.NONE,
                rank=PositionRank.NONE,
                position_title="Без ветки",
                active_warns=active_warns,
                total_punishments=punishments,
                raw_role_ids=role_ids,
                is_blacklisted=is_bl,
                blacklist_record=blacklist_record,
            )

        has_qualifier = branch_cfg.master_qualifier_role_id in role_ids

        rank = PositionRank.NONE
        position_title = "Стажер"

        if has_qualifier:
            if CONFIG.rank_5_admin_id in role_ids:
                rank = PositionRank.ADMIN
                position_title = "Администратор"
            elif CONFIG.rank_4_deputy_admin_id in role_ids:
                rank = PositionRank.DEPUTY_ADMIN
                position_title = "Зам.Администратора"
            elif CONFIG.rank_3_curator_id in role_ids:
                rank = PositionRank.CURATOR
                position_title = "Куратор"
            elif CONFIG.rank_2_master_id in role_ids:
                rank = PositionRank.MASTER
                position_title = "Мастер"

        if rank == PositionRank.NONE:
            if branch_cfg.rank_1_role_id in role_ids:
                rank = PositionRank.RANK_1
                titles = {
                    BranchType.MODERATION: "Модератор",
                    BranchType.SUPPORT: "Саппорт",
                    BranchType.EVENTERS: "Эвентер",
                }
                position_title = titles.get(branch, "Рядовой")

        return StaffProfile(
            user_id=member.id,
            guild_id=member.guild.id,
            is_staff=True,
            branch=branch,
            rank=rank,
            position_title=position_title,
            active_warns=active_warns,
            total_punishments=punishments,
            raw_role_ids=role_ids,
            is_blacklisted=is_bl,
            blacklist_record=blacklist_record,
        )

    @classmethod
    def can_promote(cls, actor: StaffProfile, target: StaffProfile) -> tuple[bool, str]:
        if not actor.is_supreme and actor.user_id == target.user_id:
            return False, "Вы не можете повысить самого себя."

        if not target.is_staff or target.branch == BranchType.NONE:
            return False, "Пользователь не состоит ни на одной ветке стаффа."

        if target.rank >= PositionRank.ADMIN:
            return False, "Пользователь уже имеет максимальную должность ветки или выше."

        # Must have at least one rank the actor is allowed to promote to
        available = cls.get_available_promotions(actor, target)
        if not available:
            return False, "Нет доступных должностей для повышения сотрудника с вашими правами."

        return True, ""

    @classmethod
    def get_available_promotions(cls, actor: StaffProfile, target: StaffProfile) -> list[PositionRank]:
        if not actor.is_supreme and actor.user_id == target.user_id:
            return []
        if not target.is_staff or target.branch == BranchType.NONE:
            return []
        if actor.rank < PositionRank.MASTER:
            return []
        if actor.rank <= target.rank:
            return []
        if actor.rank < PositionRank.STAFF_ADMIN and actor.branch != target.branch:
            return []

        ranks: list[PositionRank] = []
        for r in (PositionRank.MASTER, PositionRank.CURATOR, PositionRank.DEPUTY_ADMIN, PositionRank.ADMIN):
            if r <= target.rank:
                continue
            if r == PositionRank.ADMIN and actor.rank < PositionRank.STAFF_ADMIN:
                continue
            if r >= actor.rank and not actor.is_supreme:
                continue
            ranks.append(r)
        return ranks

    @classmethod
    def get_available_demotions(cls, actor: StaffProfile, target: StaffProfile) -> list[PositionRank]:
        if not actor.is_supreme and actor.user_id == target.user_id:
            return []
        if not target.is_staff or target.branch == BranchType.NONE:
            return []
        if target.rank < PositionRank.MASTER:
            return []
        if actor.rank < PositionRank.MASTER:
            return []
        if actor.rank <= target.rank:
            return []
        if target.rank == PositionRank.ADMIN and actor.rank < PositionRank.STAFF_ADMIN:
            return []
        if actor.rank < PositionRank.STAFF_ADMIN and actor.branch != target.branch:
            return []

        # Return lower ranks ordered from highest to lowest
        ranks: list[PositionRank] = []
        for r in (PositionRank.DEPUTY_ADMIN, PositionRank.CURATOR, PositionRank.MASTER, PositionRank.RANK_1):
            if r < target.rank:
                ranks.append(r)
        return ranks

    @classmethod
    def can_demote(cls, actor: StaffProfile, target: StaffProfile) -> tuple[bool, str]:
        if not actor.is_supreme and actor.user_id == target.user_id:
            return False, "Вы не можете понизить самого себя."

        if not target.is_staff or target.branch == BranchType.NONE:
            return False, "Пользователь не состоит в стаффе."

        if target.rank < PositionRank.MASTER:
            return False, "Пользователь уже на минимальной должности (Рядовой). Для исключения используйте кнопку «Снять»."

        if target.rank == PositionRank.ADMIN and actor.rank < PositionRank.STAFF_ADMIN:
            return False, "Понижать Администратора может только Стафф Администратор или Владелец."

        if actor.rank < PositionRank.MASTER:
            return False, "Понижать сотрудников могут только Мастера и выше."

        if actor.rank <= target.rank:
            return False, "Вы не можете понизить сотрудника равной или старшей должности."

        if actor.rank < PositionRank.STAFF_ADMIN and actor.branch != target.branch:
            return False, f"Вы можете управлять сотрудниками только своей ветки ({actor.branch.value})."

        return True, ""

    @classmethod
    def can_appoint(cls, actor: StaffProfile, target: StaffProfile, target_branch: BranchType) -> tuple[bool, str]:
        if not actor.is_supreme and actor.user_id == target.user_id:
            return False, "Вы не можете назначить самого себя."

        if target.is_staff and target.branch != BranchType.NONE:
            return False, "Пользователь уже состоит в стаффе."

        if actor.rank < PositionRank.MASTER:
            return False, "Назначать сотрудников могут только Мастера и выше."

        if actor.rank < PositionRank.STAFF_ADMIN and actor.branch != target_branch:
            return False, f"Вы можете назначать сотрудников только в свою ветку ({actor.branch.value})."

        return True, ""

    @classmethod
    def can_dismiss(cls, actor: StaffProfile, target: StaffProfile) -> tuple[bool, str]:
        if not actor.is_supreme and actor.user_id == target.user_id:
            return False, "Вы не можете снять самого себя."

        if not target.is_staff:
            return False, "Пользователь не состоит в стаффе."

        if target.rank == PositionRank.ADMIN and actor.rank < PositionRank.STAFF_ADMIN:
            return False, "Снимать Администратора может только Стафф Администратор или Владелец."

        if actor.rank < PositionRank.MASTER:
            return False, "Снимать сотрудников могут только Мастера и выше."

        if actor.rank <= target.rank:
            return False, "Вы не можете снять сотрудника равной или старшей должности."

        if actor.rank < PositionRank.STAFF_ADMIN and actor.branch != target.branch:
            return False, f"Вы можете снимать сотрудников только своей ветки ({actor.branch.value})."

        return True, ""

    @classmethod
    def can_warn(cls, actor: StaffProfile, target: StaffProfile) -> tuple[bool, str]:
        if not actor.is_supreme and actor.user_id == target.user_id:
            return False, "Вы не можете выдать выговор самому себе."

        if not target.is_staff or target.branch == BranchType.NONE:
            return False, "Выговор можно выдать только действующему сотруднику стаффа."

        if actor.rank < PositionRank.MASTER:
            return False, "Выдавать выговоры могут только Мастера и выше."

        if target.rank == PositionRank.ADMIN and actor.rank < PositionRank.STAFF_ADMIN:
            return False, "Выдавать выговор Администратору может только Стафф Администратор или Владелец."

        if actor.rank <= target.rank:
            return False, "Вы не можете выдать выговор сотруднику равной или старшей должности."

        if actor.rank < PositionRank.STAFF_ADMIN and actor.branch != target.branch:
            return False, f"Вы можете выдавать выговоры только сотрудникам своей ветки ({actor.branch.value})."

        return True, ""

    @classmethod
    def can_unwarn(cls, actor: StaffProfile, target: StaffProfile, warn: WarnRecord) -> tuple[bool, str]:
        if not actor.is_supreme and actor.user_id == target.user_id:
            return False, "Вы не можете снять выговор самому себе."

        if actor.rank < PositionRank.MASTER:
            return False, "Снимать выговоры могут только Мастера и выше."

        if actor.rank < PositionRank.STAFF_ADMIN and actor.branch != target.branch:
            return False, f"Вы можете снимать выговоры только сотрудникам своей ветки ({actor.branch.value})."

        if actor.rank < warn.issuer_rank_weight and not actor.is_supreme:
            issuer_rank_name = PositionRank(warn.issuer_rank_weight).display_name
            return False, (
                f"Выговор был выдан должностью выше вашей ({issuer_rank_name}). "
                f"Обратитесь к <@{warn.issuer_id}>, чтобы снять выговор."
            )

        return True, ""
