from __future__ import annotations

import json
import tempfile
from http.client import HTTPConnection
from threading import Thread
from urllib.parse import urlencode
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
            image_fetcher=LocalArchiveSource(str(PHOTOS_ROOT)).read_bytes,
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


    def test_browse_continues_excluding_previous_images_and_can_go_back(self) -> None:
        self.start_api()
        token = "viewer-token"
        self.assertEqual(self.request("GET", "/browse", "read-token")[0], 401)
        self.assertEqual(self.request("GET", "/browse", "admin-token")[0], 404)
        status, first = self.request("POST", "/browse", token, {"action": "search", "q": "city", "count": 1})
        self.assertEqual(status, 200)
        self.assertEqual(first["years"], [2021])
        self.assertEqual(len(first["folders"]), 1)
        self.assertFalse(first["can_go_back"])
        self.assertEqual(self.request("GET", "/browse", token), (200, first))
        self.assertEqual(self.request("GET", "/browse", "admin-token")[0], 404)

        status, second = self.request("POST", "/browse", token, {"action": "more"})
        self.assertEqual(status, 200)
        self.assertNotEqual(second["items"][0]["path"], first["items"][0]["path"])
        self.assertTrue(second["can_go_back"])
        self.assertEqual(self.request("POST", "/browse", token, {"action": "more"})[1]["items"], [])
        self.assertEqual(self.request("GET", "/browse", token), (200, second))
        self.assertEqual(self.request("POST", "/browse", token, {"action": "back"}), (200, first))

    def test_browse_can_switch_to_folder_and_year_and_returns_conflicts_for_missing_context(self) -> None:
        self.start_api()
        token = "viewer-token"
        self.request("POST", "/browse", token, {"action": "search", "q": "city", "count": 1})
        status, in_folder = self.request("POST", "/browse", token, {"action": "same_folder"})
        self.assertEqual((status, in_folder["scope"], in_folder["years"]), (200, "same_folder", [2021]))
        self.request("POST", "/browse", token, {"action": "back"})
        status, in_year = self.request("POST", "/browse", token, {"action": "same_year"})
        self.assertEqual((status, in_year["scope"], in_year["years"]), (200, "same_year", [2021]))
        self.request("POST", "/browse", token, {"action": "search", "count": 5})
        self.assertEqual(self.request("POST", "/browse", token, {"action": "related"})[0], 409)
        self.assertEqual(self.request("POST", "/browse", token, {"action": "more", "count": True})[0], 400)

    def test_browse_related_keeps_anchor_for_continuation(self) -> None:
        with self.repository.session() as connection:
            for index in (1, 2):
                record = PathParser().parse_image_path(
                    str(PHOTOS_ROOT), f"2021/2021-08-16_city_walk/IMG_{index}.jpg", None, None
                )
                self.repository.upsert_image_record(connection, record, "test")
        self.start_api()
        token = "viewer-token"
        self.request("POST", "/browse", token, {"action": "search", "q": "city", "count": 1})
        status, related = self.request("POST", "/browse", token, {"action": "related"})
        self.assertEqual((status, related["scope"]), (200, "related_images"))
        self.assertEqual(related["folders"], ["2021/2021-08-16_city_walk"])
        status, continuation = self.request("POST", "/browse", token, {"action": "more"})
        self.assertEqual((status, continuation["folders"]), (200, related["folders"]))
        self.assertNotEqual(continuation["items"][0]["path"], related["items"][0]["path"])

    def test_browser_can_curate_and_view_person_details(self) -> None:
        self.start_api()
        status, person = self.request("POST", "/admin/people", "admin-token", {"display_name": "Ana"})
        self.assertEqual(status, 201)
        person_id = person["item"]["id"]
        path = f"/admin/people/{person_id}"
        self.assertEqual(self.request("PATCH", path, "viewer-token", {"display_name": "Other"})[0], 403)
        self.assertEqual(self.request("PATCH", path, "admin-token", {"display_name": "Anita"})[0], 200)
        self.assertEqual(self.request("POST", path + "/aliases", "admin-token", {"alias": "Anni"})[0], 200)
        folder = "2021/2021-08-15_city_trip"
        self.assertEqual(self.request("POST", path + "/folders", "admin-token", {"path": folder})[0], 200)
        status, detail = self.request("GET", f"/people/{person_id}", "read-token")
        self.assertEqual(status, 200)
        self.assertEqual(detail["item"]["display_name"], "Anita")
        self.assertIn("Anni", detail["item"]["aliases"])
        self.assertIn(folder, detail["item"]["folder_paths"])
        self.assertEqual(self.request("DELETE", path + "/folders?" + urlencode({"path": folder}), "admin-token")[0], 200)
        self.assertEqual(self.request("GET", f"/people/{person_id}", "read-token")[1]["item"]["folder_paths"], [])
        self.assertEqual(self.repository.list_audit_events()[0].actor_chat_id, 102)

    def test_interpretation_and_indexed_image_download(self) -> None:
        self.start_api()
        status, data = self.request("POST", "/interpret", "read-token", {"text": "show me 2 city photos from 2021"})
        self.assertEqual(status, 200)
        self.assertEqual(data["item"]["action"], "images")
        self.assertEqual(data["item"]["count"], 2)
        self.assertIn("city", data["item"]["query"])
        self.assertEqual(self.request("GET", "/image?path=../readme.txt", "read-token")[0], 404)
        path = "2021/2021-08-15_city_trip/IMG_001.jpg"
        url = "/api/v1/image?" + urlencode({"path": path})
        connection = HTTPConnection(*self.server.server_address, timeout=2)
        try:
            connection.request("GET", url, headers={"Authorization": "Bearer read-token"})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("Content-Type"), "image/jpeg")
            self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
            self.assertEqual(response.read(), (PHOTOS_ROOT / path).read_bytes())
        finally:
            connection.close()


    def test_searches_are_private_to_the_chat_and_can_be_pinned(self) -> None:
        self.start_api()
        self.request("POST", "/browse", "viewer-token", {"action": "search", "q": "city", "count": 1})
        status, data = self.request("GET", "/searches", "viewer-token")
        self.assertEqual(status, 200)
        search = data["items"][0]
        self.assertEqual((search["kind"], search["query"], search["count"]), ("images", "city", 1))
        path = f"/searches/{search['id']}"
        self.assertEqual(self.request("GET", "/searches", "admin-token"), (200, {"items": []}))
        self.assertEqual(self.request("PATCH", path, "admin-token", {"pinned": True})[0], 404)
        self.assertEqual(self.request("PATCH", path, "viewer-token", {"pinned": True})[0], 200)
        self.assertTrue(self.request("GET", "/searches?pinned=true", "viewer-token")[1]["items"][0]["pinned"])

    def test_sync_status_reports_recent_runs(self) -> None:
        self.start_api()
        self.assertEqual(self.request("GET", "/sync/runs")[0], 401)
        status, data = self.request("GET", "/sync/runs?limit=1", "read-token")
        self.assertEqual(status, 200)
        run, = data["items"]
        self.assertEqual((run["mode"], run["status"]), ("full", "succeeded"))
        self.assertEqual(run["summary"]["images_indexed"], 5)
