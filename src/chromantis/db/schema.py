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

CREATE TABLE IF NOT EXISTS image_tags (
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    UNIQUE (image_id, tag_id)
);

CREATE TABLE IF NOT EXISTS authorized_chats (
    chat_id INTEGER PRIMARY KEY,
    username TEXT NULL,
    first_name TEXT NULL,
    authorized_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_chat_sessions (
    chat_id INTEGER PRIMARY KEY,
    session_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
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
"""
