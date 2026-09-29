from datetime import datetime, timezone
from typing import List, Optional

from kawaii_core.database.connection import db_manager
from kawaii_core.domain.enums import GuardPermission
from kawaii_core.domain.models import BlacklistRecord, SecurityStrikesRecord, UserGuardPermissions, WarnRecord


class StaffRepository:
    @staticmethod
    async def get_punishments_count(user_id: int) -> int:
        async with db_manager.get_connection() as db:
            async with db.execute("SELECT punishments_count FROM staff_stats WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return int(row["punishments_count"]) if row else 0

    @staticmethod
    async def increment_punishments(user_id: int, delta: int = 1) -> None:
        async with db_manager.get_connection() as db:
            await db.execute(
                """
                INSERT INTO staff_stats (user_id, punishments_count, total_actions, updated_at)
                VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    punishments_count = punishments_count + ?,
                    total_actions = total_actions + 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, delta, delta),
            )
            await db.commit()

    @staticmethod
    async def create_warn(
        guild_id: int,
        target_id: int,
        issuer_id: int,
        issuer_rank_weight: int,
        reason: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> int:
        async with db_manager.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO staff_warns (
                    guild_id, target_id, issuer_id, issuer_rank_weight, reason, created_at, expires_at, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    guild_id,
                    target_id,
                    issuer_id,
                    issuer_rank_weight,
                    reason,
                    created_at.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            await db.commit()
            return int(cursor.lastrowid)

    @staticmethod
    async def get_active_warns(guild_id: int, target_id: int) -> List[WarnRecord]:
        async with db_manager.get_connection() as db:
            async with db.execute(
                """
                SELECT id, guild_id, target_id, issuer_id, issuer_rank_weight, reason, created_at, expires_at, is_active
                FROM staff_warns
                WHERE guild_id = ? AND target_id = ? AND is_active = 1
                ORDER BY created_at DESC
                """,
                (guild_id, target_id),
            ) as cursor:
                rows = await cursor.fetchall()
                results: List[WarnRecord] = []
                for row in rows:
                    results.append(
                        WarnRecord(
                            id=row["id"],
                            guild_id=row["guild_id"],
                            target_id=row["target_id"],
                            issuer_id=row["issuer_id"],
                            issuer_rank_weight=row["issuer_rank_weight"],
                            reason=row["reason"],
                            created_at=datetime.fromisoformat(row["created_at"]),
                            expires_at=datetime.fromisoformat(row["expires_at"]),
                            is_active=bool(row["is_active"]),
                        )
                    )
                return results

    @staticmethod
    async def get_all_warns(guild_id: int, target_id: int, limit: int = 15) -> List[WarnRecord]:
        async with db_manager.get_connection() as db:
            async with db.execute(
                """
                SELECT id, guild_id, target_id, issuer_id, issuer_rank_weight, reason, created_at, expires_at, is_active
                FROM staff_warns
                WHERE guild_id = ? AND target_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (guild_id, target_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                results: List[WarnRecord] = []
                for row in rows:
                    results.append(
                        WarnRecord(
                            id=row["id"],
                            guild_id=row["guild_id"],
                            target_id=row["target_id"],
                            issuer_id=row["issuer_id"],
                            issuer_rank_weight=row["issuer_rank_weight"],
                            reason=row["reason"],
                            created_at=datetime.fromisoformat(row["created_at"]),
                            expires_at=datetime.fromisoformat(row["expires_at"]),
                            is_active=bool(row["is_active"]),
                        )
                    )
                return results

    @staticmethod
    async def deactivate_warn(warn_id: int) -> bool:
        async with db_manager.get_connection() as db:
            cursor = await db.execute(
                "UPDATE staff_warns SET is_active = 0 WHERE id = ?",
                (warn_id,),
            )
            await db.commit()
            return cursor.rowcount > 0

    @staticmethod
    async def deactivate_expired_warns() -> List[WarnRecord]:
        now_iso = datetime.now(timezone.utc).isoformat()
        async with db_manager.get_connection() as db:
            async with db.execute(
                """
                SELECT id, guild_id, target_id, issuer_id, issuer_rank_weight, reason, created_at, expires_at, is_active
                FROM staff_warns
                WHERE is_active = 1 AND expires_at <= ?
                """,
                (now_iso,),
            ) as cursor:
                rows = await cursor.fetchall()
                expired = [
                    WarnRecord(
                        id=row["id"],
                        guild_id=row["guild_id"],
                        target_id=row["target_id"],
                        issuer_id=row["issuer_id"],
                        issuer_rank_weight=row["issuer_rank_weight"],
                        reason=row["reason"],
                        created_at=datetime.fromisoformat(row["created_at"]),
                        expires_at=datetime.fromisoformat(row["expires_at"]),
                        is_active=False,
                    )
                    for row in rows
                ]

            if expired:
                expired_ids = [w.id for w in expired]
                placeholders = ",".join("?" for _ in expired_ids)
                await db.execute(
                    f"UPDATE staff_warns SET is_active = 0 WHERE id IN ({placeholders})",
                    expired_ids,
                )
                await db.commit()
            return expired

    @staticmethod
    async def add_to_blacklist(
        guild_id: int,
        target_id: int,
        issuer_id: int,
        issuer_rank_weight: int,
        issuer_rank_title: str,
        reason: str,
        created_at: datetime,
    ) -> int:
        async with db_manager.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO staff_blacklist (
                    guild_id, target_id, issuer_id, issuer_rank_weight, issuer_rank_title,
                    reason, created_at, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    guild_id,
                    target_id,
                    issuer_id,
                    issuer_rank_weight,
                    issuer_rank_title,
                    reason,
                    created_at.isoformat(),
                ),
            )
            await db.commit()
            return int(cursor.lastrowid)

    @staticmethod
    async def remove_from_blacklist(
        blacklist_id: int,
        unlisted_by: int,
        unlisted_at: datetime,
        unlisted_reason: Optional[str] = None,
    ) -> None:
        async with db_manager.get_connection() as db:
            await db.execute(
                """
                UPDATE staff_blacklist
                SET is_active = 0, unlisted_by = ?, unlisted_at = ?, unlisted_reason = ?
                WHERE id = ?
                """,
                (unlisted_by, unlisted_at.isoformat(), unlisted_reason, blacklist_id),
            )
            await db.commit()

    @staticmethod
    async def is_user_blacklisted(guild_id: int, target_id: int) -> bool:
        async with db_manager.get_connection() as db:
            async with db.execute(
                "SELECT 1 FROM staff_blacklist WHERE guild_id = ? AND target_id = ? AND is_active = 1 LIMIT 1",
                (guild_id, target_id),
            ) as cursor:
                return await cursor.fetchone() is not None

    @staticmethod
    async def get_active_blacklist(guild_id: int, target_id: int) -> Optional[BlacklistRecord]:
        async with db_manager.get_connection() as db:
            async with db.execute(
                """
                SELECT id, guild_id, target_id, issuer_id, issuer_rank_weight, issuer_rank_title,
                       reason, created_at, is_active, unlisted_by, unlisted_at, unlisted_reason
                FROM staff_blacklist
                WHERE guild_id = ? AND target_id = ? AND is_active = 1
                ORDER BY created_at DESC LIMIT 1
                """,
                (guild_id, target_id),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return BlacklistRecord(
                    id=row["id"],
                    guild_id=row["guild_id"],
                    target_id=row["target_id"],
                    issuer_id=row["issuer_id"],
                    issuer_rank_weight=row["issuer_rank_weight"],
                    issuer_rank_title=row["issuer_rank_title"],
                    reason=row["reason"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    is_active=bool(row["is_active"]),
                    unlisted_by=row["unlisted_by"],
                    unlisted_at=datetime.fromisoformat(row["unlisted_at"]) if row["unlisted_at"] else None,
                    unlisted_reason=row["unlisted_reason"] if "unlisted_reason" in row.keys() else None,
                )

    @staticmethod
    async def get_all_active_blacklist(guild_id: int) -> List[BlacklistRecord]:
        async with db_manager.get_connection() as db:
            async with db.execute(
                """
                SELECT id, guild_id, target_id, issuer_id, issuer_rank_weight, issuer_rank_title,
                       reason, created_at, is_active, unlisted_by, unlisted_at, unlisted_reason
                FROM staff_blacklist
                WHERE guild_id = ? AND is_active = 1
                ORDER BY created_at DESC
                """,
                (guild_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                results: List[BlacklistRecord] = []
                for row in rows:
                    results.append(
                        BlacklistRecord(
                            id=row["id"],
                            guild_id=row["guild_id"],
                            target_id=row["target_id"],
                            issuer_id=row["issuer_id"],
                            issuer_rank_weight=row["issuer_rank_weight"],
                            issuer_rank_title=row["issuer_rank_title"],
                            reason=row["reason"],
                            created_at=datetime.fromisoformat(row["created_at"]),
                            is_active=bool(row["is_active"]),
                            unlisted_by=row["unlisted_by"],
                            unlisted_at=datetime.fromisoformat(row["unlisted_at"]) if row["unlisted_at"] else None,
                            unlisted_reason=row["unlisted_reason"] if "unlisted_reason" in row.keys() else None,
                        )
                    )
                return results


class SecurityRepository:
    @staticmethod
    async def get_strikes(user_id: int, guild_id: int) -> SecurityStrikesRecord:
        async with db_manager.get_connection() as db:
            async with db.execute(
                "SELECT user_id, guild_id, strikes_count, last_action, updated_at FROM security_strikes WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return SecurityStrikesRecord(
                        user_id=row["user_id"],
                        guild_id=row["guild_id"],
                        strikes_count=int(row["strikes_count"]),
                        last_action=row["last_action"],
                        updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
                    )
                return SecurityStrikesRecord(user_id=user_id, guild_id=guild_id, strikes_count=0)

    @staticmethod
    async def increment_strike(user_id: int, guild_id: int, action_description: str) -> int:
        async with db_manager.get_connection() as db:
            await db.execute(
                """
                INSERT INTO security_strikes (user_id, guild_id, strikes_count, last_action, updated_at)
                VALUES (?, ?, 1, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    strikes_count = strikes_count + 1,
                    last_action = excluded.last_action,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, guild_id, action_description),
            )
            await db.commit()

            async with db.execute(
                "SELECT strikes_count FROM security_strikes WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id),
            ) as cursor:
                row = await cursor.fetchone()
                return int(row["strikes_count"]) if row else 1

    @staticmethod
    async def reset_strikes(user_id: int, guild_id: int) -> None:
        async with db_manager.get_connection() as db:
            await db.execute(
                "UPDATE security_strikes SET strikes_count = 0, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id),
            )
            await db.commit()

    @staticmethod
    async def get_permissions(user_id: int, guild_id: int) -> UserGuardPermissions:
        async with db_manager.get_connection() as db:
            async with db.execute(
                """
                SELECT manage_roles_pkm, edit_roles, create_roles, delete_roles,
                       ban_members, kick_members, timeout_members,
                       create_channels, edit_channels, delete_channels,
                       edit_server, manage_webhooks, add_bots
                FROM guard_permissions
                WHERE user_id = ? AND guild_id = ?
                """,
                (user_id, guild_id),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return UserGuardPermissions(
                        user_id=user_id,
                        guild_id=guild_id,
                        manage_roles_pkm=bool(row["manage_roles_pkm"]),
                        edit_roles=bool(row["edit_roles"]),
                        create_roles=bool(row["create_roles"]),
                        delete_roles=bool(row["delete_roles"]),
                        ban_members=bool(row["ban_members"]),
                        kick_members=bool(row["kick_members"]),
                        timeout_members=bool(row["timeout_members"]),
                        create_channels=bool(row["create_channels"]),
                        edit_channels=bool(row["edit_channels"]),
                        delete_channels=bool(row["delete_channels"]),
                        edit_server=bool(row["edit_server"]),
                        manage_webhooks=bool(row["manage_webhooks"]),
                        add_bots=bool(row["add_bots"]),
                    )
                return UserGuardPermissions(user_id=user_id, guild_id=guild_id)

    @staticmethod
    async def toggle_permission(user_id: int, guild_id: int, permission: GuardPermission) -> bool:
        current_perms = await SecurityRepository.get_permissions(user_id, guild_id)
        current_val = getattr(current_perms, permission.value, False)
        new_val = not current_val

        field_name = permission.value
        async with db_manager.get_connection() as db:
            await db.execute(
                f"""
                INSERT INTO guard_permissions (user_id, guild_id, {field_name})
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET
                    {field_name} = ?
                """,
                (user_id, guild_id, 1 if new_val else 0, 1 if new_val else 0),
            )
            await db.commit()
            return new_val


class RecruitmentRepository:
    @staticmethod
    async def create_application(
        guild_id: int,
        user_id: int,
        branch: str,
        name_age_tz: str,
        activity: str,
        discord_id_input: str = "",
        rules_score: str = "",
        experience: str = "",
        motivation: str = "",
        created_at: Optional[datetime] = None,
    ) -> int:
        now = created_at or datetime.now(timezone.utc)
        async with db_manager.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO staff_applications (
                    guild_id, user_id, discord_id_input, branch, status, created_at,
                    name_age_tz, activity, rules_score, experience, motivation
                ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    user_id,
                    discord_id_input,
                    branch,
                    now.isoformat(),
                    name_age_tz,
                    activity,
                    rules_score,
                    experience,
                    motivation,
                ),
            )
            await db.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    @staticmethod
    async def set_message_info(app_id: int, channel_id: int, message_id: int) -> None:
        async with db_manager.get_connection() as db:
            await db.execute(
                "UPDATE staff_applications SET channel_id = ?, message_id = ? WHERE id = ?",
                (channel_id, message_id, app_id),
            )
            await db.commit()

    @staticmethod
    async def get_application(app_id: int) -> Optional[dict]:
        async with db_manager.get_connection() as db:
            async with db.execute(
                "SELECT * FROM staff_applications WHERE id = ?",
                (app_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return dict(row)

    @staticmethod
    async def get_pending_application(user_id: int) -> Optional[dict]:
        async with db_manager.get_connection() as db:
            async with db.execute(
                "SELECT * FROM staff_applications WHERE user_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return dict(row)

    @staticmethod
    async def get_last_rejected_application(user_id: int) -> Optional[dict]:
        async with db_manager.get_connection() as db:
            async with db.execute(
                "SELECT * FROM staff_applications WHERE user_id = ? AND status = 'rejected' ORDER BY closed_at DESC LIMIT 1",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return dict(row)

    @staticmethod
    async def update_application_status(
        app_id: int,
        status: str,
        reviewer_id: int,
        closed_at: datetime,
    ) -> None:
        async with db_manager.get_connection() as db:
            await db.execute(
                """
                UPDATE staff_applications
                SET status = ?, reviewer_id = ?, closed_at = ?
                WHERE id = ?
                """,
                (status, reviewer_id, closed_at.isoformat(), app_id),
            )
            await db.commit()


class EventRepository:
    @staticmethod
    async def create_event(
        guild_id: int,
        title: str,
        description: str,
        event_timestamp: int,
        image_url: Optional[str],
        organizer_id: int,
        channel_id: int,
        target_role_id: Optional[int],
        voice_channel_id: Optional[int] = None,
        reminded_24h: int = 0,
        reminded_1h: int = 0,
        reminded_15m: int = 0,
        reminded_start: int = 0,
    ) -> int:
        async with db_manager.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO scheduled_events (
                    guild_id, title, description, event_timestamp, image_url,
                    organizer_id, channel_id, voice_channel_id, target_role_id, is_cancelled,
                    reminded_24h, reminded_1h, reminded_15m, reminded_start, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    guild_id,
                    title,
                    description,
                    event_timestamp,
                    image_url,
                    organizer_id,
                    channel_id,
                    voice_channel_id,
                    target_role_id,
                    reminded_24h,
                    reminded_1h,
                    reminded_15m,
                    reminded_start,
                ),
            )
            await db.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    @staticmethod
    async def get_event(event_id: int) -> Optional[dict]:
        async with db_manager.get_connection() as db:
            async with db.execute("SELECT * FROM scheduled_events WHERE id = ?", (event_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    @staticmethod
    async def get_active_events(guild_id: Optional[int] = None) -> List[dict]:
        now_ts = int(datetime.now(timezone.utc).timestamp())
        query = "SELECT * FROM scheduled_events WHERE is_cancelled = 0 AND event_timestamp >= ?"
        params: list = [now_ts]
        if guild_id is not None:
            query += " AND guild_id = ?"
            params.append(guild_id)
        query += " ORDER BY event_timestamp ASC"

        async with db_manager.get_connection() as db:
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    @staticmethod
    async def get_upcoming_events(guild_id: Optional[int] = None) -> List[dict]:
        """
        Возвращает неотмененные мероприятия, требующие отправки уведомления о начале.
        Выбирает события в пределах последних 2 часов (для надежной доставки) и будущие.
        """
        now_ts = int(datetime.now(timezone.utc).timestamp())
        # Ивенты не старше 2 часов назад, которые еще не были оповещены
        cutoff_ts = now_ts - 7200
        query = """
            SELECT * FROM scheduled_events
            WHERE is_cancelled = 0
              AND reminded_start = 0
              AND event_timestamp >= ?
        """
        params: list = [cutoff_ts]
        if guild_id is not None:
            query += " AND guild_id = ?"
            params.append(guild_id)
        query += " ORDER BY event_timestamp ASC"

        async with db_manager.get_connection() as db:
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    @staticmethod
    async def mark_reminded(event_id: int, reminder_type: str) -> None:
        col_map = {
            "24h": "reminded_24h",
            "1h": "reminded_1h",
            "15m": "reminded_15m",
            "start": "reminded_start",
        }
        col = col_map.get(reminder_type)
        if not col:
            return
        async with db_manager.get_connection() as db:
            await db.execute(f"UPDATE scheduled_events SET {col} = 1 WHERE id = ?", (event_id,))
            await db.commit()

    @staticmethod
    async def cancel_event(event_id: int) -> bool:
        async with db_manager.get_connection() as db:
            cursor = await db.execute(
                "UPDATE scheduled_events SET is_cancelled = 1 WHERE id = ? AND is_cancelled = 0",
                (event_id,),
            )
            await db.commit()
            return cursor.rowcount > 0


class RoleRepository:
    @staticmethod
    async def get_categories(guild_id: int) -> List[dict]:
        await RoleRepository.ensure_defaults(guild_id)
        async with db_manager.get_connection() as db:
            async with db.execute(
                "SELECT * FROM role_categories WHERE guild_id = ? ORDER BY position ASC, id ASC",
                (guild_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    @staticmethod
    async def get_category_by_name(guild_id: int, name: str) -> Optional[dict]:
        await RoleRepository.ensure_defaults(guild_id)
        async with db_manager.get_connection() as db:
            async with db.execute(
                "SELECT * FROM role_categories WHERE guild_id = ? AND LOWER(name) = LOWER(?)",
                (guild_id, name.strip()),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    @staticmethod
    async def get_category_by_id(category_id: int) -> Optional[dict]:
        async with db_manager.get_connection() as db:
            async with db.execute(
                "SELECT * FROM role_categories WHERE id = ?",
                (category_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    @staticmethod
    async def create_category(guild_id: int, name: str, emoji: str = "📁") -> int:
        await RoleRepository.ensure_defaults(guild_id)
        async with db_manager.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO role_categories (guild_id, name, emoji, position)
                VALUES (?, ?, ?, (SELECT COALESCE(MAX(position), 0) + 1 FROM role_categories WHERE guild_id = ?))
                """,
                (guild_id, name.strip(), emoji, guild_id),
            )
            await db.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    @staticmethod
    async def get_category_buttons(category_id: int) -> List[dict]:
        async with db_manager.get_connection() as db:
            async with db.execute(
                "SELECT * FROM role_category_buttons WHERE category_id = ? ORDER BY position ASC, id ASC",
                (category_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    @staticmethod
    async def add_button(category_id: int, role_id: int, label: str, emoji: Optional[str] = None) -> int:
        async with db_manager.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO role_category_buttons (category_id, role_id, label, emoji, position)
                VALUES (?, ?, ?, ?, (SELECT COALESCE(MAX(position), 0) + 1 FROM role_category_buttons WHERE category_id = ?))
                ON CONFLICT(category_id, role_id) DO UPDATE SET
                    label = excluded.label,
                    emoji = excluded.emoji
                """,
                (category_id, role_id, label.strip(), emoji, category_id),
            )
            await db.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    @staticmethod
    async def ensure_defaults(guild_id: int) -> None:
        """
        Инициализирует стандартные категории 'Игры' и 'Уведомления' с их ролями,
        если для сервера еще не создано ни одной категории в БД.
        """
        async with db_manager.get_connection() as db:
            async with db.execute("SELECT COUNT(*) AS cnt FROM role_categories WHERE guild_id = ?", (guild_id,)) as cursor:
                row = await cursor.fetchone()
                if row and row["cnt"] > 0:
                    return

            # Создаем стандартную категорию 'Игры'
            cursor_games = await db.execute(
                "INSERT INTO role_categories (guild_id, name, emoji, position) VALUES (?, 'Игры', '📁', 1)",
                (guild_id,),
            )
            games_id = cursor_games.lastrowid

            # Стандартные игровые роли из CONFIG
            default_game_buttons = [
                (games_id, 1554488379255558174, "CS 2", "🔫", 1),
                (games_id, 1554488482754330684, "Dota 2", "🛡️", 2),
                (games_id, 1554488473602359306, "GTA V", "🎮", 3),
                (games_id, 1554488562358165575, "Rust", "⚔️", 4),
                (games_id, 1554489141427970088, "Minecraft", "🟩", 5),
            ]
            for gid, rid, lbl, emj, pos in default_game_buttons:
                await db.execute(
                    "INSERT INTO role_category_buttons (category_id, role_id, label, emoji, position) VALUES (?, ?, ?, ?, ?)",
                    (gid, rid, lbl, emj, pos),
                )

            # Создаем стандартную категорию 'Уведомления'
            cursor_notifs = await db.execute(
                "INSERT INTO role_categories (guild_id, name, emoji, position) VALUES (?, 'Уведомления', '📁', 2)",
                (guild_id,),
            )
            notifs_id = cursor_notifs.lastrowid

            # Стандартные роли уведомлений из CONFIG
            default_notif_buttons = [
                (notifs_id, 1524931367673266380, "Ивенты", "🎉", 1),
                (notifs_id, 1553420613857710251, "Розыгрыши", "🎁", 2),
                (notifs_id, 1524931363982147774, "Новости", "📢", 3),
            ]
            for nid, rid, lbl, emj, pos in default_notif_buttons:
                await db.execute(
                    "INSERT INTO role_category_buttons (category_id, role_id, label, emoji, position) VALUES (?, ?, ?, ?, ?)",
                    (nid, rid, lbl, emj, pos),
                )

            await db.commit()


