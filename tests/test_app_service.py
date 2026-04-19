from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from chromantis.app import ApplicationService
from chromantis.db.repository import Repository


class ApplicationServiceAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = str(Path(self.temp_dir.name) / "chromantis.db")
        self.repository = Repository(db_path)
        self.repository.init_schema()
        self.service = ApplicationService(
            self.repository,
            access_code="246810",
            static_viewer_chat_ids=(1234,),
            static_owner_chat_ids=(9999,),
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_resolve_principal_supports_static_dynamic_and_none(self) -> None:
        self.repository.authorize_chat(5678, username="member", role="admin")

        static_viewer = self.service.resolve_principal(1234)
        static_owner = self.service.resolve_principal(9999)
        dynamic = self.service.resolve_principal(5678)
        missing = self.service.resolve_principal(42)

        self.assertEqual((static_viewer.role, static_viewer.auth_mode), ("viewer", "static_viewer"))
        self.assertEqual((static_owner.role, static_owner.auth_mode), ("owner", "static_owner"))
        self.assertEqual((dynamic.role, dynamic.auth_mode), ("admin", "dynamic"))
        self.assertEqual((missing.role, missing.auth_mode), ("none", "none"))

    def test_static_principal_overrides_dynamic_role(self) -> None:
        self.repository.authorize_chat(1234, username="override", role="admin")

        principal = self.service.resolve_principal(1234)

        self.assertEqual(principal.role, "viewer")
        self.assertEqual(principal.auth_mode, "static_viewer")
        self.assertEqual(principal.username, "override")

    def test_access_code_login_is_viewer_only(self) -> None:
        chat = self.service.authorize_with_code(5678, "246810", username="guest")

        self.assertEqual(chat.role, "viewer")
        self.assertEqual(self.repository.get_chat_role(5678), "viewer")

    def test_list_effective_authorized_chats_merges_static_and_dynamic(self) -> None:
        self.repository.authorize_chat(5678, username="guest", role="viewer")

        principals = self.service.list_effective_authorized_chats()

        self.assertEqual(
            [(item.chat_id, item.role, item.auth_mode) for item in principals],
            [
                (1234, "viewer", "static_viewer"),
                (5678, "viewer", "dynamic"),
                (9999, "owner", "static_owner"),
            ],
        )

    def test_chat_language_can_be_stored_through_service(self) -> None:
        preferences = self.service.set_chat_language(5678, "es", actor_chat_id=5678)

        self.assertEqual(preferences.language, "es")
        self.assertEqual(self.service.get_chat_language(5678), "es")
