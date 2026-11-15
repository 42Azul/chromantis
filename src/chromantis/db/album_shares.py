from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from sqlite3 import Connection


TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{43}")


def _digest(secret: object) -> str | None:
    if isinstance(secret, str) and TOKEN_RE.fullmatch(secret):
        return hashlib.sha256(secret.encode("ascii")).hexdigest()
    return None


class AlbumShareStore:
    def __init__(self, connection: Connection, owner_chat_id: int | None = None):
        self.connection = connection
        self.owner_chat_id = owner_chat_id

    def create(self, path: str, ttl_days: int) -> tuple[dict, str]:
        if self.owner_chat_id is None:
            raise ValueError("An owner is required.")
        if type(ttl_days) is not int or not 1 <= ttl_days <= 90:
            raise ValueError("ttl_days must be an integer between 1 and 90.")
        folder = self.connection.execute(
            "SELECT id FROM folders WHERE folder_path = ?", (path,)
        ).fetchone()
        if folder is None:
            raise ValueError("Choose an album from the index.")
        now = datetime.now(timezone.utc)
        self.connection.execute("DELETE FROM album_shares WHERE expires_at <= ?", (now.isoformat(),))
        secret = secrets.token_urlsafe(32)
        expires_at = (now + timedelta(days=ttl_days)).isoformat()
        result = self.connection.execute(
            """INSERT INTO album_shares
               (owner_chat_id, folder_id, secret_hash, expires_at, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (self.owner_chat_id, folder["id"], _digest(secret), expires_at, now.isoformat()),
        )
        return self.get(int(result.lastrowid)), secret

    def list(self, path: str | None = None) -> list[dict]:
        if self.owner_chat_id is None:
            raise ValueError("An owner is required.")
        clauses = ["s.owner_chat_id = ?", "s.expires_at > ?"]
        values: list[object] = [self.owner_chat_id, datetime.now(timezone.utc).isoformat()]
        if path is not None:
            clauses.append("f.folder_path = ?")
            values.append(path)
        rows = self.connection.execute(
            f"""SELECT s.id, f.folder_path AS path, album.title, s.expires_at, s.created_at
                FROM album_shares s JOIN folders f ON f.id = s.folder_id
                JOIN album_metadata album ON album.id = f.id
                WHERE {' AND '.join(clauses)} ORDER BY s.id DESC""",
            values,
        )
        return [dict(row) for row in rows]

    def get(self, share_id: int) -> dict:
        row = self.connection.execute(
            """SELECT s.id, f.folder_path AS path, album.title, s.expires_at, s.created_at
               FROM album_shares s JOIN folders f ON f.id = s.folder_id
               JOIN album_metadata album ON album.id = f.id
               WHERE s.id = ? AND s.owner_chat_id = ?""",
            (share_id, self.owner_chat_id),
        ).fetchone()
        if row is None:
            raise LookupError("Album share not found.")
        return dict(row)

    def revoke(self, share_id: int) -> None:
        result = self.connection.execute(
            "DELETE FROM album_shares WHERE id = ? AND owner_chat_id = ?",
            (share_id, self.owner_chat_id),
        )
        if not result.rowcount:
            raise LookupError("Album share not found.")

    def resolve(self, secret: object) -> dict | None:
        digest = _digest(secret)
        if digest is None:
            return None
        row = self.connection.execute(
            """SELECT s.id, f.folder_path AS path, album.title, album.event_date,
                      album.year, s.expires_at
               FROM album_shares s JOIN folders f ON f.id = s.folder_id
               JOIN album_metadata album ON album.id = f.id
               WHERE s.secret_hash = ? AND s.expires_at > ?""",
            (digest, datetime.now(timezone.utc).isoformat()),
        ).fetchone()
        return None if row is None else dict(row)

    def contains_image(self, share: dict, path: str) -> bool:
        row = self.connection.execute(
            """SELECT 1 FROM images i JOIN folders f ON f.id = i.folder_id
               WHERE i.file_path = ? AND f.folder_path = ?""",
            (path, share["path"]),
        ).fetchone()
        return row is not None

    def images(self, share: dict, limit: int, offset: int) -> list[dict]:
        rows = self.connection.execute(
            """SELECT i.file_path AS path, i.filename, f.folder_path, album.title,
                      album.year
               FROM images i JOIN folders f ON f.id = i.folder_id
               JOIN album_metadata album ON album.id = f.id
               WHERE f.folder_path = ? ORDER BY i.file_path LIMIT ? OFFSET ?""",
            (share["path"], limit, offset),
        )
        return [dict(row) for row in rows]
