from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from chromantis.config import AppConfig, normalize_ftp_root


class ConfigTests(unittest.TestCase):
    def test_normalize_ftp_root_requires_absolute_path(self) -> None:
        with self.assertRaises(ValueError):
            normalize_ftp_root("photos/archive")

    def test_normalize_ftp_root_strips_duplicate_slashes(self) -> None:
        self.assertEqual(normalize_ftp_root("/photos//archive/"), "/photos/archive")

    def test_from_env_reads_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text(
                "\n".join(
                    [
                        "FTP_HOST=ftp.local",
                        "FTP_USER=tester",
                        "FTP_PASSWORD=secret",
                        "FTP_PHOTOS_ROOT=/photos/archive",
                        "SQLITE_PATH=/tmp/chromantis-test.db",
                        "TELEGRAM_CHAT_ALLOWLIST=10,20",
                        "TELEGRAM_ACCESS_CODE=654321",
                    ]
                ),
                encoding="utf-8",
            )

            for key in (
                "FTP_HOST",
                "FTP_USER",
                "FTP_PASSWORD",
                "FTP_PHOTOS_ROOT",
                "SQLITE_PATH",
                "TELEGRAM_CHAT_ALLOWLIST",
                "TELEGRAM_ACCESS_CODE",
            ):
                os.environ.pop(key, None)

            config = AppConfig.from_env(str(dotenv_path))

        self.assertEqual(config.ftp_host, "ftp.local")
        self.assertEqual(config.ftp_photos_root, "/photos/archive")
        self.assertEqual(config.sqlite_path, "/tmp/chromantis-test.db")
        self.assertEqual(config.telegram_chat_allowlist, (10, 20))
        self.assertEqual(config.telegram_access_code, "654321")
