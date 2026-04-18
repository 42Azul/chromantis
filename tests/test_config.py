from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from chromantis.config import AppConfig, normalize_ftp_root, normalize_local_root, normalize_source_type


class ConfigTests(unittest.TestCase):
    def test_normalize_source_type_rejects_unknown_value(self) -> None:
        with self.assertRaises(ValueError):
            normalize_source_type("s3")

    def test_normalize_ftp_root_requires_absolute_path(self) -> None:
        with self.assertRaises(ValueError):
            normalize_ftp_root("photos/archive")

    def test_normalize_ftp_root_strips_duplicate_slashes(self) -> None:
        self.assertEqual(normalize_ftp_root("/photos//archive/"), "/photos/archive")

    def test_normalize_local_root_resolves_relative_path_from_repo_root(self) -> None:
        resolved = normalize_local_root("tests/fixtures/ftp_tree")
        self.assertTrue(resolved.endswith("tests/fixtures/ftp_tree"))

    def test_from_env_reads_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text(
                "\n".join(
                    [
                        "SOURCE_TYPE=ftp",
                        "SOURCE_ROOT=/photos/archive",
                        "FTP_HOST=ftp.local",
                        "FTP_USER=tester",
                        "FTP_PASSWORD=secret",
                        "SQLITE_PATH=/tmp/chromantis-test.db",
                        "TELEGRAM_CHAT_ALLOWLIST=10,20",
                        "TELEGRAM_ADMIN_CHAT_ALLOWLIST=20",
                        "TELEGRAM_ACCESS_CODE=654321",
                    ]
                ),
                encoding="utf-8",
            )

            for key in (
                "SOURCE_TYPE",
                "SOURCE_ROOT",
                "FTP_HOST",
                "FTP_USER",
                "FTP_PASSWORD",
                "SQLITE_PATH",
                "TELEGRAM_CHAT_ALLOWLIST",
                "TELEGRAM_ADMIN_CHAT_ALLOWLIST",
                "TELEGRAM_ACCESS_CODE",
            ):
                os.environ.pop(key, None)

            config = AppConfig.from_env(str(dotenv_path))

        self.assertEqual(config.source_type, "ftp")
        self.assertEqual(config.ftp_host, "ftp.local")
        self.assertEqual(config.source_root, "/photos/archive")
        self.assertEqual(config.sqlite_path, "/tmp/chromantis-test.db")
        self.assertEqual(config.telegram_chat_allowlist, (10, 20))
        self.assertEqual(config.telegram_admin_chat_allowlist, (20,))
        self.assertEqual(config.telegram_access_code, "654321")

    def test_from_env_reads_local_source_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text(
                "\n".join(
                    [
                        "SOURCE_TYPE=local",
                        "SOURCE_ROOT=tests/fixtures/ftp_tree/server_root/photos/archive",
                    ]
                ),
                encoding="utf-8",
            )
            for key in ("SOURCE_TYPE", "SOURCE_ROOT", "FTP_PHOTOS_ROOT"):
                os.environ.pop(key, None)
            config = AppConfig.from_env(str(dotenv_path))

        self.assertEqual(config.source_type, "local")
        self.assertTrue(config.source_root.endswith("tests/fixtures/ftp_tree/server_root/photos/archive"))
