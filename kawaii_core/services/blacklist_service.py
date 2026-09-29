from datetime import datetime, timezone
from typing import Set
import discord

from kawaii_core.config import CONFIG
from kawaii_core.database.repository import StaffRepository
from kawaii_core.domain.enums import BranchType, PositionRank
from kawaii_core.domain.hierarchy import HierarchyService
from kawaii_core.services.log_service import AuditLogger


class BlacklistService:
    @classmethod
    async def add_to_blacklist(
        cls,
        actor: discord.Member,
        target: discord.Member,
        reason: str,
    ) -> tuple[bool, str]:
        if actor.id == target.id:
            return False, "Вы не можете занести самого себя в ЧСКП."

        actor_profile = HierarchyService.resolve_profile(actor)
        target_profile = HierarchyService.resolve_profile(target)

        if not actor_profile.is_supreme and actor_profile.rank < PositionRank.MASTER:
            return False, "Вносить в ЧСКП могут только Мастера и выше."

        if target_profile.rank == PositionRank.OWNER:
            return False, "Нельзя внести в ЧСКП владельца сервера."

        if target_profile.is_staff and target_profile.rank != PositionRank.NONE:
            if actor_profile.rank <= target_profile.rank and not actor_profile.is_supreme:
                return False, "Вы не можете внести в ЧСКП сотрудника равной или старшей должности."

            if (
                actor_profile.rank == PositionRank.STAFF_ADMIN
                and target_profile.rank == PositionRank.STAFF_ADMIN
                and not actor_profile.is_supreme
            ):
                return False, "Стафф Администратор не может внести другого Стафф Администратора в ЧСКП."

        is_already_bl = await StaffRepository.is_user_blacklisted(target.guild.id, target.id)
        if is_already_bl:
            return False, f"Пользователь {target.mention} уже находится в Черном Списке Команды Проекта (ЧСКП)."

        if actor_profile.branch not in (BranchType.NONE, BranchType.STAFF):
            issuer_rank_title = f"{actor_profile.position_title} ({actor_profile.branch.value})"
        else:
            issuer_rank_title = actor_profile.position_title

        now = datetime.now(timezone.utc)

        await StaffRepository.add_to_blacklist(
            guild_id=target.guild.id,
            target_id=target.id,
            issuer_id=actor.id,
            issuer_rank_weight=int(actor_profile.rank),
            issuer_rank_title=issuer_rank_title,
            reason=reason,
            created_at=now,
        )

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
                    reason=f"Внесение в ЧСКП: аннулирование всех должностей ({actor})",
                )
            except discord.Forbidden:
                for r in roles_to_remove:
                    try:
                        await target.remove_roles(r, reason="Внесение в ЧСКП")
                    except Exception:
                        pass
            except Exception:
                pass

        try:
            embed_dm = discord.Embed(
                title="🚫 Внесение в ЧСКП • Kawaii World",
                description=(
                    f"Вы были внесены в **Черный Список Команды Проекта (ЧСКП)** сервера **{target.guild.name}**."
                ),
                color=CONFIG.danger_color,
                timestamp=now,
            )
            if target.guild.icon:
                embed_dm.set_thumbnail(url=target.guild.icon.url)

            embed_dm.add_field(
                name="👤 Пользователь",
                value=f"{target.mention} (`{target.display_name}`)",
                inline=False,
            )
            embed_dm.add_field(
                name="📋 Причина внесения",
                value=f"```{reason}```",
                inline=False,
            )
            embed_dm.add_field(
                name="🛡️ Инициатор",
                value=f"{actor.mention} (`{issuer_rank_title}`)",
                inline=True,
            )
            embed_dm.add_field(
                name="⏳ Срок действия",
                value="**Бессрочно**",
                inline=True,
            )
            embed_dm.add_field(
                name="🔒 Последствия",
                value="Все роли и права стаффа аннулированы. Доступ к назначению на любые должности заблокирован.",
                inline=False,
            )
            embed_dm.set_footer(
                text=f"{target.guild.name} • Blacklist System",
                icon_url=target.guild.icon.url if target.guild.icon else None,
            )
            await target.send(embed=embed_dm)
        except Exception:
            pass

        await AuditLogger.log_blacklist_add(
            guild=target.guild,
            actor=actor,
            target=target,
            issuer_rank_title=issuer_rank_title,
            reason=reason,
        )
        await StaffRepository.increment_punishments(actor.id, delta=1)

        return True, f"Пользователь {target.mention} успешно внесен в **Черный Список Команды Проекта (ЧСКП)**."

    @classmethod
    async def remove_from_blacklist(
        cls,
        actor: discord.Member,
        target: discord.Member,
        reason: str,
    ) -> tuple[bool, str]:
        actor_profile = HierarchyService.resolve_profile(actor)

        if not actor_profile.is_supreme and actor_profile.rank < PositionRank.MASTER:
            return False, "Выносить из ЧСКП могут только Мастера и выше."

        record = await StaffRepository.get_active_blacklist(target.guild.id, target.id)
        if not record:
            return False, f"Пользователь {target.mention} не находится в активном ЧСКП."

        if actor_profile.rank < record.issuer_rank_weight and not actor_profile.is_supreme:
            return False, (
                f"ЧСКП был выдан должностью выше вашей ({record.issuer_rank_title}). "
                f"Обратитесь к <@{record.issuer_id}> или высшей администрации для вынесения."
            )

        now = datetime.now(timezone.utc)
        await StaffRepository.remove_from_blacklist(
            blacklist_id=record.id,
            unlisted_by=actor.id,
            unlisted_at=now,
            unlisted_reason=reason,
        )

        try:
            embed_dm = discord.Embed(
                title="🕊️ Вынесение из ЧСКП • Kawaii World",
                description=(
                    f"Вы были успешно вынесены из **Черного Списка Команды Проекта (ЧСКП)** сервера **{target.guild.name}**."
                ),
                color=CONFIG.success_color,
                timestamp=now,
            )
            if target.guild.icon:
                embed_dm.set_thumbnail(url=target.guild.icon.url)

            embed_dm.add_field(
                name="👤 Пользователь",
                value=f"{target.mention} (`{target.display_name}`)",
                inline=False,
            )
            embed_dm.add_field(
                name="📋 Причина амнистии",
                value=f"```{reason}```",
                inline=False,
            )
            embed_dm.add_field(
                name="🛡️ Решение принял",
                value=f"{actor.mention}",
                inline=True,
            )
            embed_dm.add_field(
                name="🔓 Статус",
                value="Все ограничения на вступление в команду проекта и участие сняты.",
                inline=False,
            )
            embed_dm.set_footer(
                text=f"{target.guild.name} • Blacklist System",
                icon_url=target.guild.icon.url if target.guild.icon else None,
            )
            await target.send(embed=embed_dm)
        except Exception:
            pass

        await AuditLogger.log_blacklist_remove(
            guild=target.guild,
            actor=actor,
            target=target,
            reason=reason,
        )

        return True, f"Пользователь {target.mention} успешно вынесен из **Черного Списка Команды Проекта (ЧСКП)**."
