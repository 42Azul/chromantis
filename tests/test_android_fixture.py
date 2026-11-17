from __future__ import annotations

import importlib.util
import json
import shutil
import ssl
import subprocess
import tempfile
import unittest
from http.client import HTTPSConnection
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode

from chromantis.db.family_access import FamilyAccess
from chromantis.db.repository import Repository


@unittest.skipUnless(shutil.which("openssl") and importlib.util.find_spec("PIL"), "Requires OpenSSL and Pillow.")
class AndroidFixtureTests(unittest.TestCase):
    def test_family_smoke_over_https_with_disconnection_and_revocation(self):
        from android_fixture import open_fixture

        with tempfile.TemporaryDirectory() as temporary:
            cert, key = Path(temporary) / "cert.pem", Path(temporary) / "key.pem"
            subprocess.run(
                [
                    "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                    "-subj", "/CN=Chromantis-Fixture", "-addext", "subjectAltName=IP:127.0.0.1",
                    "-keyout", str(key), "-out", str(cert),
                ],
                check=True, capture_output=True, timeout=15,
            )
            tls = ssl.create_default_context(cafile=str(cert))
            with open_fixture(cert, key, port=0) as (server, db, access_id, invitation):
                thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
                thread.start()
                try:
                    self.exercise_fixture(server.server_port, tls, db, access_id, invitation)
                finally:
                    server.shutdown()
                    thread.join(timeout=3)

    def exercise_fixture(self, port, tls, db, access_id, invitation):
        cookie = None

        def request(method, route, expected=200, *, params=None, body=None):
            headers = {"Origin": f"https://127.0.0.1:{port}"}
            if cookie:
                headers["Cookie"] = cookie
            if body is not None:
                headers["Content-Type"] = "application/json"
            if params is not None:
                route += "?" + urlencode(params)
            connection = HTTPSConnection("127.0.0.1", port, timeout=3, context=tls)
            try:
                connection.request(method, "/api/v1" + route, json.dumps(body) if body is not None else None, headers)
                response = connection.getresponse()
                payload = response.read()
                self.assertEqual(response.status, expected, (method, route))
                if response.getheader("Content-Type", "").startswith("image/"):
                    return payload
                return json.loads(payload), response.getheader("Set-Cookie")
            finally:
                connection.close()

        request("GET", "/years", 401)
        _, session = request("POST", "/family/session", body={"code": invitation})
        self.assertIn("Secure", session.split("; "))
        request("POST", "/family/session", 401, body={"code": invitation})
        cookie = session.split(";", 1)[0]

        years, _ = request("GET", "/years")
        self.assertIn(2024, [item["year"] for item in years["items"]])
        folders, _ = request("GET", "/folders", params={"q": 2024})
        album = folders["items"][0]["path"]
        self.assertEqual(album, "2024/2024-07-01_playa")
        first, _ = request("GET", "/album-images", params={"path": album, "limit": 30})
        self.assertEqual((len(first["items"]), first["next_offset"]), (30, 30))
        second, _ = request("GET", "/album-images", params={"path": album, "limit": 30, "offset": 30})
        self.assertEqual((len(second["items"]), second["next_offset"]), (3, None))
        photo = second["items"][0]["path"]
        for route in ("/thumbnail", "/image"):
            self.assertTrue(request("GET", route, params={"path": photo}).startswith(b"\xff\xd8"))

        archive = Path(db).parent / "archive"
        archive.rename(archive.with_name("disconnected"))
        request("GET", "/image", 404, params={"path": photo})
        offline, _ = request("GET", "/album-images", params={"path": album, "limit": 30, "offset": 30})
        self.assertEqual(offline, second)
        people, _ = request("GET", "/album-review/people")
        ana = next(person for person in people["items"] if "Anita" in person["aliases"])
        review, _ = request("GET", "/album-review", params={"path": album})
        current = review["item"]
        request("POST", "/album-review", body={
            "id": current["id"], "path": album, "revision": current["revision"],
            "add_people": [ana["id"]], "decisions": {"playa": "playa"},
        })
        matches, _ = request("GET", "/folders", params={
            "q": "fotos de la playa con Anita antes de 2025", "filters": 1,
        })
        self.assertEqual([item["path"] for item in matches["items"]], [album])
        self.assertEqual([item["kind"] for item in matches["filters"]["active"]], ["year", "person"])

        self.assertTrue(FamilyAccess(Repository(db)).revoke(access_id))
        request("GET", "/years", 401)
