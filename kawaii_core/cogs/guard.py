from datetime import datetime, timezone
from typing import Optional, Set
import discord
from discord.ext import commands

from kawaii_core.config import CONFIG
from kawaii_core.domain.enums import GuardPermission
from kawaii_core.services.guard_service import GuardService


class GuardCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _is_owner_or_bot(self, guild: discord.Guild, user_id: int) -> bool:
        if user_id == self.bot.user.id:  # type: ignore[union-attr]
            return True
        member = guild.get_member(user_id)
        if member and CONFIG.owner_role_id in {r.id for r in member.roles}:
            return True
        return False

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        guild = after.guild
        if guild.id != CONFIG.guild_id:
            return

        now = datetime.now(timezone.utc)

        # 1. Role assignments / revocations (ПКМ)
        if before.roles != after.roles:
            added_roles = set(after.roles) - set(before.roles)
            removed_roles = set(before.roles) - set(after.roles)

            staff_role_ids = (
                {CONFIG.base_staff_role_id}
                | CONFIG.all_branch_role_ids
                | CONFIG.all_qualifier_role_ids
                | CONFIG.all_rank_role_ids
            )
            added_staff_roles = [r for r in added_roles if r.id in staff_role_ids]
            if added_staff_roles:
                from kawaii_core.database.repository import StaffRepository
                if await StaffRepository.is_user_blacklisted(guild.id, after.id):
                    clean_roles = [r for r in after.roles if r.id not in staff_role_ids]
                    await after.edit(
                        roles=clean_roles,
                        reason="Защита: попытка выдать роль стаффа пользователю из Черного Списка (ЧСКП)",
                    )
                    role_names = ", ".join(f"`@{r.name}`" for r in added_staff_roles)
                    try:
                        channel = guild.get_channel(CONFIG.log_channel_id)
                        if isinstance(channel, discord.TextChannel):
                            embed_bl_guard = discord.Embed(
                                title="🚨 Блокировка выдачи роли (ЧСКП)",
                                description=(
                                    f"Была заблокирована попытка выдать роль(и) стаффа {role_names} "
                                    f"пользователю {after.mention} (`{after.id}`), так как он находится в **ЧСКП**!\n"
                                    f"Роли были немедленно сняты системой."
                                ),
                                color=CONFIG.danger_color,
                                timestamp=now,
                            )
                            embed_bl_guard.set_footer(text="Kawaii World • Blacklist Guard")
                            await channel.send(embed=embed_bl_guard)
                    except Exception:
                        pass
                    return

            try:
                async for entry in guild.audit_logs(action=discord.AuditLogAction.member_role_update, limit=3):
                    if entry.target and entry.target.id == after.id:
                        delta = (now - entry.created_at).total_seconds()
                        if delta <= 7:
                            actor = entry.user
                            if not actor or self._is_owner_or_bot(guild, actor.id):
                                return

                            is_allowed = await GuardService.is_action_allowed(
                                actor_id=actor.id,
                                guild_id=guild.id,
                                permission=GuardPermission.MANAGE_ROLES_PKM,
                            )

                            if not is_allowed:
                                await after.edit(
                                    roles=before.roles,
                                    reason="Защита: несанкционированное изменение ролей через контекстное меню (ПКМ)",
                                )
                                role_names = ", ".join(f"`@{r.name}`" for r in (added_roles | removed_roles))
                                await GuardService.handle_infraction(
                                    guild=guild,
                                    actor_id=actor.id,
                                    action_name="Выдача/снятие ролей (ПКМ)",
                                    details=f"Попытка изменить роли {role_names} пользователю {after.mention}",
                                )
                            break
            except discord.HTTPException:
                pass

        # 2. Timeout (Мут)
        if before.timed_out_until != after.timed_out_until and after.timed_out_until is not None:
            try:
                async for entry in guild.audit_logs(action=discord.AuditLogAction.member_update, limit=3):
                    if entry.target and entry.target.id == after.id:
                        delta = (now - entry.created_at).total_seconds()
                        if delta <= 7:
                            actor = entry.user
                            if not actor or self._is_owner_or_bot(guild, actor.id):
                                return

                            is_allowed = await GuardService.is_action_allowed(
                                actor_id=actor.id,
                                guild_id=guild.id,
                                permission=GuardPermission.TIMEOUT_MEMBERS,
                            )

                            if not is_allowed:
                                await after.timeout(None, reason="Защита: несанкционированный таймаут/мут")
                                await GuardService.handle_infraction(
                                    guild=guild,
                                    actor_id=actor.id,
                                    action_name="Таймаут (мут) участника",
                                    details=f"Попытка выдать таймаут пользователю {after.mention}",
                                )
                            break
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member) -> None:
        if guild.id != CONFIG.guild_id:
            return

        now = datetime.now(timezone.utc)
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.ban, limit=3):
                if entry.target and entry.target.id == user.id:
                    delta = (now - entry.created_at).total_seconds()
                    if delta <= 7:
                        actor = entry.user
                        if not actor or self._is_owner_or_bot(guild, actor.id):
                            return

                        is_allowed = await GuardService.is_action_allowed(
                            actor_id=actor.id,
                            guild_id=guild.id,
                            permission=GuardPermission.BAN_MEMBERS,
                        )

                        if not is_allowed:
                            await guild.unban(user, reason="Защита: несанкционированный бан участника")
                            await GuardService.handle_infraction(
                                guild=guild,
                                actor_id=actor.id,
                                action_name="Бан участника",
                                details=f"Попытка забанить пользователя {user.mention} (`{user.id}`)",
                            )
                        break
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        guild = member.guild
        if guild.id != CONFIG.guild_id:
            return

        now = datetime.now(timezone.utc)
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.kick, limit=3):
                if entry.target and entry.target.id == member.id:
                    delta = (now - entry.created_at).total_seconds()
                    if delta <= 7:
                        actor = entry.user
                        if not actor or self._is_owner_or_bot(guild, actor.id):
                            return

                        is_allowed = await GuardService.is_action_allowed(
                            actor_id=actor.id,
                            guild_id=guild.id,
                            permission=GuardPermission.KICK_MEMBERS,
                        )

                        if not is_allowed:
                            await GuardService.handle_infraction(
                                guild=guild,
                                actor_id=actor.id,
                                action_name="Кик участника",
                                details=f"Пользователь {member.mention} (`{member.id}`) был исключен",
                            )
                        break
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        guild = role.guild
        if guild.id != CONFIG.guild_id:
            return

        now = datetime.now(timezone.utc)
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.role_create, limit=3):
                if entry.target and entry.target.id == role.id:
                    delta = (now - entry.created_at).total_seconds()
                    if delta <= 7:
                        actor = entry.user
                        if not actor or self._is_owner_or_bot(guild, actor.id):
                            return

                        is_allowed = await GuardService.is_action_allowed(
                            actor_id=actor.id,
                            guild_id=guild.id,
                            permission=GuardPermission.CREATE_ROLES,
                        )

                        if not is_allowed:
                            try:
                                await role.delete(reason="Защита: несанкционированное создание роли")
                            except discord.HTTPException:
                                pass

                            await GuardService.handle_infraction(
                                guild=guild,
                                actor_id=actor.id,
                                action_name="Создание роли",
                                details=f"Создана роль @{role.name}",
                            )
                        break
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        guild = role.guild
        if guild.id != CONFIG.guild_id:
            return

        now = datetime.now(timezone.utc)
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.role_delete, limit=3):
                if entry.target and entry.target.id == role.id:
                    delta = (now - entry.created_at).total_seconds()
                    if delta <= 7:
                        actor = entry.user
                        if not actor or self._is_owner_or_bot(guild, actor.id):
                            return

                        is_allowed = await GuardService.is_action_allowed(
                            actor_id=actor.id,
                            guild_id=guild.id,
                            permission=GuardPermission.DELETE_ROLES,
                        )

                        if not is_allowed:
                            # Recreate deleted role
                            try:
                                await guild.create_role(
                                    name=role.name,
                                    permissions=role.permissions,
                                    colour=role.colour,
                                    hoist=role.hoist,
                                    mentionable=role.mentionable,
                                    reason="Защита: автоматическое восстановление удаленной роли",
                                )
                            except discord.HTTPException:
                                pass

                            await GuardService.handle_infraction(
                                guild=guild,
                                actor_id=actor.id,
                                action_name="Удаление роли",
                                details=f"Удалена роль @{role.name} (была автоматически воссоздана)",
                            )
                        break
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        if before.permissions.value == after.permissions.value:
            return

        guild = after.guild
        if guild.id != CONFIG.guild_id:
            return
        now = datetime.now(timezone.utc)

        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.role_update, limit=3):
                if entry.target and entry.target.id == after.id:
                    delta = (now - entry.created_at).total_seconds()
                    if delta <= 7:
                        actor = entry.user
                        if not actor or self._is_owner_or_bot(guild, actor.id):
                            return

                        is_allowed = await GuardService.is_action_allowed(
                            actor_id=actor.id,
                            guild_id=guild.id,
                            permission=GuardPermission.EDIT_ROLES,
                        )

                        if not is_allowed:
                            try:
                                await after.edit(
                                    permissions=before.permissions,
                                    reason="Защита: несанкционированное изменение прав роли",
                                )
                            except discord.HTTPException:
                                pass

                            await GuardService.handle_infraction(
                                guild=guild,
                                actor_id=actor.id,
                                action_name="Редактирование прав ролей",
                                details=f"Изменены права роли @{after.name}",
                            )
                        break
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        guild = channel.guild
        if guild.id != CONFIG.guild_id:
            return
        now = datetime.now(timezone.utc)

        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.channel_create, limit=3):
                if entry.target and entry.target.id == channel.id:
                    delta = (now - entry.created_at).total_seconds()
                    if delta <= 7:
                        actor = entry.user
                        if not actor or self._is_owner_or_bot(guild, actor.id):
                            return

                        is_allowed = await GuardService.is_action_allowed(
                            actor_id=actor.id,
                            guild_id=guild.id,
                            permission=GuardPermission.CREATE_CHANNELS,
                        )

                        if not is_allowed:
                            try:
                                await channel.delete(reason="Защита: несанкционированное создание канала")
                            except discord.HTTPException:
                                pass

                            await GuardService.handle_infraction(
                                guild=guild,
                                actor_id=actor.id,
                                action_name="Создание каналов/категорий",
                                details=f"Создан канал #{channel.name}",
                            )
                        break
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        guild = channel.guild
        if guild.id != CONFIG.guild_id:
            return
        now = datetime.now(timezone.utc)

        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.channel_delete, limit=3):
                if entry.target and entry.target.id == channel.id:
                    delta = (now - entry.created_at).total_seconds()
                    if delta <= 7:
                        actor = entry.user
                        if not actor or self._is_owner_or_bot(guild, actor.id):
                            return

                        is_allowed = await GuardService.is_action_allowed(
                            actor_id=actor.id,
                            guild_id=guild.id,
                            permission=GuardPermission.DELETE_CHANNELS,
                        )

                        if not is_allowed:
                            await GuardService.handle_infraction(
                                guild=guild,
                                actor_id=actor.id,
                                action_name="Удаление каналов/категорий",
                                details=f"Удален канал #{channel.name}",
                            )
                        break
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel) -> None:
        guild = after.guild
        if guild.id != CONFIG.guild_id:
            return
        now = datetime.now(timezone.utc)

        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.channel_update, limit=3):
                if entry.target and entry.target.id == after.id:
                    delta = (now - entry.created_at).total_seconds()
                    if delta <= 7:
                        actor = entry.user
                        if not actor or self._is_owner_or_bot(guild, actor.id):
                            return

                        is_allowed = await GuardService.is_action_allowed(
                            actor_id=actor.id,
                            guild_id=guild.id,
                            permission=GuardPermission.EDIT_CHANNELS,
                        )

                        if not is_allowed:
                            await GuardService.handle_infraction(
                                guild=guild,
                                actor_id=actor.id,
                                action_name="Редактирование настроек канала",
                                details=f"Изменен канал #{after.name}",
                            )
                        break
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        if after.id != CONFIG.guild_id:
            return

        now = datetime.now(timezone.utc)
        try:
            async for entry in after.audit_logs(action=discord.AuditLogAction.guild_update, limit=3):
                delta = (now - entry.created_at).total_seconds()
                if delta <= 7:
                    actor = entry.user
                    if not actor or self._is_owner_or_bot(after, actor.id):
                        return

                    is_allowed = await GuardService.is_action_allowed(
                        actor_id=actor.id,
                        guild_id=after.id,
                        permission=GuardPermission.EDIT_SERVER,
                    )

                    if not is_allowed:
                        try:
                            await after.edit(name=before.name, reason="Защита: откат настроек сервера")
                        except discord.HTTPException:
                            pass

                        await GuardService.handle_infraction(
                            guild=after,
                            actor_id=actor.id,
                            action_name="Изменение параметров сервера",
                            details="Попытка изменить название или настройки сервера",
                        )
                    break
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel) -> None:
        guild = channel.guild
        if guild.id != CONFIG.guild_id:
            return

        now = datetime.now(timezone.utc)
        try:
            async for entry in guild.audit_logs(limit=3):
                if entry.action in (discord.AuditLogAction.webhook_create, discord.AuditLogAction.webhook_delete):
                    delta = (now - entry.created_at).total_seconds()
                    if delta <= 7:
                        actor = entry.user
                        if not actor or self._is_owner_or_bot(guild, actor.id):
                            return

                        is_allowed = await GuardService.is_action_allowed(
                            actor_id=actor.id,
                            guild_id=guild.id,
                            permission=GuardPermission.MANAGE_WEBHOOKS,
                        )

                        if not is_allowed:
                            await GuardService.handle_infraction(
                                guild=guild,
                                actor_id=actor.id,
                                action_name="Управление вебхуками",
                                details=f"Действие с вебхуками в канале #{channel.name}",
                            )
                        break
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """
        Защита: контроль добавления ботов на сервер.
        Если бот добавлен пользователем без права ADD_BOTS:
        - Добавленный бот кикается/банится;
        - Пользователю выдается страйк безопасности с возможной блокировкой.
        """
        if not member.bot:
            return

        guild = member.guild
        if guild.id != CONFIG.guild_id:
            return

        now = datetime.now(timezone.utc)
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.bot_add):
                if entry.target and entry.target.id == member.id:
                    delta = (now - entry.created_at).total_seconds()
                    if delta <= 15:
                        actor = entry.user
                        if not actor or self._is_owner_or_bot(guild, actor.id):
                            return

                        is_allowed = await GuardService.is_action_allowed(
                            actor_id=actor.id,
                            guild_id=guild.id,
                            permission=GuardPermission.ADD_BOTS,
                        )

                        if not is_allowed:
                            # 1. Изгоняем несанкционированного бота
                            try:
                                await member.kick(reason=f"Защита: несанкционированное добавление бота от {actor.name}")
                            except Exception:
                                try:
                                    await member.ban(reason=f"Защита: несанкционированное добавление бота от {actor.name}")
                                except Exception:
                                    pass

                            # 2. Наказываем пользователя, добавившего бота
                            await GuardService.handle_infraction(
                                guild=guild,
                                actor_id=actor.id,
                                action_name="Добавление ботов",
                                details=f"Попытка добавить бота {member.name} (`{member.id}`)",
                            )
                        break
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GuardCog(bot))
