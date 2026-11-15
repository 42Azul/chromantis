from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from sqlite3 import Connection

from chromantis.db.repository import Repository


SESSION_SECONDS = 90 * 24 * 60 * 60


@dataclass(frozen=True)
class FamilySession:
    id: int
    label: str
    secret_hash: str = field(repr=False)


def _digest(secret: object) -> str | None:
    if isinstance(secret, str) and re.fullmatch(r"[A-Za-z0-9_-]{43}", secret):
        return hashlib.sha256(secret.encode("ascii")).hexdigest()
    return None


class FamilyAccess:
    def __init__(self, repository: Repository):
        self.repository = repository

    def invite(self, label: str) -> tuple[int, str]:
        label = label.strip()
        if not 1 <= len(label) <= 80:
            raise ValueError("Escribe un nombre de entre 1 y 80 caracteres.")
        code = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        with self.repository.write_transaction() as connection:
            connection.execute("DELETE FROM family_access WHERE expires_at <= ?", (now.isoformat(),))
            row = connection.execute(
                """INSERT INTO family_access (label, secret_hash, kind, expires_at)
                   VALUES (?, ?, 'invite', ?)""",
                (label, _digest(code), (now + timedelta(days=1)).isoformat()),
            )
            return int(row.lastrowid), code

    def redeem(self, invite: object) -> str | None:
        invite_hash = _digest(invite)
        if invite_hash is None:
            return None
        secret = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        with self.repository.session() as connection:
            result = connection.execute(
                """UPDATE family_access SET secret_hash = ?, kind = 'session', expires_at = ?
                   WHERE secret_hash = ? AND kind = 'invite' AND expires_at > ?""",
                (_digest(secret), (now + timedelta(seconds=SESSION_SECONDS)).isoformat(),
                 invite_hash, now.isoformat()),
            )
            return secret if result.rowcount else None

    def resolve(self, secret: str) -> FamilySession | None:
        digest = _digest(secret)
        if digest is None:
            return None
        with self.repository.session() as connection:
            row = self._active_session(connection, digest)
            return FamilySession(row["id"], row["label"], digest) if row is not None else None

    def still_active(self, connection: Connection, session: FamilySession) -> bool:
        row = self._active_session(connection, session.secret_hash)
        return row is not None and row["id"] == session.id

    @staticmethod
    def _active_session(connection: Connection, digest: str):
        return connection.execute(
            """SELECT id, label FROM family_access
               WHERE secret_hash = ? AND kind = 'session' AND expires_at > ?""",
            (digest, datetime.now(timezone.utc).isoformat()),
        ).fetchone()

    def list(self) -> list[dict]:
        with self.repository.session() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT id, label, kind, expires_at FROM family_access WHERE expires_at > ? ORDER BY id",
                (datetime.now(timezone.utc).isoformat(),),
            )]

    def revoke(self, identity: int) -> bool:
        with self.repository.session() as connection:
            return connection.execute("DELETE FROM family_access WHERE id = ?", (identity,)).rowcount == 1

    def sign_out(self, secret: str) -> None:
        digest = _digest(secret)
        if digest is not None:
            with self.repository.session() as connection:
                connection.execute(
                    "DELETE FROM family_access WHERE secret_hash = ? AND kind = 'session'", (digest,),
                )
