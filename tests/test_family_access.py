from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from http.cookies import SimpleCookie
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode

from chromantis.api.server import ApiServer, make_api_handler
from chromantis.app import ApplicationService, AuthOperationError
from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser


ALBUM = "2024/2024-03-03_beach_trip"
PHOTO = ALBUM + "/synthetic.jpg"
REPO = Path(__file__).resolve().parents[1]


class FamilyAccessTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db_path = str(Path(temp.name) / "index.db")
        self.repository = Repository(self.db_path)
        self.repository.init_schema()
        record = PathParser().parse_image_path("/synthetic", PHOTO, 4, None)
        with self.repository.write_transaction() as connection:
            self.repository.upsert_image_record(connection, record, "test")
        self.app = ApplicationService(self.repository, static_owner_chat_ids=(10,))
        self.ana = self.repository.create_person("Ana")
        self.start_server()

    def start_server(self, *, protected=True):
        server = ApiServer(("127.0.0.1", 0), make_api_handler(
            self.app,
            api_chat_tokens=((10, "owner-example"),) if protected else (),
            image_fetcher=lambda path: b"test",
        ))
        self.address = server.server_address
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)

    def request(self, method, path, *, body=None, cookie=None, origin=True, token=None,
                content_type="application/json"):
        connection = HTTPConnection(*self.address, timeout=3)
        headers = {}
        if body is not None:
            headers["Content-Type"] = content_type
        if origin:
            headers["Origin"] = f"http://127.0.0.1:{self.address[1]}" if origin is True else origin
        if cookie:
            headers["Cookie"] = cookie
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            connection.request(method, "/api/v1" + path, json.dumps(body) if body is not None else None, headers)
            response = connection.getresponse()
            return response.status, response.getheader("Set-Cookie"), response.read()
        finally:
            connection.close()

    def enter(self, code):
        status, header, body = self.request("POST", "/family/session", body={"code": code})
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body), {"ok": True})
        self.assertIn("HttpOnly", header)
        self.assertIn("SameSite=Strict", header)
        self.assertIn("Max-Age=7776000", header)
        self.assertNotIn(code, header)
        return header.split(";", 1)[0]

    def cli(self, *arguments):
        env = dict(os.environ, SOURCE_TYPE="local", SOURCE_ROOT="/synthetic", SQLITE_PATH=self.db_path,
                   API_CHAT_TOKENS='{"10":"owner-example"}', API_TOKEN="")
        return subprocess.run(
            [sys.executable, str(REPO / "scripts" / "family_access.py"), *arguments],
            cwd=Path(self.db_path).parent, env=env, check=True, capture_output=True, text=True,
        ).stdout

    def test_web_only_curator_can_review_and_search_until_owner_revokes(self):
        output = self.cli("invite", "Familiar de prueba")
        code = output.splitlines()[-1]
        cookie = self.enter(code)
        secret = SimpleCookie(cookie)["chromantis_family"].value
        with self.repository.session() as connection:
            (row,) = connection.execute("SELECT id, secret_hash FROM family_access").fetchall()
            self.assertNotEqual(row["secret_hash"], secret)
            self.assertNotEqual(row["secret_hash"], code)
        identity = row["id"]
        self.assertIn("sesión", self.cli("list"))
        self.assertNotIn(secret, self.cli("list"))
        for _ in range(2):
            status, _, body = self.request("GET", "/auth/me", cookie=cookie)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["item"]["auth_mode"], "family")
        status, _, body = self.request("GET", "/album-review", cookie=cookie)
        self.assertEqual(status, 200)
        item = json.loads(body)["item"]
        data = {key: item[key] for key in ("path", "id", "revision")}
        data.update(add_people=[self.ana.id], decisions={"playa": "playa", "viaje": None})
        self.assertEqual(self.request("POST", "/album-review", body=data, cookie=cookie)[0], 200)
        status, _, body = self.request("GET", "/folders?q=Ana", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["items"][0]["path"], ALBUM)
        preview = "/image?" + urlencode({"path": PHOTO})
        self.assertEqual(self.request("GET", preview, cookie=cookie)[0], 200)
        for path in ("/admin/chats", "/admin/people", "/auth/preferences", "/browse", "/searches"):
            self.assertEqual(self.request("GET", path, cookie=cookie)[0], 403)
        self.assertEqual(self.request("GET", "/admin/chats", token="owner-example", cookie=cookie)[0], 200)
        self.assertEqual(self.request("GET", "/auth/me", token="wrong", cookie=cookie)[0], 401)
        self.assertEqual(self.request("POST", "/family/session", body={"code": code})[0], 401)
        audit = next(event for event in self.repository.list_audit_events() if event.action == "save_album_review")
        self.assertIsNone(audit.actor_chat_id)
        self.assertEqual(json.loads(audit.details_json)["family_access_id"], identity)
        self.cli("revoke", str(identity))
        for method, path in (("GET", "/auth/me"), ("GET", preview), ("POST", "/album-review")):
            self.assertEqual(self.request(method, path, cookie=cookie, body=data if method == "POST" else None)[0], 401)

    def test_csrf_checks_before_redeeming_and_saving(self):
        _, code = self.app.family_access.invite("Móvil")
        for origin, content_type in ((False, "application/json"), ("http://untrusted.test", "application/json"),
                                     (True, "text/plain")):
            self.assertEqual(self.request(
                "POST", "/family/session", body={"code": code}, origin=origin, content_type=content_type
            )[0], 403)
        cookie = self.enter(code)
        self.assertEqual(self.request("POST", "/album-review", cookie=cookie, body={}, origin=False)[0], 403)
        self.assertEqual(self.request(
            "POST", "/album-review", cookie=cookie, body={}, content_type="text/plain"
        )[0], 403)
        self.assertEqual(self.request("DELETE", "/family/session", cookie=cookie, origin=False)[0], 403)
        status, header, _ = self.request("DELETE", "/family/session", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn("Max-Age=0", header)
        self.assertEqual(self.request("GET", "/auth/me", cookie=cookie)[0], 401)

    def test_expired_invite_and_session_and_revoked_inflight_write(self):
        first, expired = self.app.family_access.invite("Viejo")
        with self.repository.session() as connection:
            connection.execute("UPDATE family_access SET expires_at = '2000' WHERE id = ?", (first,))
        self.assertEqual(self.request("POST", "/family/session", body={"code": expired})[0], 401)
        identity, code = self.app.family_access.invite("Vigente")
        self.assertEqual(len(self.app.family_access.list()), 1)
        cookie = self.enter(code)
        secret = SimpleCookie(cookie)["chromantis_family"].value
        actor = self.app.family_access.resolve(secret)
        item = self.app.get_album_review(actor)
        with self.repository.session() as connection:
            connection.execute("UPDATE family_access SET expires_at = '2000' WHERE id = ?", (identity,))
        self.assertEqual(self.request("GET", "/album-review", cookie=cookie)[0], 401)
        with self.assertRaises(AuthOperationError) as error:
            self.app.save_album_review(
                actor, item["path"], item["id"], item["revision"], add_people={self.ana.id},
                remove_people=set(), new_person=None, decisions={}, manual_add=set(), manual_remove=set(),
            )
        self.assertEqual(error.exception.status, 401)
        self.assertEqual(self.app.search_folders("Ana"), [])

    def test_redeeming_is_atomic(self):
        _, code = self.app.family_access.invite("Compartida")
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(self.app.family_access.redeem, (code, code)))
        self.assertEqual(sum(result is not None for result in results), 1)

    def test_legacy_album_index_migrates_and_unprotected_api_cannot_issue_sessions(self):
        with self.repository.session() as connection:
            connection.execute("DROP TABLE family_access")
        self.repository.init_schema()
        self.assertEqual(self.app.get_album_review(10)["path"], ALBUM)
        _, code = self.app.family_access.invite("Una invitación")
        self.start_server(protected=False)
        self.assertEqual(self.request("POST", "/family/session", body={"code": code})[0], 403)
        self.assertEqual(self.request("GET", "/folders?q=beach")[0], 200)
        self.assertEqual(self.app.family_access.list()[0]["kind"], "invite")


if __name__ == "__main__":
    unittest.main()
