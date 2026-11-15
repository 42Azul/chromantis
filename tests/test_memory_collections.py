from __future__ import annotations

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from unittest.mock import Mock

from chromantis.api.server import ApiServer, make_api_handler
from chromantis.app import ApplicationService
from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser
from chromantis.source import ArchiveScanner, LocalArchiveSource


ALBUM = "2024/2024-09-01_beach"
PHOTO = ALBUM + "/synthetic.jpg"


class CollectionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "photos"
        self.photo = self.source / PHOTO
        self.photo.parent.mkdir(parents=True)
        self.photo.write_bytes(b"synthetic photo")
        self.repository = Repository(str(self.root / "index.db"))
        self.repository.init_schema()
        self.scanner = ArchiveScanner(LocalArchiveSource(str(self.source)), self.repository, PathParser())
        self.scanner.scan()
        self.app = ApplicationService(
            self.repository, static_owner_chat_ids=(1, 2), static_viewer_chat_ids=(3,),
        )
        self.repository.authorize_chat(4, role="admin")
        self.media = Mock(side_effect=AssertionError("Collection management must use the index only"))
        server = ApiServer(("127.0.0.1", 0), make_api_handler(
            self.app, api_token="read-token", api_chat_tokens=(
                (1, "owner-token"), (2, "other-owner"), (3, "viewer-token"), (4, "admin-token"),
            ), image_fetcher=self.media,
        ))
        self.address = server.server_address
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)

    def request(self, method, path="/collections", body=None, *, token="owner-token", cookie=None):
        connection = HTTPConnection(*self.address, timeout=3)
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if cookie:
            headers["Cookie"] = cookie
        if body is not None:
            headers["Content-Type"] = "application/json"
        try:
            connection.request(method, "/api/v1" + path, json.dumps(body) if body is not None else None, headers)
            response = connection.getresponse()
            self.assertEqual(response.getheader("Cache-Control"), "no-store")
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def create(self, name="Recuerdos"):
        status, result = self.request("POST", body={"name": name, "entry": {"kind": "folder", "path": ALBUM}})
        self.assertEqual(status, 201, result)
        return result["item"]

    def test_create_reopen_remove_and_delete_keep_the_archive_read_only(self):
        collection = self.create()
        path = f"/collections/{collection['id']}"
        self.assertEqual(self.request("POST", path + "/entries", {"kind": "image", "path": PHOTO})[0], 200)
        self.scanner.scan()
        self.assertEqual(self.request("GET")[1]["items"], [
            {"id": collection["id"], "name": "Recuerdos", "count": 2},
        ])
        item = self.request("GET", path)[1]["item"]
        self.assertEqual([entry["path"] for entry in item["entries"]], [ALBUM, PHOTO])
        self.assertTrue(all(entry["available"] for entry in item["entries"]))
        self.assertEqual(self.request("DELETE", path + f"/entries/{item['entries'][1]['id']}")[0], 200)
        self.assertEqual(len(self.request("GET", path)[1]["item"]["entries"]), 1)
        self.assertEqual(self.request("DELETE", path)[0], 200)
        self.assertEqual(self.request("GET", path)[0], 404)
        self.assertEqual(self.photo.read_bytes(), b"synthetic photo")
        self.media.assert_not_called()

    def test_owner_isolation_and_existing_family_permissions(self):
        collection = self.create()
        path = f"/collections/{collection['id']}"
        for token, expected in (("read-token", 401), ("viewer-token", 403), ("admin-token", 403), (None, 401)):
            self.assertEqual(self.request("GET", path, token=token)[0], expected)
        self.assertEqual(self.request("GET", token="other-owner")[1]["items"], [])
        self.assertEqual(self.request("GET", path, token="other-owner")[0], 404)
        self.assertEqual(self.request("DELETE", path, token="other-owner")[0], 404)
        entry = collection["entries"][0]
        self.assertEqual(self.request("DELETE", path + f"/entries/{entry['id']}", token="other-owner")[0], 404)
        self.assertEqual(self.request("POST", path + "/entries", {"kind": "image", "path": PHOTO},
                                      token="other-owner")[0], 404)
        _, code = self.app.family_access.invite("synthetic")
        cookie = "chromantis_family=" + self.app.family_access.redeem(code)
        self.assertEqual(self.request("GET", path, token=None, cookie=cookie)[0], 403)
        self.assertEqual(self.request("GET", "/folders?q=beach", token=None, cookie=cookie)[0], 200)

    def test_invalid_creation_rolls_back_and_concurrent_add_is_idempotent(self):
        status, _ = self.request("POST", body={"name": "Missing", "entry": {"kind": "image", "path": "../secret"}})
        self.assertEqual(status, 400)
        self.assertEqual(self.request("GET")[1]["items"], [])
        collection = self.create("Álbum familiar")
        self.assertEqual(self.request("POST", body={"name": "album familiar"})[0], 400)
        path = f"/collections/{collection['id']}"
        with ThreadPoolExecutor(3) as workers:
            results = list(workers.map(lambda _: self.request(
                "POST", path + "/entries", {"kind": "image", "path": PHOTO},
            ), range(3)))
        self.assertEqual([status for status, _ in results], [200] * 3)
        self.assertEqual(len(self.request("GET", path)[1]["item"]["entries"]), 2)
        self.media.assert_not_called()

    def test_stale_reference_survives_reindex_and_different_archive_root(self):
        collection = self.create()
        path = f"/collections/{collection['id']}"
        self.assertEqual(self.request("POST", path + "/entries", {"kind": "image", "path": PHOTO})[0], 200)
        other_root = self.root / "other-photos"
        other_photo = other_root / PHOTO
        other_photo.parent.mkdir(parents=True)
        other_photo.write_bytes(b"another fixture")
        ArchiveScanner(LocalArchiveSource(str(other_root)), self.repository, PathParser()).scan()
        stale = self.request("GET", path)[1]["item"]
        self.assertEqual([entry["path"] for entry in stale["entries"]], [ALBUM, PHOTO])
        self.assertTrue(all(not entry["available"] for entry in stale["entries"]))
        self.scanner.scan()
        self.assertTrue(all(entry["available"] for entry in self.request("GET", path)[1]["item"]["entries"]))
        self.photo.unlink()
        self.scanner.scan()
        missing = self.request("GET", path)[1]["item"]
        self.assertEqual(len(missing["entries"]), 2)
        self.assertTrue(all(not entry["available"] for entry in missing["entries"]))

    def test_legacy_index_migrates(self):
        with self.repository.write_transaction() as connection:
            connection.execute("DROP TABLE memory_collection_entries")
            connection.execute("DROP TABLE memory_collections")
        self.repository.init_schema()
        self.repository.init_schema()
        self.assertEqual(self.create()["entries"][0]["path"], ALBUM)


if __name__ == "__main__":
    unittest.main()
