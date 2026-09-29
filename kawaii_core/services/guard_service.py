from typing import Optional
import discord

from kawaii_core.config import CONFIG
from kawaii_core.database.repository import SecurityRepository
from kawaii_core.domain.enums import GuardPermission
from kawaii_core.services.log_service import AuditLogger


class GuardService:
    @staticmethod
    async def is_action_allowed(actor_id: int, guild_id: int, permission: GuardPermission) -> bool:
        perms = await SecurityRepository.get_permissions(actor_id, guild_id)
        return getattr(perms, permission.value, False)

    @classmethod
    async def handle_infraction(
        cls,
        guild: discord.Guild,
        actor_id: int,
        action_name: str,
        details: str,
    ) -> None:
        if actor_id == guild.me.id:
            return

        actor_member = guild.get_member(actor_id)
        if actor_member and CONFIG.owner_role_id in {r.id for r in actor_member.roles}:
            return

        strikes = await SecurityRepository.increment_strike(
            user_id=actor_id,
            guild_id=guild.id,
            action_description=action_name,
        )

        await AuditLogger.log_guard_alert(
            guild=guild,
            actor_id=actor_id,
            action=action_name,
            strikes=strikes,
            details=details,
        )

        if actor_member:
            try:
                dm_message = (
                    f"⚠️ **Предупреждение системы безопасности Kawaii World**\n"
                    f"Вы совершили действие: **{action_name}**, это запрещено регламентом сервера.\n"
                    f"Вам выдано замечание: **{strikes}/{CONFIG.max_security_strikes}** Замечаний.\n"
                    f"*(При получении 5/5 замечаний ваши роли будут аннулированы и будет выдана блокировка).*"
                )
                await actor_member.send(dm_message)
            except discord.HTTPException:
                pass

            if strikes >= CONFIG.max_security_strikes:
                quarantine_role = guild.get_role(CONFIG.quarantine_ban_role_id)
                roles_to_keep = [quarantine_role] if quarantine_role else []

                try:
                    await actor_member.edit(
                        roles=roles_to_keep,
                        reason=f"Превышение лимита замечаний безопасности ({strikes}/{CONFIG.max_security_strikes})",
                    )
                    await AuditLogger.log_quarantine(guild=guild, member=actor_member, strikes=strikes)
                except discord.HTTPException:
                    pass
