from __future__ import annotations

import importlib.util
import json
import shutil
import ssl
import subprocess
import tempfile
import unittest
from http.client import HTTPSConnection
from io import BytesIO
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode
from zipfile import ZipFile

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
            with open_fixture(cert, key, port=0, split_year=True) as (server, db, access_id, invitation):
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
                content_type = response.getheader("Content-Type", "")
                if content_type.startswith("image/") or content_type == "application/zip":
                    return payload
                return json.loads(payload), response.getheader("Set-Cookie")
            finally:
                connection.close()

        request("GET", "/years", 401)
        request("GET", "/album-tags", 401)
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

        for offset, branch in ((0, 1), (30, 2)):
            page, _ = request("GET", "/folders", params={"q": 2003, "limit": 31, "offset": offset})
            self.assertEqual(len(page["items"]), 31 if offset == 0 else 1)
            path = f"2003({branch})/album_00"
            self.assertEqual(page["items"][0]["path"], path)
            gallery, _ = request("GET", "/album-images", params={"path": path})
            self.assertEqual([item["path"] for item in gallery["items"]], [f"{path}/Photo_01.jpg"])

        selection = {"paths": [photo, first["items"][0]["path"]]}
        request("POST", "/photo-export", 413, body={"album": album})
        large_album = {"album": album, "large": True}
        archive = Path(db).parent / "archive"
        disconnected = archive.with_name("disconnected")
        archive.rename(disconnected)
        uncached = {"path": second["items"][1]["path"]}
        cover = {"path": "2003(2)/album_00"}
        request("GET", "/thumbnail", 404, params=uncached)
        request("GET", "/album-cover", 404, params=cover)
        cached = request("GET", "/thumbnail", params={"path": photo})
        self.assertTrue(cached.startswith(b"\xff\xd8"))
        request("GET", "/image", 404, params={"path": photo})
        request("POST", "/photo-export", 404, body=selection)
        request("POST", "/photo-export", 404, body=large_album)
        offline, _ = request("GET", "/album-images", params={"path": album, "limit": 30, "offset": 30})
        self.assertEqual(offline, second)
        catalog, _ = request("GET", "/album-tags", params={"limit": 1})
        self.assertEqual(len(catalog["items"]), 1)
        self.assertEqual(catalog["next_offset"], 1)
        next_tags, _ = request("GET", "/album-tags", params={"limit": 1, "offset": 1})
        self.assertNotEqual(catalog["items"], next_tags["items"])
        matches, _ = request("GET", "/folders", params={"tag": "PLÁYA"})
        self.assertEqual([item["path"] for item in matches["items"]], [album])
        month, _ = request("GET", "/folders", params={"tag": "2024-07"})
        self.assertEqual([item["path"] for item in month["items"]], [album])
        no_match, _ = request("GET", "/folders", params={"tag": "play"})
        self.assertEqual(no_match["items"], [])
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

        # Album membership is separate from confirmed people and tags on individual photos.
        photos = []
        for image in second["items"]:
            tags, _ = request("GET", "/photo-tags", params={"path": image["path"]})
            entry = tags["items"][0]
            photos.append({"path": entry["path"], "identity": entry["identity"]})
        request("PATCH", "/photo-tags", body={"photos": photos[:2], "add_people": [ana["id"]]})
        request("PATCH", "/photo-tags", body={"photos": photos[1:], "manual_add": ["Romería"]})
        filters = {"person": "Anita", "tag": "ROMERIA"}
        combined, _ = request("GET", "/confirmed-images", params=filters)
        self.assertEqual([item["path"] for item in combined["items"]], [photos[1]["path"]])
        request("PATCH", "/photo-tags", body={"photos": photos[1:2], "manual_remove": ["romeria"]})
        combined, _ = request("GET", "/confirmed-images", params=filters)
        self.assertEqual(combined["items"], [])
        confirmed, _ = request("GET", "/confirmed-images", params={"person": "Anita"})
        self.assertCountEqual([item["path"] for item in confirmed["items"]], [item["path"] for item in photos[:2]])

        disconnected.rename(archive)
        payload = request("POST", "/photo-export", body=selection)
        with ZipFile(BytesIO(payload)) as exported:
            self.assertEqual(exported.namelist(), ["01-Photo_31.jpg", "02-Photo_01.jpg"])
            originals = [request("GET", "/image", params={"path": path}) for path in selection["paths"]]
            self.assertEqual([exported.read(name) for name in exported.namelist()], originals)
        with ZipFile(BytesIO(request("POST", "/photo-export", body=large_album))) as exported:
            self.assertEqual(exported.namelist(), [f"{number:02d}-Photo_{number:02d}.jpg" for number in range(1, 34)])
            for entry, item in zip(exported.namelist(), first["items"] + second["items"]):
                self.assertEqual(exported.read(entry), (archive / item["path"]).read_bytes())
        self.assertTrue(request("GET", "/thumbnail", params=uncached).startswith(b"\xff\xd8"))
        self.assertTrue(request("GET", "/album-cover", params=cover).startswith(b"\xff\xd8"))

        self.assertTrue(FamilyAccess(Repository(db)).revoke(access_id))
        request("GET", "/years", 401)
        request("POST", "/photo-export", 401, body=large_album)
