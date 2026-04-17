from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from chromantis.db.schema import SCHEMA_SQL
from chromantis.parsing.path_parser import ParsedImageRecord


@dataclass(frozen=True)
class ScanSummary:
    folders_indexed: int
    images_indexed: int
    skipped_paths: int
    deleted_folders: int
    deleted_images: int


@dataclass(frozen=True)
class IndexStats:
    folders: int
    images: int
    tags: int


@dataclass(frozen=True)
class AuthorizedChat:
    chat_id: int
    username: str | None
    first_name: str | None
    authorized_at: str


class Repository:
    def __init__(self, sqlite_path: str):
        self.sqlite_path = sqlite_path

    def connect(self) -> sqlite3.Connection:
        Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.sqlite_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def init_schema(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA_SQL)

    @contextmanager
    def session(self):
        with self.connect() as connection:
            yield connection
            connection.commit()

    def begin_scan(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def upsert_image_record(
        self, connection: sqlite3.Connection, record: ParsedImageRecord, scan_seen_at: str
    ) -> tuple[int, int]:
        folder_id = self._upsert_folder(connection, record, scan_seen_at)
        image_id = self._upsert_image(connection, folder_id, record, scan_seen_at)
        self._replace_folder_tags(connection, folder_id, record.folder_tags)
        self._replace_image_tags(connection, image_id, record.image_tags)
        return folder_id, image_id

    def prune_stale(
        self, connection: sqlite3.Connection, ftp_root_path: str, scan_seen_at: str
    ) -> tuple[int, int]:
        stale_images = connection.execute(
            """
            SELECT COUNT(*)
            FROM images
            WHERE scan_seen_at != ?
              AND folder_id IN (
                  SELECT id FROM folders WHERE ftp_root_path = ?
              )
            """,
            (scan_seen_at, ftp_root_path),
        ).fetchone()[0]

        connection.execute(
            """
            DELETE FROM images
            WHERE scan_seen_at != ?
              AND folder_id IN (
                  SELECT id FROM folders WHERE ftp_root_path = ?
              )
            """,
            (scan_seen_at, ftp_root_path),
        )

        stale_folders = connection.execute(
            """
            SELECT COUNT(*)
            FROM folders
            WHERE ftp_root_path = ? AND scan_seen_at != ?
            """,
            (ftp_root_path, scan_seen_at),
        ).fetchone()[0]
        connection.execute(
            """
            DELETE FROM folders
            WHERE ftp_root_path = ? AND scan_seen_at != ?
            """,
            (ftp_root_path, scan_seen_at),
        )
        return stale_folders, stale_images

    def list_years(self) -> list[int]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT DISTINCT year FROM folders ORDER BY year"
            ).fetchall()
        return [row["year"] for row in rows]

    def get_index_stats(self) -> IndexStats:
        with self.connect() as connection:
            folders = connection.execute("SELECT COUNT(*) FROM folders").fetchone()[0]
            images = connection.execute("SELECT COUNT(*) FROM images").fetchone()[0]
            tags = connection.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
        return IndexStats(folders=folders, images=images, tags=tags)

    def is_chat_authorized(self, chat_id: int) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM authorized_chats WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        return row is not None

    def authorize_chat(
        self, chat_id: int, username: str | None = None, first_name: str | None = None
    ) -> None:
        authorized_at = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO authorized_chats (chat_id, username, first_name, authorized_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    authorized_at = excluded.authorized_at
                """,
                (chat_id, username, first_name, authorized_at),
            )
            connection.commit()

    def revoke_chat(self, chat_id: int) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM authorized_chats WHERE chat_id = ?",
                (chat_id,),
            )
            connection.commit()

    def list_authorized_chats(self) -> list[AuthorizedChat]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT chat_id, username, first_name, authorized_at
                FROM authorized_chats
                ORDER BY authorized_at ASC
                """
            ).fetchall()
        return [
            AuthorizedChat(
                chat_id=row["chat_id"],
                username=row["username"],
                first_name=row["first_name"],
                authorized_at=row["authorized_at"],
            )
            for row in rows
        ]

    def get_chat_session(self, chat_id: int) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT session_json FROM bot_chat_sessions WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        return None if row is None else str(row["session_json"])

    def save_chat_session(self, chat_id: int, session_json: str) -> None:
        updated_at = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO bot_chat_sessions (chat_id, session_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    session_json = excluded.session_json,
                    updated_at = excluded.updated_at
                """,
                (chat_id, session_json, updated_at),
            )
            connection.commit()

    def clear_chat_session(self, chat_id: int) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM bot_chat_sessions WHERE chat_id = ?",
                (chat_id,),
            )
            connection.commit()

    def _upsert_folder(
        self, connection: sqlite3.Connection, record: ParsedImageRecord, scan_seen_at: str
    ) -> int:
        existing = connection.execute(
            "SELECT id FROM folders WHERE folder_path = ?",
            (record.folder_path,),
        ).fetchone()
        if existing:
            connection.execute(
                """
                UPDATE folders
                SET ftp_root_path = ?, year = ?, folder_name_raw = ?, folder_slug = ?,
                    title = ?, event_date = ?, scan_seen_at = ?
                WHERE id = ?
                """,
                (
                    record.ftp_root_path,
                    record.year,
                    record.folder_name_raw,
                    record.folder_slug,
                    record.title,
                    record.event_date,
                    scan_seen_at,
                    existing["id"],
                ),
            )
            return int(existing["id"])

        cursor = connection.execute(
            """
            INSERT INTO folders (
                folder_path, ftp_root_path, year, folder_name_raw, folder_slug,
                title, event_date, scan_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.folder_path,
                record.ftp_root_path,
                record.year,
                record.folder_name_raw,
                record.folder_slug,
                record.title,
                record.event_date,
                scan_seen_at,
            ),
        )
        return int(cursor.lastrowid)

    def _upsert_image(
        self,
        connection: sqlite3.Connection,
        folder_id: int,
        record: ParsedImageRecord,
        scan_seen_at: str,
    ) -> int:
        existing = connection.execute(
            "SELECT id FROM images WHERE file_path = ?",
            (record.file_path,),
        ).fetchone()
        if existing:
            connection.execute(
                """
                UPDATE images
                SET folder_id = ?, filename = ?, extension = ?,
                    ftp_modified_at = ?, file_size = ?, scan_seen_at = ?
                WHERE id = ?
                """,
                (
                    folder_id,
                    record.filename,
                    record.extension,
                    record.ftp_modified_at,
                    record.file_size,
                    scan_seen_at,
                    existing["id"],
                ),
            )
            return int(existing["id"])

        cursor = connection.execute(
            """
            INSERT INTO images (
                folder_id, file_path, filename, extension,
                ftp_modified_at, file_size, scan_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                folder_id,
                record.file_path,
                record.filename,
                record.extension,
                record.ftp_modified_at,
                record.file_size,
                scan_seen_at,
            ),
        )
        return int(cursor.lastrowid)

    def _replace_folder_tags(
        self, connection: sqlite3.Connection, folder_id: int, tags: tuple[tuple[str, str], ...]
    ) -> None:
        connection.execute("DELETE FROM folder_tags WHERE folder_id = ?", (folder_id,))
        for tag_name, source in tags:
            tag_id = self._upsert_tag(connection, tag_name, source)
            connection.execute(
                "INSERT OR IGNORE INTO folder_tags (folder_id, tag_id) VALUES (?, ?)",
                (folder_id, tag_id),
            )

    def _replace_image_tags(
        self, connection: sqlite3.Connection, image_id: int, tags: tuple[tuple[str, str], ...]
    ) -> None:
        connection.execute("DELETE FROM image_tags WHERE image_id = ?", (image_id,))
        for tag_name, source in tags:
            tag_id = self._upsert_tag(connection, tag_name, source)
            connection.execute(
                "INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)",
                (image_id, tag_id),
            )

    def _upsert_tag(self, connection: sqlite3.Connection, tag_name: str, source: str) -> int:
        existing = connection.execute(
            "SELECT id FROM tags WHERE tag = ?",
            (tag_name,),
        ).fetchone()
        if existing:
            connection.execute(
                "UPDATE tags SET source = ? WHERE id = ?",
                (source, existing["id"]),
            )
            return int(existing["id"])

        cursor = connection.execute(
            "INSERT INTO tags (tag, source) VALUES (?, ?)",
            (tag_name, source),
        )
        return int(cursor.lastrowid)
