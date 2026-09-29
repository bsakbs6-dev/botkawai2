CREATE TABLE IF NOT EXISTS staff_stats (
    user_id INTEGER PRIMARY KEY,
    punishments_count INTEGER NOT NULL DEFAULT 0,
    total_actions INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS staff_warns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    issuer_id INTEGER NOT NULL,
    issuer_rank_weight INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_staff_warns_target ON staff_warns(target_id, is_active);
CREATE INDEX IF NOT EXISTS idx_staff_warns_expiry ON staff_warns(expires_at, is_active);

CREATE TABLE IF NOT EXISTS security_strikes (
    user_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    strikes_count INTEGER NOT NULL DEFAULT 0,
    last_action TEXT,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS guard_permissions (
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    manage_roles_pkm INTEGER NOT NULL DEFAULT 0,
    edit_roles INTEGER NOT NULL DEFAULT 0,
    create_roles INTEGER NOT NULL DEFAULT 0,
    delete_roles INTEGER NOT NULL DEFAULT 0,
    ban_members INTEGER NOT NULL DEFAULT 0,
    kick_members INTEGER NOT NULL DEFAULT 0,
    timeout_members INTEGER NOT NULL DEFAULT 0,
    create_channels INTEGER NOT NULL DEFAULT 0,
    edit_channels INTEGER NOT NULL DEFAULT 0,
    delete_channels INTEGER NOT NULL DEFAULT 0,
    edit_server INTEGER NOT NULL DEFAULT 0,
    manage_webhooks INTEGER NOT NULL DEFAULT 0,
    add_bots INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(user_id, guild_id)
);

CREATE TABLE IF NOT EXISTS staff_blacklist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    issuer_id INTEGER NOT NULL,
    issuer_rank_weight INTEGER NOT NULL,
    issuer_rank_title TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    unlisted_by INTEGER,
    unlisted_at TIMESTAMP,
    unlisted_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_staff_blacklist_target ON staff_blacklist(target_id, is_active);
CREATE INDEX IF NOT EXISTS idx_staff_blacklist_guild ON staff_blacklist(guild_id, is_active);

CREATE TABLE IF NOT EXISTS staff_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    discord_id_input TEXT,
    branch TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL,
    closed_at TIMESTAMP,
    reviewer_id INTEGER,
    channel_id INTEGER,
    message_id INTEGER,
    name_age_tz TEXT NOT NULL,
    activity TEXT NOT NULL,
    rules_score TEXT,
    experience TEXT NOT NULL,
    motivation TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_staff_apps_user ON staff_applications(user_id, status);
CREATE INDEX IF NOT EXISTS idx_staff_apps_status ON staff_applications(status);

CREATE TABLE IF NOT EXISTS scheduled_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    event_timestamp INTEGER NOT NULL,
    image_url TEXT,
    organizer_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    voice_channel_id INTEGER,
    target_role_id INTEGER,
    is_cancelled INTEGER NOT NULL DEFAULT 0,
    reminded_24h INTEGER NOT NULL DEFAULT 0,
    reminded_1h INTEGER NOT NULL DEFAULT 0,
    reminded_15m INTEGER NOT NULL DEFAULT 0,
    reminded_start INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_events_time ON scheduled_events(event_timestamp, is_cancelled, reminded_start);

CREATE TABLE IF NOT EXISTS role_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    emoji TEXT DEFAULT '📁',
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(guild_id, name)
);

CREATE TABLE IF NOT EXISTS role_category_buttons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    emoji TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(category_id) REFERENCES role_categories(id) ON DELETE CASCADE,
    UNIQUE(category_id, role_id)
);

CREATE INDEX IF NOT EXISTS idx_role_cat_guild ON role_categories(guild_id);
CREATE INDEX IF NOT EXISTS idx_role_btn_cat ON role_category_buttons(category_id);

