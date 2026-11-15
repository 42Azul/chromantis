from __future__ import annotations

import json
import logging
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import configure_nas
from chromantis.logging_utils import RedactingFormatter


class NasSetupTests(unittest.TestCase):
    def test_existing_config_starts_without_prompts_or_telegram_requests(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "2021").mkdir()
            env_file = root / ".env"
            env_file.write_text(
                f"SOURCE_TYPE=local\nSOURCE_ROOT={root}\n"
                "TELEGRAM_TOKEN=123:example\nTELEGRAM_ADMIN_CHAT_ALLOWLIST=42\n"
                'API_CHAT_TOKENS={"42":"existing-web-token"}\nLOG_LEVEL=DEBUG\n',
                encoding="utf-8",
            )
            env_file.chmod(0o644)
            with (
                patch.dict(os.environ, {"CHROMANTIS_OWNER_CHAT_ID": ""}),
                patch.object(configure_nas, "telegram_request") as telegram,
                patch.object(configure_nas.getpass, "getpass") as prompt,
            ):
                configure_nas.main(path=env_file)
            prompt.assert_not_called()
            telegram.assert_not_called()
            settings = configure_nas.read_env(env_file)
            self.assertEqual(json.loads(settings["API_CHAT_TOKENS"]), {"42": "existing-web-token"})
            self.assertEqual(settings["LOG_LEVEL"], "DEBUG")
            self.assertEqual(stat.S_IMODE(env_file.stat().st_mode), 0o600)

    def test_first_install_creates_env_with_two_separate_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "2021").mkdir()
            env_file = root / ".env"
            with (
                patch.dict(os.environ, {"CHROMANTIS_PHOTOS": str(root), "CHROMANTIS_OWNER_CHAT_ID": ""}),
                patch.object(configure_nas.sys.stdin, "isatty", return_value=True),
                patch.object(configure_nas.getpass, "getpass", return_value="123:new-token"),
                patch.object(configure_nas, "telegram_request", return_value={"username": "test_bot"}) as telegram,
                patch.object(configure_nas, "enroll_owner", return_value=42),
            ):
                configure_nas.main(path=env_file)
            telegram.assert_called_once_with("123:new-token", "getMe")
            settings = configure_nas.read_env(env_file)
            self.assertEqual(settings["TELEGRAM_TOKEN"], "123:new-token")
            self.assertEqual(settings["SOURCE_ROOT"], str(root))
            self.assertEqual(settings["TELEGRAM_ADMIN_CHAT_ALLOWLIST"], "42")
            self.assertNotEqual(json.loads(settings["API_CHAT_TOKENS"])["42"], "123:new-token")
            self.assertEqual(stat.S_IMODE(env_file.stat().st_mode), 0o600)

    def test_new_owner_must_send_exact_challenge_in_a_private_chat(self) -> None:
        updates = [
            {"message": {"chat": {"id": -3, "type": "group"}, "text": "/start proof"}},
            {"message": {"chat": {"id": 4, "type": "private"}, "text": "/start stale"}},
            {"message": {"chat": {"id": 5, "type": "private"}, "text": "/start proof"}},
        ]
        self.assertEqual(configure_nas.find_owner(updates, "proof"), 5)
        self.assertIsNone(configure_nas.find_owner(updates[:2], "proof"))

    def test_telegram_token_is_hidden_in_request_logs(self) -> None:
        formatter = RedactingFormatter("123:example")
        record = logging.LogRecord("httpx", logging.INFO, "", 1, "GET %s",
                                   ("https://api.telegram.org/bot123:example/getMe",), None)
        self.assertIn("bot[redacted]/getMe", formatter.format(record))
        self.assertNotIn("123:example", formatter.format(record))
