from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator
import aiosqlite

from kawaii_core.config import DATABASE_PATH

SCHEMA_PATH: Path = Path(__file__).resolve().parent / "schema.sql"


class DatabaseManager:
    def __init__(self, db_path: Path = DATABASE_PATH):
        self._db_path = db_path

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute("PRAGMA journal_mode = WAL;")
            yield db

    async def initialize(self) -> None:
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        async with self.get_connection() as db:
            await db.executescript(schema_sql)

            # Auto-migrate any missing columns in guard_permissions
            async with db.execute("PRAGMA table_info(guard_permissions)") as cursor:
                existing_cols = {row["name"] for row in await cursor.fetchall()}

            new_columns = [
                ("create_roles", "INTEGER NOT NULL DEFAULT 0"),
                ("delete_roles", "INTEGER NOT NULL DEFAULT 0"),
                ("ban_members", "INTEGER NOT NULL DEFAULT 0"),
                ("kick_members", "INTEGER NOT NULL DEFAULT 0"),
                ("timeout_members", "INTEGER NOT NULL DEFAULT 0"),
                ("edit_server", "INTEGER NOT NULL DEFAULT 0"),
                ("manage_webhooks", "INTEGER NOT NULL DEFAULT 0"),
                ("add_bots", "INTEGER NOT NULL DEFAULT 0"),
            ]
            for col_name, col_type in new_columns:
                if col_name not in existing_cols:
                    await db.execute(f"ALTER TABLE guard_permissions ADD COLUMN {col_name} {col_type};")

            # Auto-migrate any missing columns in staff_blacklist
            async with db.execute("PRAGMA table_info(staff_blacklist)") as cursor:
                bl_cols = {row["name"] for row in await cursor.fetchall()}
            if "unlisted_reason" not in bl_cols:
                await db.execute("ALTER TABLE staff_blacklist ADD COLUMN unlisted_reason TEXT;")

            # Auto-migrate any missing columns in scheduled_events
            async with db.execute("PRAGMA table_info(scheduled_events)") as cursor:
                ev_cols = {row["name"] for row in await cursor.fetchall()}
            if "voice_channel_id" not in ev_cols:
                await db.execute("ALTER TABLE scheduled_events ADD COLUMN voice_channel_id INTEGER;")
            if "reminded_start" not in ev_cols:
                await db.execute("ALTER TABLE scheduled_events ADD COLUMN reminded_start INTEGER NOT NULL DEFAULT 0;")

            await db.commit()


db_manager = DatabaseManager()
