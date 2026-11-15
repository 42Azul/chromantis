from __future__ import annotations

import json
import tempfile
from http.client import HTTPConnection
from threading import Thread
import unittest
from pathlib import Path

from chromantis.api.server import ApiServer, handle_api_get, make_api_handler
from chromantis.app import ApplicationService
from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser
from chromantis.source import ArchiveScanner, LocalArchiveSource


PHOTOS_ROOT = Path(__file__).parent / "fixtures" / "ftp_tree" / "server_root" / "photos" / "archive"


class ApiServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = str(Path(self.temp_dir.name) / "chromantis.db")
        repository = Repository(db_path)
        self.repository = repository
        repository.init_schema()
        scanner = ArchiveScanner(LocalArchiveSource(str(PHOTOS_ROOT)), repository, PathParser())
        scanner.scan()
        self.app_service = ApplicationService(repository, static_owner_chat_ids=(101,))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_health_endpoint_is_public(self) -> None:
        status, payload = handle_api_get("/api/v1/health", app_service=self.app_service, api_token="secret-token")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"status": "ok"})

    def test_images_endpoint_requires_token(self) -> None:
        status, payload = handle_api_get("/api/v1/images?q=city", app_service=self.app_service, api_token="secret-token")
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "Unauthorized")

    def test_images_endpoint_returns_results_with_token(self) -> None:
        status, payload = handle_api_get(
            "/api/v1/images?q=city&limit=2",
            app_service=self.app_service,
            api_token="secret-token",
            auth_header="Bearer secret-token",
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["items"]), 2)
        self.assertIn("path", payload["items"][0])
        self.assertIn("reason", payload["items"][0])

    def test_years_endpoint_returns_summaries(self) -> None:
        status, payload = handle_api_get(
            "/api/v1/years?from=2019&to=2021",
            app_service=self.app_service,
            api_token="secret-token",
            x_api_token="secret-token",
        )
        self.assertEqual(status, 200)
        years = [item["year"] for item in payload["items"]]
        self.assertEqual(years, [2019, 2021])


    def start_api(self) -> None:
        self.repository.authorize_chat(102, role="admin")
        self.repository.authorize_chat(103, role="viewer")
        self.repository.authorize_chat(104, role="viewer")
        self.server = ApiServer(("127.0.0.1", 0), make_api_handler(
            self.app_service, api_token="read-token",
            api_chat_tokens=((101, "owner-token"), (102, "admin-token"), (103, "viewer-token")),
        ))
        thread = Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(self.server.shutdown)

    def request(
        self, method: str, path: str, token: str | None = None, body: object = None
    ) -> tuple[int, dict]:
        connection = HTTPConnection(*self.server.server_address, timeout=2)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            connection.request(
                method, "/api/v1" + path, None if body is None else json.dumps(body), headers
            )
            response = connection.getresponse()
            self.assertEqual(response.getheader("Cache-Control"), "no-store")
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_chat_identity_is_bound_to_credential_and_role_is_live(self) -> None:
        self.start_api()
        self.assertEqual(self.request("GET", "/auth/me", "read-token")[0], 401)
        self.assertEqual(self.request("GET", "/admin/chats?chat_id=101", "viewer-token")[0], 403)
        status, data = self.request("GET", "/auth/me?chat_id=101", "admin-token")
        self.assertEqual((status, data["item"]["chat_id"], data["item"]["role"]), (200, 102, "admin"))
        self.assertEqual(self.request("GET", "/images?q=city", "viewer-token")[0], 200)
        self.assertEqual(self.request("PATCH", "/admin/chats/102", "owner-token", {"role": "viewer"})[0], 200)
        self.assertEqual(self.request("GET", "/admin/chats", "admin-token")[0], 403)
        self.assertEqual(self.request("DELETE", "/admin/chats/103", "owner-token")[0], 200)
        self.assertEqual(self.request("GET", "/images", "viewer-token")[0], 401)
        role_change = next(event for event in self.repository.list_audit_events() if event.action == "set_chat_role")
        self.assertEqual((role_change.actor_chat_id, role_change.target_id), (101, "102"))

    def test_chat_admin_cannot_change_roles_or_revoke_another_admin(self) -> None:
        self.start_api()
        self.assertEqual(self.request("PATCH", "/admin/chats/103", "admin-token", {"role": "admin"})[0], 403)
        self.assertEqual(self.request("DELETE", "/admin/chats/102", "admin-token")[0], 403)
        self.assertEqual(self.request("DELETE", "/admin/chats/104", "admin-token")[0], 200)
        self.assertEqual(self.request("PATCH", "/admin/chats/101", "owner-token", {"role": "viewer"})[0], 409)
        self.assertEqual(self.request("DELETE", "/admin/chats/101", "owner-token")[0], 409)

    def test_admin_invites_are_secret_and_owner_revocation_is_audited(self) -> None:
        self.start_api()
        path = "/admin/invites"
        self.assertEqual(self.request("POST", path, "viewer-token", {})[0], 403)
        self.assertEqual(self.request("POST", path, "admin-token", {"role": "admin"})[0], 403)
        self.assertEqual(self.request("POST", path, "owner-token", {"ttl_days": True})[0], 400)
        self.assertEqual(self.request("POST", path, "owner-token", {"ttl_days": 99999999})[0], 400)
        status, payload = self.request("POST", path, "owner-token", {"role": "admin", "ttl_days": 3})
        self.assertEqual(status, 201)
        code = payload["item"]["code"]
        self.assertEqual(self.request("GET", path, "admin-token"), (200, {"items": []}))
        self.assertEqual(self.request("DELETE", f"{path}/{code}", "admin-token")[0], 404)
        status, payload = self.request("DELETE", f"{path}/{code}", "owner-token")
        self.assertEqual(status, 200)
        self.assertIsNotNone(payload["item"]["revoked_at"])
        event = self.repository.list_audit_events()[0]
        self.assertEqual((event.action, event.actor_chat_id, event.target_id), ("revoke_invite", 101, code))
