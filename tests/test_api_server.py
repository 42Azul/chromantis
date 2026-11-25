from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from email.parser import BytesParser
from http.client import HTTPConnection
from io import BytesIO
from zipfile import ZipFile
from threading import Event, Thread
from time import monotonic, sleep
from unittest.mock import Mock
from urllib.parse import urlencode
import unittest
from pathlib import Path

from chromantis.api.server import ApiServer, handle_api_get, make_api_handler
from chromantis.app import ApplicationService
from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser
from chromantis.source import ArchiveScanner, LocalArchiveSource
from chromantis.source.scanner import ScanBusy
from chromantis.source.adapters import ArchiveReadLimit


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

    def test_cancelled_image_response_does_not_raise(self) -> None:
        write = make_api_handler(self.app_service)._write
        for boundary in ("end_headers", "wfile.write"):
            with self.subTest(boundary=boundary):
                handler = Mock()
                handler.configure_mock(**{boundary + ".side_effect": BrokenPipeError})
                write(handler, 200, b"synthetic", "image/jpeg")
        handler = Mock()
        handler.wfile.write.side_effect = OSError("unexpected write error")
        with self.assertRaisesRegex(OSError, "unexpected write error"):
            write(handler, 200, b"synthetic", "image/jpeg")

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


    def start_api(self, thumbnails=None, start_index_scan=None, export_reader=None) -> None:
        self.repository.authorize_chat(102, role="admin")
        self.repository.authorize_chat(103, role="viewer")
        self.repository.authorize_chat(104, role="viewer")
        self.server = ApiServer(("127.0.0.1", 0), make_api_handler(
            self.app_service, api_token="read-token",
            api_chat_tokens=((101, "owner-token"), (102, "admin-token"), (103, "viewer-token")),
            image_fetcher=LocalArchiveSource(str(PHOTOS_ROOT)).read_bytes,
            deployment_info={"source_type": "local", "enrichment_search": False, "query_interpreter": "rules"},
            thumbnails=thumbnails,
            start_index_scan=start_index_scan,
            export_reader=export_reader,
        ))
        thread = Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(self.server.shutdown)

    def request(
        self, method: str, path: str, token: str | None = None, body: object = None,
        *, family_secret: str | None = None,
    ) -> tuple[int, dict]:
        connection = HTTPConnection(*self.server.server_address, timeout=2)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        if family_secret:
            host, port = self.server.server_address
            headers.update({
                "Cookie": f"chromantis_family={family_secret}",
                "Origin": f"http://{host}:{port}",
                "Content-Type": "application/json",
            })
        try:
            connection.request(
                method, "/api/v1" + path, None if body is None else json.dumps(body), headers
            )
            response = connection.getresponse()
            self.assertEqual(response.getheader("Cache-Control"), "no-store")
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_owner_starts_one_incremental_scan_and_can_see_the_result(self) -> None:
        root = Path(self.temp_dir.name) / "archive"
        shutil.copytree(PHOTOS_ROOT, root)
        album = root / "2024" / "garden"
        album.mkdir(exist_ok=True, parents=True)
        (album / "flower.jpg").write_bytes(b"fixture")
        entered, release = Event(), Event()

        class SlowListing(LocalArchiveSource):
            def iter_entries(self):
                entered.set()
                if not release.wait(5):
                    raise OSError("Test did not release listing")
                yield from super().iter_entries()

            def read_bytes(self, *args, **kwargs):
                raise AssertionError("Indexing must not open photos")

        scanner = ArchiveScanner(SlowListing(str(root)), self.repository, PathParser())
        self.start_api(start_index_scan=scanner.start_incremental)
        self.addCleanup(release.set)
        for token, denied in ((None, 401), ("read-token", 403), ("viewer-token", 403), ("admin-token", 403)):
            self.assertEqual(self.request("POST", "/sync/runs", token)[0], denied)
        _, code = self.app_service.family_access.invite("Synthetic curator")
        secret = self.app_service.family_access.redeem(code)
        self.assertIsNotNone(secret)
        self.assertEqual(self.request("POST", "/sync/runs", family_secret=secret)[0], 403)
        self.assertEqual(self.request("POST", "/sync/runs", "owner-token", {"path": "/tmp"})[0], 400)
        self.assertFalse(entered.is_set())

        status, reply = self.request("POST", "/sync/runs", "owner-token")
        self.assertEqual(status, 202)
        self.assertTrue(entered.wait(2))
        run_id = reply["item"]["id"]
        try:
            self.assertEqual(self.request("POST", "/sync/runs", "owner-token")[0], 409)
            cli = ArchiveScanner(LocalArchiveSource(str(root)), self.repository, PathParser())
            with self.assertRaises(ScanBusy):
                cli.scan(incremental=True)
            separate_process = subprocess.run(
                [sys.executable, "-c", """
import sys
from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser
from chromantis.source import ArchiveScanner, LocalArchiveSource
from chromantis.source.scanner import ScanBusy
from chromantis.source.adapters import ArchiveReadLimit

scanner = ArchiveScanner(LocalArchiveSource(sys.argv[1]), Repository(sys.argv[2]), PathParser())
try:
    scanner.scan(incremental=True)
except ScanBusy:
    sys.exit(17)
""", str(root), self.repository.sqlite_path],
                capture_output=True, text=True, timeout=3,
            )
            self.assertEqual(separate_process.returncode, 17, separate_process.stderr)
            latest = self.request("GET", "/sync/runs?limit=1", "owner-token")[1]["items"][0]
            self.assertEqual((latest["id"], latest["status"]), (run_id, "running"))
        finally:
            release.set()
        latest = self.wait_for_scan(run_id)
        self.assertEqual((latest["mode"], latest["status"]), ("incremental", "succeeded"))
        albums = self.request("GET", "/folders?q=garden", "read-token")[1]["items"]
        self.assertEqual([item["path"] for item in albums], ["2024/garden"])

    def test_background_scan_reports_failure_and_keeps_previous_index(self) -> None:
        source = LocalArchiveSource(str(Path(self.temp_dir.name) / "disconnected"))
        scanner = ArchiveScanner(source, self.repository, PathParser())
        self.start_api(start_index_scan=scanner.start_incremental)
        before = self.repository.archive_index_status()["indexed_at"]
        status, reply = self.request("POST", "/sync/runs", "owner-token")
        self.assertEqual(status, 202)
        failed = self.wait_for_scan(reply["item"]["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(self.repository.archive_index_status()["indexed_at"], before)
        self.assertEqual(self.repository.get_index_stats().images, 5)

    def wait_for_scan(self, run_id: int) -> dict:
        deadline = monotonic() + 3
        while monotonic() < deadline:
            status, reply = self.request("GET", "/sync/runs?limit=1", "owner-token")
            self.assertEqual(status, 200)
            latest = reply["items"][0]
            self.assertEqual(latest["id"], run_id)
            if latest["status"] != "running":
                return latest
            sleep(0.01)
        self.fail(f"Index scan {run_id} did not finish")

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

    def test_export_contains_only_selected_originals_and_requires_authentication(self) -> None:
        source = LocalArchiveSource(str(PHOTOS_ROOT))
        reader = Mock(side_effect=lambda path, limit: source.read_bytes(path, max_bytes=limit))
        self.start_api(export_reader=reader)
        path = "2021/2021-08-15_city_trip/IMG_001.jpg"
        route = "/photo-export"
        self.assertEqual(self.request("POST", route, body={"paths": [path]})[0], 401)
        self.assertEqual(self.request("POST", route, "read-token", {"paths": [path] * 21})[0], 400)
        self.assertEqual(self.request("POST", route, "read-token", {"paths": [path, "../missing.jpg"]})[0], 404)
        reader.assert_not_called()
        connection = HTTPConnection(*self.server.server_address, timeout=2)
        self.addCleanup(connection.close)
        connection.request("POST", "/api/v1" + route, json.dumps({"paths": [path, path]}),
                           {"Authorization": "Bearer read-token", "Content-Type": "application/json"})
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        self.assertEqual(response.getheader("Content-Type"), "application/zip")
        with ZipFile(BytesIO(response.read())) as archive:
            self.assertEqual(archive.namelist(), ["01-IMG_001.jpg"])
            self.assertEqual(archive.read("01-IMG_001.jpg"), (PHOTOS_ROOT / path).read_bytes())
        reader.assert_called_once_with(path, 16 * 1024 * 1024)
        reader.side_effect = ArchiveReadLimit()
        self.assertEqual(self.request("POST", route, "read-token", {"paths": [path]})[0], 413)
        reader.side_effect = OSError()
        self.assertEqual(self.request("POST", route, "read-token", {"paths": [path]})[0], 502)

    def test_multipart_export_keeps_original_order_and_respects_export_limits(self) -> None:
        source = LocalArchiveSource(str(PHOTOS_ROOT))
        reader = Mock(side_effect=lambda path, limit: source.read_bytes(path, max_bytes=limit))
        self.start_api(export_reader=reader)
        paths = [f"2021/2021-08-15_city_trip/IMG_{number:03d}.jpg" for number in (2, 1)]
        data = {"paths": [*paths, paths[0]], "format": "multipart"}
        self.assertEqual(self.request("POST", "/photo-export", body=data)[0], 401)
        self.assertEqual(self.request("POST", "/photo-export", "read-token", {**data, "format": "other"})[0], 400)
        reader.assert_not_called()
        connection = HTTPConnection(*self.server.server_address, timeout=2)
        self.addCleanup(connection.close)
        connection.request("POST", "/api/v1/photo-export", json.dumps(data),
                           {"Authorization": "Bearer read-token", "Content-Type": "application/json"})
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        header = response.getheader("Content-Type")
        message = BytesParser().parsebytes(f"Content-Type: {header}\r\n\r\n".encode() + response.read())
        parts = message.get_payload()
        self.assertEqual([part.get_content_type() for part in parts], ["image/jpeg", "image/jpeg"])
        originals = [(PHOTOS_ROOT / path).read_bytes() for path in paths]
        self.assertEqual([part.get_payload(decode=True) for part in parts], originals)
        self.assertEqual([call.args for call in reader.call_args_list],
                         [(paths[0], 16 * 1024 * 1024), (paths[1], 16 * 1024 * 1024 - len(originals[0]))])
        reader.side_effect = [originals[0], ArchiveReadLimit()]
        self.assertEqual(self.request("POST", "/photo-export", "read-token", data)[0], 413)

    def test_export_rejects_empty_or_oversized_albums_before_reading_originals(self) -> None:
        reader = Mock()
        self.start_api(export_reader=reader)
        route = "/photo-export"
        self.assertEqual(self.request("POST", route, "read-token", {"album": "2099/missing"})[0], 404)
        self.assertEqual(self.request("POST", route, "read-token", {"album": "x", "paths": ["y"]})[0], 400)
        with unittest.mock.patch.object(self.app_service, "images_in_folder", return_value=[None] * 21) as lookup:
            self.assertEqual(self.request("POST", route, "read-token", {"album": "2021/fixture"})[0], 413)
            lookup.assert_called_once_with("2021/fixture", limit=21)
        reader.assert_not_called()

    def test_private_album_link_is_scoped_expiring_and_revocable(self) -> None:
        class Thumbnails:
            def get(self, path, fingerprint):
                return ("preview:" + path).encode()

        self.start_api(thumbnails=Thumbnails())
        album = "2021/2021-08-15_city_trip"
        photo = album + "/IMG_001.jpg"
        other = "2019/2019-07-10_beach_day/IMG_0001.jpg"
        review = self.app_service.get_album_review(101, path=album)
        self.app_service.edit_album_context(
            101, album, review["id"], review["context_revision"],
            {"title": "Viaje a la ciudad", "place": "Madrid", "note": "Fin de semana familiar."},
        )
        self.assertEqual(self.request("POST", "/album-shares", "viewer-token",
                                      {"path": album})[0], 403)
        status, created = self.request(
            "POST", "/album-shares", "owner-token", {"path": album, "ttl_days": 2}
        )
        self.assertEqual(status, 201)
        share = created["item"]
        secret = share["url"].removeprefix("/share/")
        self.assertEqual(len(secret), 43)
        with self.repository.session() as connection:
            row = connection.execute(
                "SELECT secret_hash FROM album_shares WHERE id = ?", (share["id"],)
            ).fetchone()
            self.assertNotEqual(row["secret_hash"], secret)

        status, album_payload = self.request("GET", f"/shared/{secret}")
        self.assertEqual((status, album_payload["item"]["title"]), (200, "Viaje a la ciudad"))
        self.assertEqual(album_payload["item"]["event_date"], "2021-08-15")
        self.assertEqual(album_payload["item"]["place"], "Madrid")
        self.assertEqual(album_payload["item"]["note"], "Fin de semana familiar.")
        self.assertTrue(album_payload["items"])
        self.assertNotIn("path", album_payload["item"])
        self.assertEqual(self.request("GET", "/folders?q=city")[0], 401)
        self.assertEqual(self.request(
            "GET", f"/shared/{secret}/image?" + urlencode({"path": other})
        )[0], 404)
        self.assertEqual(self.request(
            "GET", f"/shared/{secret}/thumbnail?" + urlencode({"path": other})
        )[0], 404)
        self.assertEqual(self.request("GET", "/collections")[0], 401)
        self.assertEqual(self.request("GET", "/album-review")[0], 401)

        connection = HTTPConnection(*self.server.server_address, timeout=2)
        try:
            connection.request(
                "GET", f"/api/v1/shared/{secret}/image?" + urlencode({"path": photo})
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), (PHOTOS_ROOT / photo).read_bytes())
        finally:
            connection.close()
        connection = HTTPConnection(*self.server.server_address, timeout=2)
        try:
            connection.request(
                "GET", f"/api/v1/shared/{secret}/thumbnail?" + urlencode({"path": photo})
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), ("preview:" + photo).encode())
        finally:
            connection.close()

        listed = self.request("GET", "/album-shares", "owner-token")[1]["items"]
        self.assertEqual([item["id"] for item in listed], [share["id"]])
        self.assertNotIn(secret, json.dumps(listed))
        self.assertEqual(self.request(
            "DELETE", f"/album-shares/{share['id']}", "owner-token"
        )[0], 200)
        self.assertEqual(self.request("GET", f"/shared/{secret}")[0], 404)
        self.assertEqual(self.request(
            "GET", f"/shared/{secret}/image?" + urlencode({"path": photo})
        )[0], 404)
        self.assertEqual(self.request(
            "GET", f"/shared/{secret}/thumbnail?" + urlencode({"path": photo})
        )[0], 404)

    def test_album_share_expiry_is_checked_on_every_request(self) -> None:
        self.start_api()
        album = "2021/2021-08-15_city_trip"
        _, created = self.request(
            "POST", "/album-shares", "owner-token", {"path": album}
        )
        secret = created["item"]["url"].removeprefix("/share/")
        self.assertEqual(self.request("GET", f"/shared/{secret}")[0], 200)
        self.assertEqual(self.request("GET", f"/shared/{secret}?offset=invalid")[0], 400)
        with self.repository.session() as connection:
            connection.execute(
                "UPDATE album_shares SET expires_at = '2000-01-01T00:00:00+00:00'"
            )
        self.assertEqual(self.request("GET", f"/shared/{secret}")[0], 404)
        self.assertEqual(self.request(
            "GET", "/album-shares", "owner-token"
        )[1]["items"], [])


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


    def test_browser_assets_are_public_and_configuration_requires_admin(self) -> None:
        self.start_api()
        for path, media_type, marker in (
            ("/", "text/html", b'id="login-form"'),
            ("/ui/app.js", "text/javascript", "Vista previa no generada".encode()),
            ("/ui/style.css", "text/css", b'@media (max-width: 420px)'),
        ):
            connection = HTTPConnection(*self.server.server_address, timeout=2)
            try:
                connection.request("GET", path)
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertTrue(response.getheader("Content-Type").startswith(media_type))
                self.assertIn("connect-src 'self'", response.getheader("Content-Security-Policy"))
                asset = response.read()
                self.assertIn(marker, asset)
                self.assertNotIn(b"owner-token", asset)
            finally:
                connection.close()
        connection = HTTPConnection(*self.server.server_address, timeout=2)
        try:
            connection.request("GET", "/share/" + "a" * 43)
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertIn(b'id="shared-album"', response.read())
        finally:
            connection.close()
        self.assertEqual(self.request("GET", "/admin/config", "viewer-token")[0], 403)
        status, result = self.request("GET", "/admin/config", "owner-token")
        self.assertEqual(status, 200)
        self.assertEqual(result["item"]["source_type"], "local")
        self.assertEqual(
            self.request("PATCH", "/auth/preferences", "viewer-token", {"language": "es"}),
            (200, {"item": {"language": "es"}}),
        )
        self.assertEqual(self.repository.get_chat_language(103), "es")
