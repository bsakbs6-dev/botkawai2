from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Final, Set

BASE_DIR: Path = Path(__file__).resolve().parent.parent
ASSETS_DIR: Path = BASE_DIR / "assets"

PROFILE_BANNER_PATH: Path = ASSETS_DIR / "profile_banner.jpg"
PERMISSIONS_BANNER_PATH: Path = ASSETS_DIR / "permissions_banner.jpg"
STAFF_BANNER_PATH: Path = ASSETS_DIR / "staff_banner.jpg"
BLACKLIST_BANNER_PATH: Path = ASSETS_DIR / "blacklist_banner.jpg"
RECRUITMENT_BANNER_PATH: Path = ASSETS_DIR / "staff_recruitment_banner.jpg"
DATABASE_PATH: Path = BASE_DIR / "kawaii_bot.sqlite3"


@dataclass(frozen=True)
class BranchRoleConfig:
    branch_role_id: int
    master_qualifier_role_id: int
    rank_1_role_id: int
    name: str


@dataclass(frozen=True)
class SystemConfig:
    bot_token: str = field(default_factory=lambda: os.getenv("DISCORD_BOT_TOKEN", ""))
    guild_id: int = 1513976150958014534
    base_staff_role_id: int = 1524932407768383548
    owner_role_id: int = 1518844002533773362
    staff_admin_primary_role_id: int = 1524932409827655680
    staff_admin_secondary_role_id: int = 1553620040929247322

    log_channel_id: int = 1553633570516377680
    recruitment_channel_id: int = 1554164199561760954
    quarantine_ban_role_id: int = 1553118613357990098
    default_events_channel_id: int = 1524945624280338524

    # Game Roles
    role_cs2_id: int = 1554488379255558174
    role_dota2_id: int = 1554488482754330684
    role_gtav_id: int = 1554488473602359306
    role_rust_id: int = 1554488562358165575
    role_minecraft_id: int = 1554489141427970088

    # Notification Roles
    role_notify_events_id: int = 1524931367673266380
    role_notify_giveaways_id: int = 1553420613857710251
    role_notify_news_id: int = 1524931363982147774

    # Branch Specific Configs
    moderation: BranchRoleConfig = BranchRoleConfig(
        branch_role_id=1518841677979193394,
        master_qualifier_role_id=1553619999447580682,
        rank_1_role_id=1553623659653107773,
        name="Модерация"
    )
    support: BranchRoleConfig = BranchRoleConfig(
        branch_role_id=1553620012412047422,
        master_qualifier_role_id=1518841669339054080,
        rank_1_role_id=1553623712152948836,
        name="Саппорты"
    )
    eventers: BranchRoleConfig = BranchRoleConfig(
        branch_role_id=1518925417313075301,
        master_qualifier_role_id=1553620026005913690,
        rank_1_role_id=1553623674173784174,
        name="Эвентеры"
    )

    # Common Hierarchy Ranks
    rank_2_master_id: int = 1553619882275242024
    rank_3_curator_id: int = 1553619751060635669
    rank_4_deputy_admin_id: int = 1553619773785641041
    rank_5_admin_id: int = 1553126065231110264

    # System parameters
    max_active_warns: int = 3
    warn_duration_days: int = 14
    max_security_strikes: int = 5
    primary_color: int = 0xF59EB2
    danger_color: int = 0xE04F5F
    success_color: int = 0x57F287

    @property
    def game_roles(self) -> list[dict]:
        return [
            {"id": self.role_cs2_id, "name": "CS 2", "emoji": "🔫"},
            {"id": self.role_dota2_id, "name": "Dota 2", "emoji": "🛡️"},
            {"id": self.role_gtav_id, "name": "GTA V", "emoji": "🎮"},
            {"id": self.role_rust_id, "name": "Rust", "emoji": "⚔️"},
            {"id": self.role_minecraft_id, "name": "Minecraft", "emoji": "🟩"},
        ]

    @property
    def notification_roles(self) -> list[dict]:
        return [
            {"id": self.role_notify_events_id, "name": "Ивенты", "emoji": "🎉"},
            {"id": self.role_notify_giveaways_id, "name": "Розыгрыши", "emoji": "🎁"},
            {"id": self.role_notify_news_id, "name": "Новости", "emoji": "📢"},
        ]

    @property
    def all_interactive_role_ids(self) -> Set[int]:
        return {r["id"] for r in self.game_roles} | {r["id"] for r in self.notification_roles}

    @property
    def all_branch_role_ids(self) -> Set[int]:
        return {
            self.moderation.branch_role_id,
            self.support.branch_role_id,
            self.eventers.branch_role_id,
        }

    @property
    def all_qualifier_role_ids(self) -> Set[int]:
        return {
            self.moderation.master_qualifier_role_id,
            self.support.master_qualifier_role_id,
            self.eventers.master_qualifier_role_id,
        }

    @property
    def all_rank_role_ids(self) -> Set[int]:
        return {
            self.moderation.rank_1_role_id,
            self.support.rank_1_role_id,
            self.eventers.rank_1_role_id,
            self.rank_2_master_id,
            self.rank_3_curator_id,
            self.rank_4_deputy_admin_id,
            self.rank_5_admin_id,
            self.staff_admin_primary_role_id,
            self.staff_admin_secondary_role_id,
            self.owner_role_id,
        }


CONFIG: Final[SystemConfig] = SystemConfig()
