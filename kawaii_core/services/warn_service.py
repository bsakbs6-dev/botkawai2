from datetime import datetime, timedelta, timezone
from typing import Optional
import discord

from kawaii_core.config import CONFIG
from kawaii_core.database.repository import StaffRepository
from kawaii_core.domain.enums import PositionRank
from kawaii_core.domain.hierarchy import HierarchyService
from kawaii_core.domain.models import WarnRecord
from kawaii_core.services.log_service import AuditLogger
from kawaii_core.services.staff_service import StaffService


class WarnService:
    @classmethod
    async def issue_warn(
        cls,
        actor: discord.Member,
        target: discord.Member,
        reason: str,
    ) -> tuple[bool, str]:
        actor_profile = HierarchyService.resolve_profile(actor)
        target_profile = HierarchyService.resolve_profile(target)

        allowed, err_msg = HierarchyService.can_warn(actor_profile, target_profile)
        if not allowed:
            return False, err_msg

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=CONFIG.warn_duration_days)

        await StaffRepository.create_warn(
            guild_id=target.guild.id,
            target_id=target.id,
            issuer_id=actor.id,
            issuer_rank_weight=actor_profile.rank.value,
            reason=reason,
            created_at=now,
            expires_at=expires_at,
        )

        await StaffRepository.increment_punishments(actor.id, delta=1)

        active_warns = await StaffRepository.get_active_warns(target.guild.id, target.id)
        active_count = len(active_warns)

        await AuditLogger.log_warn(
            guild=target.guild,
            actor=actor,
            target=target,
            reason=reason,
            expires_at=expires_at,
            active_count=active_count,
        )

        # Reached limit 3/3 - Auto Dismiss
        if active_count >= CONFIG.max_active_warns:
            dismiss_reason = f"Превышен лимит активных выговоров ({active_count}/{CONFIG.max_active_warns})"
            await StaffService.dismiss_member(
                actor=target.guild.me,
                target=target,
                reason=f"Автоматическое снятие: {dismiss_reason}. Последний выговор: {reason}",
                force=True,
            )
            try:
                dm_embed = StaffService.build_dismissal_dm_embed(
                    guild=target.guild,
                    target=target,
                    reason=f"{dismiss_reason}\nПоследний выговор от {actor.display_name}: {reason}",
                    actor_name=f"Автоматическая система (по выговору от {actor.display_name})",
                    warn_count=active_count,
                    max_warns=CONFIG.max_active_warns,
                )
                await target.send(embed=dm_embed)
            except Exception:
                pass

            return True, (
                f"Сотруднику {target.mention} выдан выговор ({active_count}/{CONFIG.max_active_warns}).\n"
                f"🚨 **Превышен лимит выговоров!** Сотрудник был автоматически снят со всех должностей."
            )

        try:
            dm_embed = cls._build_warn_dm_embed(
                guild=target.guild,
                target=target,
                reason=reason,
                actor=actor,
                active_count=active_count,
                max_warns=CONFIG.max_active_warns,
                expires_at=expires_at,
            )
            await target.send(embed=dm_embed)
        except Exception:
            pass

        return True, f"Сотруднику {target.mention} успешно выдан выговор ({active_count}/{CONFIG.max_active_warns}). Причина: {reason}"

    @staticmethod
    def _build_warn_dm_embed(
        guild: discord.Guild,
        target: discord.Member,
        reason: str,
        actor: discord.Member,
        active_count: int,
        max_warns: int,
        expires_at: datetime,
    ) -> discord.Embed:
        embed = discord.Embed(
            title="⚠️ Получен выговор • Kawaii World",
            description=(
                f"Вам был выдан официальный выговор стаффа на сервере **{guild.name}**."
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
            name="📋 Причина выговора",
            value=f"```{reason}```",
            inline=False,
        )
        embed.add_field(
            name="🛡️ Выдал",
            value=f"{actor.mention}",
            inline=True,
        )
        embed.add_field(
            name="📊 Активные выговоры",
            value=f"**{active_count}** из **{max_warns}**",
            inline=True,
        )
        embed.add_field(
            name="⏳ Срок действия",
            value=f"Истекает <t:{int(expires_at.timestamp())}:R>",
            inline=False,
        )
        embed.set_footer(
            text=f"{guild.name} • Staff Warn System",
            icon_url=guild.icon.url if guild.icon else None,
        )
        return embed

    @classmethod
    async def remove_warn(
        cls,
        actor: discord.Member,
        target: discord.Member,
        warn_id: Optional[int] = None,
        reason: str = "Амнистия / снятие выговора",
    ) -> tuple[bool, str]:
        active_warns = await StaffRepository.get_active_warns(target.guild.id, target.id)
        if not active_warns:
            return False, f"У сотрудника {target.mention} нет активных выговоров."

        target_warn: Optional[WarnRecord] = None
        if warn_id is not None:
            for w in active_warns:
                if w.id == warn_id:
                    target_warn = w
                    break
            if target_warn is None:
                return False, f"Активный выговор с ID #{warn_id} не найден."
        else:
            target_warn = active_warns[0]

        actor_profile = HierarchyService.resolve_profile(actor)
        target_profile = HierarchyService.resolve_profile(target)

        allowed, err_msg = HierarchyService.can_unwarn(actor_profile, target_profile, target_warn)
        if not allowed:
            return False, err_msg

        await StaffRepository.deactivate_warn(target_warn.id)
        remaining_warns = await StaffRepository.get_active_warns(target.guild.id, target.id)

        await AuditLogger.log_unwarn(
            guild=target.guild,
            actor=actor,
            target=target,
            reason=reason,
            active_count=len(remaining_warns),
        )

        return True, f"Выговор #{target_warn.id} с сотрудника {target.mention} успешно снят. Осталось выговоров: {len(remaining_warns)}/{CONFIG.max_active_warns}."

    @classmethod
    async def process_expired_warns(cls, guild: discord.Guild) -> None:
        expired = await StaffRepository.deactivate_expired_warns()
        for w in expired:
            await AuditLogger.log_warn_expired(guild=guild, target_id=w.target_id, reason=w.reason)
