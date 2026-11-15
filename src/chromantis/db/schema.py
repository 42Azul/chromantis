from __future__ import annotations

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS folders (
    id INTEGER PRIMARY KEY,
    folder_path TEXT NOT NULL UNIQUE,
    ftp_root_path TEXT NOT NULL,
    year INTEGER NOT NULL,
    folder_name_raw TEXT NOT NULL,
    folder_slug TEXT NOT NULL,
    title TEXT NOT NULL,
    event_date TEXT NULL,
    scan_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY,
    folder_id INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    extension TEXT NOT NULL,
    ftp_modified_at TEXT NULL,
    file_size INTEGER NULL,
    scan_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    summary_json TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS image_enrichment (
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    version TEXT NOT NULL,
    source_root TEXT NOT NULL,
    source_modified_at TEXT,
    source_size INTEGER,
    caption TEXT NOT NULL,
    ocr_text TEXT NOT NULL,
    object_tags_json TEXT NOT NULL,
    searchable_text TEXT NOT NULL,
    attempted_at TEXT NOT NULL,
    error TEXT,
    PRIMARY KEY (image_id, model, version)
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    tag TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS folder_tags (
    folder_id INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    UNIQUE (folder_id, tag_id)
);

CREATE TABLE IF NOT EXISTS album_reviews (
    folder_id INTEGER PRIMARY KEY REFERENCES folders(id) ON DELETE CASCADE,
    reviewed_name TEXT,
    revision INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS album_tag_decisions (
    folder_id INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
    origin TEXT NOT NULL CHECK (origin IN ('name', 'manual')),
    label TEXT NOT NULL,
    tag TEXT,
    evidence TEXT,
    PRIMARY KEY (folder_id, origin, label)
);

CREATE TABLE IF NOT EXISTS image_tags (
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    UNIQUE (image_id, tag_id)
);

CREATE TABLE IF NOT EXISTS authorized_chats (
    chat_id INTEGER PRIMARY KEY,
    username TEXT NULL,
    first_name TEXT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    authorized_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_chat_sessions (
    chat_id INTEGER PRIMARY KEY,
    session_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_browse_sessions (
    chat_id INTEGER PRIMARY KEY,
    session_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS saved_searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('images', 'random', 'folders')),
    query TEXT NOT NULL,
    result_count INTEGER NOT NULL,
    searched_at TEXT NOT NULL,
    pinned INTEGER NOT NULL DEFAULT 0,
    UNIQUE (chat_id, kind, query, result_count)
);

CREATE TABLE IF NOT EXISTS chat_preferences (
    chat_id INTEGER PRIMARY KEY,
    language TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS person_aliases (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    alias_normalized TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS folder_people (
    folder_id INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    UNIQUE (folder_id, person_id)
);

CREATE TABLE IF NOT EXISTS invite_codes (
    code TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    created_by_chat_id INTEGER NULL,
    max_uses INTEGER NOT NULL DEFAULT 1,
    used_count INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT NULL,
    revoked_at TEXT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY,
    actor_chat_id INTEGER NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_folders_year ON folders(year);
CREATE INDEX IF NOT EXISTS idx_folders_slug ON folders(folder_slug);
CREATE INDEX IF NOT EXISTS idx_folders_event_date ON folders(event_date);
CREATE INDEX IF NOT EXISTS idx_folders_root ON folders(ftp_root_path);
CREATE INDEX IF NOT EXISTS idx_images_folder_id ON images(folder_id);
CREATE INDEX IF NOT EXISTS idx_images_filename ON images(filename);
CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag);
CREATE INDEX IF NOT EXISTS idx_authorized_chats_authorized_at ON authorized_chats(authorized_at);
CREATE INDEX IF NOT EXISTS idx_bot_chat_sessions_updated_at ON bot_chat_sessions(updated_at);
CREATE INDEX IF NOT EXISTS idx_saved_searches_recent ON saved_searches(chat_id, searched_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_preferences_language ON chat_preferences(language);
CREATE INDEX IF NOT EXISTS idx_people_normalized_name ON people(normalized_name);
CREATE INDEX IF NOT EXISTS idx_person_aliases_person_id ON person_aliases(person_id);
CREATE INDEX IF NOT EXISTS idx_person_aliases_normalized ON person_aliases(alias_normalized);
CREATE INDEX IF NOT EXISTS idx_folder_people_person_id ON folder_people(person_id);
CREATE INDEX IF NOT EXISTS idx_invite_codes_role ON invite_codes(role);
CREATE INDEX IF NOT EXISTS idx_invite_codes_expires_at ON invite_codes(expires_at);
CREATE INDEX IF NOT EXISTS idx_audit_events_action ON audit_events(action);
CREATE INDEX IF NOT EXISTS idx_audit_events_created_at ON audit_events(created_at);
"""
