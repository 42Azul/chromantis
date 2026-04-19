from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from chromantis.db.repository import Repository


class RepositoryMigrationTests(unittest.TestCase):
    def test_init_schema_migrates_legacy_authorized_chats_table(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "chromantis.db"
            connection = sqlite3.connect(db_path)
            connection.execute(
                """
                CREATE TABLE authorized_chats (
                    chat_id INTEGER PRIMARY KEY,
                    username TEXT NULL,
                    first_name TEXT NULL,
                    authorized_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO authorized_chats (chat_id, username, first_name, authorized_at)
                VALUES (1, 'tester', 'Test', '2026-04-19T12:00:00+00:00')
                """
            )
            connection.commit()
            connection.close()

            repository = Repository(str(db_path))
            repository.init_schema()

            migrated_connection = repository.connect()
            columns = migrated_connection.execute(
                "PRAGMA table_info(authorized_chats)"
            ).fetchall()
            column_names = {row["name"] for row in columns}
            self.assertIn("role", column_names)
            role = migrated_connection.execute(
                "SELECT role FROM authorized_chats WHERE chat_id = 1"
            ).fetchone()["role"]
            self.assertEqual(role, "viewer")
            index_names = {
                row["name"]
                for row in migrated_connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                ).fetchall()
            }
            self.assertIn("idx_authorized_chats_role", index_names)
            migrated_connection.close()

    def test_authorize_chat_accepts_owner_role(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "chromantis.db"
            repository = Repository(str(db_path))
            repository.init_schema()

            repository.authorize_chat(1, username="owner", role="owner")

            self.assertEqual(repository.get_chat_role(1), "owner")

    def test_revoke_chat_access_records_actor_and_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "chromantis.db"
            repository = Repository(str(db_path))
            repository.init_schema()
            repository.authorize_chat(1, username="viewer", role="viewer")

            repository.revoke_chat_access(1, actor_chat_id=99, reason="admin_revoke")

            self.assertFalse(repository.is_chat_authorized(1))
            event = repository.list_audit_events(limit=1)[0]
            self.assertEqual(event.action, "revoke_chat_access")
            self.assertEqual(event.actor_chat_id, 99)
            self.assertIn('"reason": "admin_revoke"', event.details_json)

    def test_revoke_invite_marks_invite_revoked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "chromantis.db"
            repository = Repository(str(db_path))
            repository.init_schema()
            invite = repository.create_invite(role="viewer", created_by_chat_id=1)

            revoked = repository.revoke_invite(invite.code, actor_chat_id=2)

            self.assertIsNotNone(revoked.revoked_at)
            self.assertEqual(repository.list_invites(active_only=True), [])
