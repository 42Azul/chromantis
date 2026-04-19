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
