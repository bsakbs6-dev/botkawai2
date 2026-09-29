from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from kawaii_core.domain.enums import BranchType, PositionRank


@dataclass(slots=True)
class BlacklistRecord:
    id: int
    guild_id: int
    target_id: int
    issuer_id: int
    issuer_rank_weight: int
    issuer_rank_title: str
    reason: str
    created_at: datetime
    is_active: bool = True
    unlisted_by: Optional[int] = None
    unlisted_at: Optional[datetime] = None
    unlisted_reason: Optional[str] = None


@dataclass(slots=True)
class StaffProfile:
    user_id: int
    guild_id: int
    is_staff: bool
    branch: BranchType
    rank: PositionRank
    position_title: str
    active_warns: int = 0
    total_punishments: int = 0
    raw_role_ids: set[int] = field(default_factory=set)
    is_blacklisted: bool = False
    blacklist_record: Optional[BlacklistRecord] = None

    @property
    def can_warn(self) -> bool:
        return self.rank >= PositionRank.MASTER

    @property
    def is_supreme(self) -> bool:
        return self.rank == PositionRank.OWNER


@dataclass(slots=True)
class WarnRecord:
    id: int
    guild_id: int
    target_id: int
    issuer_id: int
    issuer_rank_weight: int
    reason: str
    created_at: datetime
    expires_at: datetime
    is_active: bool = True


@dataclass(slots=True)
class SecurityStrikesRecord:
    user_id: int
    guild_id: int
    strikes_count: int
    last_action: Optional[str] = None
    updated_at: Optional[datetime] = None


@dataclass(slots=True)
class UserGuardPermissions:
    user_id: int
    guild_id: int
    manage_roles_pkm: bool = False
    edit_roles: bool = False
    create_roles: bool = False
    delete_roles: bool = False
    ban_members: bool = False
    kick_members: bool = False
    timeout_members: bool = False
    create_channels: bool = False
    edit_channels: bool = False
    delete_channels: bool = False
    edit_server: bool = False
    manage_webhooks: bool = False
    add_bots: bool = False
