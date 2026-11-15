from __future__ import annotations
import json
import secrets
import sqlite3
from contextlib import contextmanager, nullcontext
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from chromantis.db.schema import SCHEMA_SQL
from chromantis.parsing.path_parser import ParsedImageRecord, normalize_text


@dataclass(frozen=True)
class ScanSummary:
    folders_indexed: int
    images_indexed: int
    skipped_paths: int
    deleted_folders: int
    deleted_images: int
    unchanged_images: int = 0


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
    role: str
    authorized_at: str


@dataclass(frozen=True)
class SavedSearch:
    id: int
    kind: str
    query: str
    count: int
    searched_at: str
    pinned: bool


@dataclass(frozen=True)
class ChatPreferences:
    chat_id: int
    language: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class InviteCode:
    code: str
    role: str
    created_by_chat_id: int | None
    max_uses: int
    used_count: int
    expires_at: str | None
    revoked_at: str | None
    created_at: str


@dataclass(frozen=True)
class AuditEvent:
    id: int
    actor_chat_id: int | None
    action: str
    target_type: str
    target_id: str
    details_json: str
    created_at: str


@dataclass(frozen=True)
class YearSummary:
    year: int
    folders: int
    images: int


@dataclass(frozen=True)
class PersonSummary:
    id: int
    display_name: str
    aliases_count: int
    folder_count: int


@dataclass(frozen=True)
class PersonDetail:
    id: int
    display_name: str
    aliases: tuple[str, ...]
    folder_paths: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedPerson:
    id: int
    display_name: str
    search_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class EnrichmentCandidate:
    image_id: int
    path: str
    source_root: str
    modified_at: str | None
    size: int | None


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
            self._migrate_schema(connection)
            connection.commit()

    @contextmanager
    def session(self):
        with self.connect() as connection:
            yield connection
            connection.commit()

    def _existing_or_session(self, connection: sqlite3.Connection | None):
        return nullcontext(connection) if connection is not None else self.session()

    @contextmanager
    def write_transaction(self):
        with self.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            yield connection

    def begin_scan(self, incremental: bool) -> tuple[int, str]:
        now = datetime.now(timezone.utc).isoformat()
        with self.session() as connection:
            cursor = connection.execute(
                "INSERT INTO sync_runs (mode, status, started_at) VALUES (?, 'running', ?)",
                ("incremental" if incremental else "full", now),
            )
            return int(cursor.lastrowid), now

    def scan_is_superseded(self, connection: sqlite3.Connection, scan_id: int) -> bool:
        return connection.execute(
            "SELECT 1 FROM sync_runs WHERE id > ? AND status = 'succeeded' LIMIT 1", (scan_id,)
        ).fetchone() is not None

    def finish_scan(
        self, scan_id: int, status: str, summary: ScanSummary | None = None,
        error: str | None = None, *, connection: sqlite3.Connection | None = None,
    ) -> None:
        finished_at = datetime.now(timezone.utc).isoformat()
        with self._existing_or_session(connection) as connection:
            connection.execute(
                """
                UPDATE sync_runs SET status = ?, finished_at = ?, summary_json = ?, error = ?
                WHERE id = ?
                """,
                (status, finished_at, json.dumps(asdict(summary)) if summary else None, error, scan_id),
            )

    def list_sync_runs(self, limit: int) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM sync_runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {
                "id": row["id"], "mode": row["mode"], "status": row["status"],
                "started_at": row["started_at"], "finished_at": row["finished_at"],
                "summary": json.loads(row["summary_json"]) if row["summary_json"] else None,
                "error": row["error"],
            }
            for row in rows
        ]

    def indexed_image_metadata(
        self, connection: sqlite3.Connection
    ) -> dict[str, tuple[str, int | None, str | None]]:
        rows = connection.execute(
            """
            SELECT i.file_path, f.ftp_root_path, i.file_size, i.ftp_modified_at
            FROM images i JOIN folders f ON f.id = i.folder_id
            """
        )
        return {row[0]: (row[1], row[2], row[3]) for row in rows}

    def delete_missing_images(
        self, connection: sqlite3.Connection, paths: set[str]
    ) -> tuple[int, int]:
        images = connection.executemany(
            "DELETE FROM images WHERE file_path = ?", ((path,) for path in paths)
        ).rowcount
        folders = connection.execute(
            "DELETE FROM folders WHERE NOT EXISTS (SELECT 1 FROM images WHERE folder_id = folders.id)"
        ).rowcount
        return folders, images

    def upsert_image_record(
        self, connection: sqlite3.Connection, record: ParsedImageRecord, scan_seen_at: str
    ) -> tuple[int, int]:
        folder_id = self._upsert_folder(connection, record, scan_seen_at)
        image_id = self._upsert_image(connection, folder_id, record, scan_seen_at)
        self._replace_folder_tags(connection, folder_id, record.folder_tags)
        self._replace_image_tags(connection, image_id, record.image_tags)
        return folder_id, image_id

    def list_years(self) -> list[int]:
        return [summary.year for summary in self.list_year_summaries()]

    def list_year_summaries(
        self, year_from: int | None = None, year_to: int | None = None
    ) -> list[YearSummary]:
        with self.connect() as connection:
            filters: list[str] = []
            params: list[object] = []
            if year_from is not None:
                filters.append("f.year >= ?")
                params.append(year_from)
            if year_to is not None:
                filters.append("f.year <= ?")
                params.append(year_to)
            where_clause = ""
            if filters:
                where_clause = "WHERE " + " AND ".join(filters)
            rows = connection.execute(
                f"""
                SELECT f.year,
                       COUNT(DISTINCT f.id) AS folders,
                       COUNT(DISTINCT i.id) AS images
                FROM album_metadata f
                LEFT JOIN images i ON i.folder_id = f.id
                {where_clause}
                GROUP BY f.year
                ORDER BY f.year
                """,
                params,
            ).fetchall()
        return [
            YearSummary(
                year=row["year"],
                folders=row["folders"],
                images=row["images"],
            )
            for row in rows
        ]

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

    def get_authorized_chat(
        self,
        chat_id: int,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> AuthorizedChat | None:
        with self._existing_or_session(connection) as connection:
            row = connection.execute(
                """
                SELECT chat_id, username, first_name, role, authorized_at
                FROM authorized_chats
                WHERE chat_id = ?
                """,
                (chat_id,),
            ).fetchone()
        if row is None:
            return None
        return AuthorizedChat(
            chat_id=row["chat_id"],
            username=row["username"],
            first_name=row["first_name"],
            role=row["role"],
            authorized_at=row["authorized_at"],
        )

    def get_chat_role(self, chat_id: int) -> str | None:
        chat = self.get_authorized_chat(chat_id)
        return None if chat is None else chat.role

    def get_chat_preferences(self, chat_id: int) -> ChatPreferences | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT chat_id, language, created_at, updated_at
                FROM chat_preferences
                WHERE chat_id = ?
                """,
                (chat_id,),
            ).fetchone()
        if row is None:
            return None
        return ChatPreferences(
            chat_id=row["chat_id"],
            language=row["language"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_chat_language(self, chat_id: int) -> str | None:
        preferences = self.get_chat_preferences(chat_id)
        return None if preferences is None else preferences.language

    def set_chat_language(
        self,
        chat_id: int,
        language: str,
        actor_chat_id: int | None = None,
    ) -> ChatPreferences:
        if language not in {"en", "es"}:
            raise ValueError("Language must be en or es.")
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            existing = connection.execute(
                """
                SELECT created_at
                FROM chat_preferences
                WHERE chat_id = ?
                """,
                (chat_id,),
            ).fetchone()
            created_at = now if existing is None else str(existing["created_at"])
            connection.execute(
                """
                INSERT INTO chat_preferences (chat_id, language, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    language = excluded.language,
                    updated_at = excluded.updated_at
                """,
                (chat_id, language, created_at, now),
            )
            self._record_audit(
                connection,
                action="set_chat_language",
                target_type="chat_preferences",
                target_id=str(chat_id),
                actor_chat_id=actor_chat_id,
                details={"language": language},
            )
            connection.commit()
        return ChatPreferences(
            chat_id=chat_id,
            language=language,
            created_at=created_at,
            updated_at=now,
        )

    def authorize_chat(
        self,
        chat_id: int,
        username: str | None = None,
        first_name: str | None = None,
        role: str = "viewer",
    ) -> None:
        if role not in {"viewer", "admin", "owner"}:
            raise ValueError("Chat role must be viewer, admin, or owner.")
        authorized_at = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO authorized_chats (chat_id, username, first_name, role, authorized_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    role = excluded.role,
                    authorized_at = excluded.authorized_at
                """,
                (chat_id, username, first_name, role, authorized_at),
            )
            self._record_audit(
                connection,
                action="authorize_chat",
                target_type="chat",
                target_id=str(chat_id),
                actor_chat_id=chat_id,
                details={"role": role, "username": username, "first_name": first_name},
            )
            connection.commit()

    def set_chat_role(
        self,
        chat_id: int,
        role: str,
        actor_chat_id: int | None = None,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> AuthorizedChat:
        if role not in {"viewer", "admin", "owner"}:
            raise ValueError("Chat role must be viewer, admin, or owner.")
        with self._existing_or_session(connection) as connection:
            row = connection.execute(
                """
                SELECT chat_id, username, first_name, authorized_at
                FROM authorized_chats
                WHERE chat_id = ?
                """,
                (chat_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Chat is not dynamically authorized.")
            connection.execute(
                """
                UPDATE authorized_chats
                SET role = ?
                WHERE chat_id = ?
                """,
                (role, chat_id),
            )
            self._record_audit(
                connection,
                action="set_chat_role",
                target_type="chat",
                target_id=str(chat_id),
                actor_chat_id=actor_chat_id,
                details={"role": role},
            )
        return AuthorizedChat(
            chat_id=row["chat_id"],
            username=row["username"],
            first_name=row["first_name"],
            role=role,
            authorized_at=row["authorized_at"],
        )

    def revoke_chat_access(
        self,
        chat_id: int,
        actor_chat_id: int | None = None,
        reason: str = "admin_revoke",
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        with self._existing_or_session(connection) as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM authorized_chats
                WHERE chat_id = ?
                """,
                (chat_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Chat is not dynamically authorized.")
            connection.execute(
                "DELETE FROM authorized_chats WHERE chat_id = ?",
                (chat_id,),
            )
            connection.execute("DELETE FROM api_browse_sessions WHERE chat_id = ?", (chat_id,))
            connection.execute("DELETE FROM saved_searches WHERE chat_id = ?", (chat_id,))
            self._record_audit(
                connection,
                action="revoke_chat_access",
                target_type="chat",
                target_id=str(chat_id),
                actor_chat_id=actor_chat_id,
                details={"reason": reason},
            )

    def revoke_chat(self, chat_id: int) -> None:
        self.revoke_chat_access(
            chat_id=chat_id,
            actor_chat_id=chat_id,
            reason="self_logout",
        )

    def list_authorized_chats(self) -> list[AuthorizedChat]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT chat_id, username, first_name, role, authorized_at
                FROM authorized_chats
                ORDER BY authorized_at ASC
                """
            ).fetchall()
        return [
            AuthorizedChat(
                chat_id=row["chat_id"],
                username=row["username"],
                first_name=row["first_name"],
                role=row["role"],
                authorized_at=row["authorized_at"],
            )
            for row in rows
        ]

    def create_invite(
        self,
        role: str,
        created_by_chat_id: int | None,
        ttl_days: int = 7,
        max_uses: int = 1,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> InviteCode:
        if role not in {"viewer", "admin"}:
            raise ValueError("Invite role must be viewer or admin.")
        if ttl_days < 1:
            raise ValueError("Invite TTL must be at least 1 day.")
        if max_uses < 1:
            raise ValueError("Invite max_uses must be at least 1.")
        created_at = datetime.now(timezone.utc)
        expires_at = (created_at + timedelta(days=ttl_days)).isoformat()
        with self._existing_or_session(connection) as connection:
            for _ in range(20):
                code = f"{secrets.randbelow(1_000_000):06d}"
                result = connection.execute(
                    """
                    INSERT INTO invite_codes (
                        code, role, created_by_chat_id, max_uses, used_count,
                        expires_at, revoked_at, created_at
                    )
                    VALUES (?, ?, ?, ?, 0, ?, NULL, ?)
                    ON CONFLICT(code) DO NOTHING
                    """,
                    (code, role, created_by_chat_id, max_uses, expires_at, created_at.isoformat()),
                )
                if result.rowcount:
                    break
            else:
                raise ValueError("Could not allocate an invite code. Try again.")
            self._record_audit(
                connection,
                action="create_invite",
                target_type="invite",
                target_id=code,
                actor_chat_id=created_by_chat_id,
                details={
                    "role": role,
                    "ttl_days": ttl_days,
                    "max_uses": max_uses,
                },
            )
        return InviteCode(
            code, role, created_by_chat_id, max_uses, 0, expires_at, None, created_at.isoformat()
        )

    def redeem_invite(
        self,
        code: str,
        chat_id: int,
        username: str | None = None,
        first_name: str | None = None,
    ) -> AuthorizedChat:
        now = datetime.now(timezone.utc)
        with self.write_transaction() as connection:
            row = connection.execute(
                """
                SELECT code, role, created_by_chat_id, max_uses, used_count, expires_at, revoked_at, created_at
                FROM invite_codes
                WHERE code = ?
                """,
                (code.strip(),),
            ).fetchone()
            if row is None:
                raise ValueError("Invalid access code.")
            if row["revoked_at"]:
                raise ValueError("This invite has been revoked.")
            if row["expires_at"] and datetime.fromisoformat(row["expires_at"]) < now:
                raise ValueError("This invite has expired.")
            if row["used_count"] >= row["max_uses"]:
                raise ValueError("This invite has already been used.")
            authorized_at = now.isoformat()
            connection.execute(
                """
                INSERT INTO authorized_chats (chat_id, username, first_name, role, authorized_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    role = excluded.role,
                    authorized_at = excluded.authorized_at
                """,
                (chat_id, username, first_name, row["role"], authorized_at),
            )
            connection.execute(
                """
                UPDATE invite_codes
                SET used_count = used_count + 1
                WHERE code = ?
                """,
                (code.strip(),),
            )
            self._record_audit(
                connection,
                action="redeem_invite",
                target_type="invite",
                target_id=code.strip(),
                actor_chat_id=chat_id,
                details={"role": row["role"], "username": username, "first_name": first_name},
            )
        return AuthorizedChat(
            chat_id=chat_id,
            username=username,
            first_name=first_name,
            role=str(row["role"]),
            authorized_at=authorized_at,
        )

    def list_invites(
        self,
        active_only: bool = True,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> list[InviteCode]:
        filters = []
        params: list[object] = []
        now = datetime.now(timezone.utc).isoformat()
        if active_only:
            filters.append("revoked_at IS NULL")
            filters.append("(expires_at IS NULL OR expires_at >= ?)")
            filters.append("used_count < max_uses")
            params.append(now)
        where = ""
        if filters:
            where = "WHERE " + " AND ".join(filters)
        with self._existing_or_session(connection) as connection:
            rows = connection.execute(
                f"""
                SELECT code, role, created_by_chat_id, max_uses, used_count, expires_at, revoked_at, created_at
                FROM invite_codes
                {where}
                ORDER BY created_at DESC
                """,
                params,
            ).fetchall()
        return [self._row_to_invite(row) for row in rows]

    def revoke_invite(
        self,
        code: str,
        actor_chat_id: int | None = None,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> InviteCode:
        stripped = code.strip()
        revoked_at = datetime.now(timezone.utc).isoformat()
        with self._existing_or_session(connection) as connection:
            row = connection.execute(
                """
                SELECT code, role, created_by_chat_id, max_uses, used_count, expires_at, revoked_at, created_at
                FROM invite_codes
                WHERE code = ?
                """,
                (stripped,),
            ).fetchone()
            if row is None:
                raise ValueError("Unknown invite code.")
            if row["revoked_at"]:
                raise ValueError("Invite is already revoked.")
            connection.execute(
                """
                UPDATE invite_codes
                SET revoked_at = ?
                WHERE code = ?
                """,
                (revoked_at, stripped),
            )
            self._record_audit(
                connection,
                action="revoke_invite",
                target_type="invite",
                target_id=stripped,
                actor_chat_id=actor_chat_id,
                details={},
            )
        return InviteCode(
            code=row["code"],
            role=row["role"],
            created_by_chat_id=row["created_by_chat_id"],
            max_uses=row["max_uses"],
            used_count=row["used_count"],
            expires_at=row["expires_at"],
            revoked_at=revoked_at,
            created_at=row["created_at"],
        )

    def list_audit_events(self, limit: int = 50) -> list[AuditEvent]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, actor_chat_id, action, target_type, target_id, details_json, created_at
                FROM audit_events
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            AuditEvent(
                id=row["id"],
                actor_chat_id=row["actor_chat_id"],
                action=row["action"],
                target_type=row["target_type"],
                target_id=row["target_id"],
                details_json=row["details_json"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def record_audit_event(
        self,
        action: str,
        target_type: str,
        target_id: str,
        details: dict[str, object],
        actor_chat_id: int | None = None,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        with self._existing_or_session(connection) as connection:
            self._record_audit(
                connection,
                action=action,
                target_type=target_type,
                target_id=target_id,
                details=details,
                actor_chat_id=actor_chat_id,
            )

    def record_search(
        self, connection: sqlite3.Connection, chat_id: int, kind: str, query: str, count: int
    ) -> None:
        connection.execute(
            """
            INSERT INTO saved_searches (chat_id, kind, query, result_count, searched_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, kind, query, result_count)
            DO UPDATE SET searched_at = excluded.searched_at
            """,
            (chat_id, kind, query, count, datetime.now(timezone.utc).isoformat()),
        )
        self._prune_recent_searches(connection, chat_id)

    def list_saved_searches(
        self, chat_id: int, pinned_only: bool = False, limit: int = 20, offset: int = 0
    ) -> list[SavedSearch]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM saved_searches WHERE chat_id = ? AND (? = 0 OR pinned = 1)
                ORDER BY searched_at DESC, id DESC LIMIT ? OFFSET ?
                """,
                (chat_id, pinned_only, limit, offset),
            ).fetchall()
        return [self._row_to_saved_search(row) for row in rows]

    def get_saved_search(self, chat_id: int, search_id: int) -> SavedSearch | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM saved_searches WHERE id = ? AND chat_id = ?", (search_id, chat_id)
            ).fetchone()
        return None if row is None else self._row_to_saved_search(row)

    def set_search_pinned(
        self, connection: sqlite3.Connection, chat_id: int, search_id: int, pinned: bool
    ) -> SavedSearch | None:
        connection.execute(
            "UPDATE saved_searches SET pinned = ? WHERE id = ? AND chat_id = ?",
            (pinned, search_id, chat_id),
        )
        row = connection.execute(
            "SELECT * FROM saved_searches WHERE id = ? AND chat_id = ?", (search_id, chat_id)
        ).fetchone()
        self._prune_recent_searches(connection, chat_id)
        return None if row is None else self._row_to_saved_search(row)

    @staticmethod
    def _prune_recent_searches(connection: sqlite3.Connection, chat_id: int) -> None:
        connection.execute(
            """
            DELETE FROM saved_searches WHERE id IN (
                SELECT id FROM saved_searches WHERE chat_id = ? AND pinned = 0
                ORDER BY searched_at DESC, id DESC LIMIT -1 OFFSET 20
            )
            """,
            (chat_id,),
        )

    @staticmethod
    def _row_to_saved_search(row: sqlite3.Row) -> SavedSearch:
        return SavedSearch(
            row["id"], row["kind"], row["query"], row["result_count"],
            row["searched_at"], bool(row["pinned"]),
        )

    def get_api_browse_session(self, connection: sqlite3.Connection, chat_id: int) -> str | None:
        row = connection.execute(
            "SELECT session_json FROM api_browse_sessions WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        return None if row is None else str(row["session_json"])

    def save_api_browse_session(
        self, connection: sqlite3.Connection, chat_id: int, session_json: str
    ) -> None:
        connection.execute(
            """
            INSERT INTO api_browse_sessions (chat_id, session_json)
            VALUES (?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET session_json = excluded.session_json
            """,
            (chat_id, session_json),
        )

    def list_enrichment_candidates(
        self, source_root: str, model: str, version: str, limit: int
    ) -> list[EnrichmentCandidate]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT i.id, i.file_path, f.ftp_root_path, i.ftp_modified_at, i.file_size
                FROM images i
                JOIN folders f ON f.id = i.folder_id
                LEFT JOIN image_enrichment e
                    ON e.image_id = i.id AND e.model = ? AND e.version = ?
                   AND e.source_root = f.ftp_root_path
                   AND e.source_modified_at IS i.ftp_modified_at AND e.source_size IS i.file_size
                WHERE f.ftp_root_path = ? AND (e.image_id IS NULL OR e.error IS NOT NULL)
                ORDER BY e.attempted_at, i.id LIMIT ?
                """,
                (model, version, source_root, limit),
            ).fetchall()
        return [EnrichmentCandidate(*row) for row in rows]

    def save_image_enrichment(
        self,
        candidate: EnrichmentCandidate,
        model: str,
        version: str,
        caption: str,
        ocr_text: str,
        object_tags: tuple[str, ...],
        error: str | None = None,
    ) -> bool:
        searchable_text = normalize_text(" ".join((caption, ocr_text, *object_tags)))
        with self.session() as connection:
            result = connection.execute(
                """
                INSERT INTO image_enrichment (
                    image_id, model, version, source_root, source_modified_at, source_size,
                    caption, ocr_text, object_tags_json, searchable_text, attempted_at, error
                )
                SELECT i.id, ?, ?, f.ftp_root_path, i.ftp_modified_at, i.file_size, ?, ?, ?, ?, ?, ?
                FROM images i JOIN folders f ON f.id = i.folder_id
                WHERE i.id = ? AND i.file_path = ? AND f.ftp_root_path = ?
                  AND i.ftp_modified_at IS ? AND i.file_size IS ?
                ON CONFLICT(image_id, model, version) DO UPDATE SET
                    source_root = excluded.source_root, source_modified_at = excluded.source_modified_at,
                    source_size = excluded.source_size, caption = excluded.caption,
                    ocr_text = excluded.ocr_text, object_tags_json = excluded.object_tags_json,
                    searchable_text = excluded.searchable_text, attempted_at = excluded.attempted_at,
                    error = excluded.error
                    WHERE image_enrichment.error IS NOT NULL OR excluded.error IS NULL
                       OR image_enrichment.source_root != excluded.source_root
                       OR image_enrichment.source_modified_at IS NOT excluded.source_modified_at
                       OR image_enrichment.source_size IS NOT excluded.source_size
                """,
                (
                    model, version, caption, ocr_text, json.dumps(object_tags), searchable_text,
                    datetime.now(timezone.utc).isoformat(), error, candidate.image_id, candidate.path,
                    candidate.source_root, candidate.modified_at, candidate.size,
                ),
            )
        return bool(result.rowcount)

    def is_indexed_image(self, path: str) -> bool:
        with self.connect() as connection:
            return connection.execute(
                "SELECT 1 FROM images WHERE file_path = ?", (path,)
            ).fetchone() is not None

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

    def list_people(self) -> list[PersonSummary]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT p.id,
                       p.display_name,
                       COUNT(DISTINCT pa.id) AS aliases_count,
                       COUNT(DISTINCT fp.folder_id) AS folder_count
                FROM people p
                LEFT JOIN person_aliases pa ON pa.person_id = p.id
                LEFT JOIN folder_people fp ON fp.person_id = p.id
                GROUP BY p.id
                ORDER BY p.display_name ASC
                """
            ).fetchall()
        return [
            PersonSummary(
                id=row["id"],
                display_name=row["display_name"],
                aliases_count=row["aliases_count"],
                folder_count=row["folder_count"],
            )
            for row in rows
        ]

    def create_person(
        self, display_name: str, *, connection: sqlite3.Connection | None = None
    ) -> PersonDetail:
        normalized_name = self._normalize_person_value(display_name)
        with self._existing_or_session(connection) as connection:
            self._assert_person_name_available(connection, normalized_name)
            cursor = connection.execute(
                """
                INSERT INTO people (display_name, normalized_name)
                VALUES (?, ?)
                """,
                (display_name.strip(), normalized_name),
            )
            return self._person_detail_by_id(connection, int(cursor.lastrowid))

    def rename_person(self, identifier: str | int, new_display_name: str) -> PersonDetail:
        normalized_name = self._normalize_person_value(new_display_name)
        with self.connect() as connection:
            person = self._resolve_person(connection, identifier)
            if person is None:
                raise ValueError(f"Unknown person: {identifier}")
            self._assert_person_name_available(connection, normalized_name, exclude_person_id=person.id)
            previous_display_name = person.display_name
            previous_normalized = normalize_text(previous_display_name)
            connection.execute(
                """
                UPDATE people
                SET display_name = ?, normalized_name = ?
                WHERE id = ?
                """,
                (new_display_name.strip(), normalized_name, person.id),
            )
            if previous_normalized != normalized_name:
                self._insert_alias_if_missing(
                    connection,
                    person_id=person.id,
                    alias=previous_display_name,
                )
            connection.commit()
            return self._person_detail_by_id(connection, person.id)

    def add_person_alias(self, identifier: str | int, alias: str) -> PersonDetail:
        normalized_alias = self._normalize_person_value(alias)
        with self.connect() as connection:
            person = self._resolve_person(connection, identifier)
            if person is None:
                raise ValueError(f"Unknown person: {identifier}")
            self._assert_person_name_available(connection, normalized_alias, exclude_person_id=person.id)
            self._insert_alias_if_missing(connection, person.id, alias.strip())
            connection.commit()
            return self._person_detail_by_id(connection, person.id)

    def get_person_detail(self, identifier: str | int) -> PersonDetail | None:
        with self.connect() as connection:
            person = self._resolve_person(connection, identifier)
            if person is None:
                return None
            return self._person_detail_by_id(connection, person.id)

    def link_person_to_folder(self, identifier: str | int, folder_path: str) -> PersonDetail:
        with self.connect() as connection:
            person = self._resolve_person(connection, identifier)
            if person is None:
                raise ValueError(f"Unknown person: {identifier}")
            folder_id = self._resolve_folder_id(connection, folder_path)
            if folder_id is None:
                raise ValueError(f"Unknown folder: {folder_path}")
            connection.execute(
                """
                INSERT OR IGNORE INTO folder_people (folder_id, person_id)
                VALUES (?, ?)
                """,
                (folder_id, person.id),
            )
            connection.commit()
            return self._person_detail_by_id(connection, person.id)

    def unlink_person_from_folder(self, identifier: str | int, folder_path: str) -> PersonDetail:
        with self.connect() as connection:
            person = self._resolve_person(connection, identifier)
            if person is None:
                raise ValueError(f"Unknown person: {identifier}")
            folder_id = self._resolve_folder_id(connection, folder_path)
            if folder_id is None:
                raise ValueError(f"Unknown folder: {folder_path}")
            connection.execute(
                """
                DELETE FROM folder_people
                WHERE folder_id = ? AND person_id = ?
                """,
                (folder_id, person.id),
            )
            connection.commit()
            return self._person_detail_by_id(connection, person.id)

    def list_alias_map(self) -> dict[str, ResolvedPerson]:
        with self.connect() as connection:
            people_rows = connection.execute(
                """
                SELECT id, display_name, normalized_name
                FROM people
                ORDER BY id ASC
                """
            ).fetchall()
            alias_rows = connection.execute(
                """
                SELECT pa.person_id, pa.alias_normalized
                FROM person_aliases pa
                ORDER BY pa.person_id ASC, pa.alias_normalized ASC
                """
            ).fetchall()
        person_terms: dict[int, set[str]] = {}
        display_names: dict[int, str] = {}
        alias_map: dict[str, ResolvedPerson] = {}
        for row in people_rows:
            person_id = row["id"]
            display_names[person_id] = row["display_name"]
            person_terms.setdefault(person_id, set()).add(row["normalized_name"])
        for row in alias_rows:
            person_terms.setdefault(row["person_id"], set()).add(row["alias_normalized"])
        for person_id, terms in person_terms.items():
            resolved = ResolvedPerson(
                id=person_id,
                display_name=display_names[person_id],
                search_terms=tuple(sorted(terms)),
            )
            for term in resolved.search_terms:
                alias_map[term] = resolved
        return alias_map

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
                    record.source_root,
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
                record.source_root,
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
                    record.source_modified_at,
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
                record.source_modified_at,
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

    @staticmethod
    def _normalize_person_value(value: str) -> str:
        normalized = normalize_text(value)
        if not normalized:
            raise ValueError("Person name must not be empty.")
        return normalized

    def _assert_person_name_available(
        self,
        connection: sqlite3.Connection,
        normalized_value: str,
        exclude_person_id: int | None = None,
    ) -> None:
        people_row = connection.execute(
            """
            SELECT id FROM people WHERE normalized_name = ?
            """,
            (normalized_value,),
        ).fetchone()
        if people_row and people_row["id"] != exclude_person_id:
            raise ValueError(f'Name "{normalized_value}" is already assigned to another person.')
        alias_row = connection.execute(
            """
            SELECT person_id FROM person_aliases WHERE alias_normalized = ?
            """,
            (normalized_value,),
        ).fetchone()
        if alias_row and alias_row["person_id"] != exclude_person_id:
            raise ValueError(f'Alias "{normalized_value}" is already assigned to another person.')

    def _resolve_person(
        self, connection: sqlite3.Connection, identifier: str | int
    ) -> ResolvedPerson | None:
        if isinstance(identifier, int):
            row = connection.execute(
                "SELECT id, display_name FROM people WHERE id = ?", (identifier,)
            ).fetchone()
            return None if row is None else ResolvedPerson(row["id"], row["display_name"])
        normalized_identifier = normalize_text(identifier)
        if not normalized_identifier:
            return None
        row = connection.execute(
            """
            SELECT id, display_name
            FROM people
            WHERE normalized_name = ?
            """,
            (normalized_identifier,),
        ).fetchone()
        if row is None:
            row = connection.execute(
                """
                SELECT p.id, p.display_name
                FROM person_aliases pa
                JOIN people p ON p.id = pa.person_id
                WHERE pa.alias_normalized = ?
                """,
                (normalized_identifier,),
            ).fetchone()
        if row is None:
            return None
        return ResolvedPerson(id=row["id"], display_name=row["display_name"])

    @staticmethod
    def _resolve_folder_id(connection: sqlite3.Connection, folder_path: str) -> int | None:
        row = connection.execute(
            """
            SELECT id FROM folders WHERE folder_path = ?
            """,
            (folder_path.strip(),),
        ).fetchone()
        return None if row is None else int(row["id"])

    def _insert_alias_if_missing(
        self, connection: sqlite3.Connection, person_id: int, alias: str
    ) -> None:
        normalized_alias = self._normalize_person_value(alias)
        person_row = connection.execute(
            """
            SELECT normalized_name FROM people WHERE id = ?
            """,
            (person_id,),
        ).fetchone()
        if person_row is not None and person_row["normalized_name"] == normalized_alias:
            return
        existing = connection.execute(
            """
            SELECT 1 FROM person_aliases
            WHERE person_id = ? AND alias_normalized = ?
            """,
            (person_id, normalized_alias),
        ).fetchone()
        if existing is not None:
            return
        connection.execute(
            """
            INSERT INTO person_aliases (person_id, alias, alias_normalized)
            VALUES (?, ?, ?)
            """,
            (person_id, alias.strip(), normalized_alias),
        )

    def _person_detail_by_id(self, connection: sqlite3.Connection, person_id: int) -> PersonDetail:
        person_row = connection.execute(
            """
            SELECT id, display_name
            FROM people
            WHERE id = ?
            """,
            (person_id,),
        ).fetchone()
        aliases = connection.execute(
            """
            SELECT alias
            FROM person_aliases
            WHERE person_id = ?
            ORDER BY alias_normalized ASC
            """,
            (person_id,),
        ).fetchall()
        folder_rows = connection.execute(
            """
            SELECT f.folder_path
            FROM folder_people fp
            JOIN folders f ON f.id = fp.folder_id
            WHERE fp.person_id = ?
            ORDER BY f.year DESC, f.folder_path ASC
            """,
            (person_id,),
        ).fetchall()
        return PersonDetail(
            id=person_row["id"],
            display_name=person_row["display_name"],
            aliases=tuple(row["alias"] for row in aliases),
            folder_paths=tuple(row["folder_path"] for row in folder_rows),
        )

    @staticmethod
    def _row_to_invite(row: sqlite3.Row) -> InviteCode:
        return InviteCode(
            code=row["code"],
            role=row["role"],
            created_by_chat_id=row["created_by_chat_id"],
            max_uses=row["max_uses"],
            used_count=row["used_count"],
            expires_at=row["expires_at"],
            revoked_at=row["revoked_at"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _record_audit(
        connection: sqlite3.Connection,
        action: str,
        target_type: str,
        target_id: str,
        details: dict[str, object],
        actor_chat_id: int | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_events (
                actor_chat_id, action, target_type, target_id, details_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                actor_chat_id,
                action,
                target_type,
                target_id,
                json.dumps(details, sort_keys=True),
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    @staticmethod
    def _has_column(connection: sqlite3.Connection, table_name: str, column_name: str) -> bool:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        return any(row["name"] == column_name for row in rows)

    def _migrate_schema(self, connection: sqlite3.Connection) -> None:
        if not self._has_column(connection, "authorized_chats", "role"):
            connection.execute(
                "ALTER TABLE authorized_chats ADD COLUMN role TEXT NOT NULL DEFAULT 'viewer'"
            )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_authorized_chats_role ON authorized_chats(role)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_preferences_language ON chat_preferences(language)"
        )
