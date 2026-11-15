from __future__ import annotations

import json
import tempfile
import unittest
from http.client import HTTPConnection
from threading import Thread
from pathlib import Path
from urllib.parse import urlencode

from chromantis.api.server import ApiServer, make_api_handler
from chromantis.app import ApplicationService
from chromantis.bot.telegram_bot import TelegramBotService
from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser
from chromantis.source import ArchiveScanner, LocalArchiveSource


ALBUM = "2024/2024-04-21_beach_trip"
ALIAS = "Abuela's birthday"


class AlbumContextTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.archive = root / "archive"
        self.photo = self.archive / ALBUM / "SYNTHETIC.jpg"
        self.photo.parent.mkdir(parents=True)
        self.photo.write_bytes(b"synthetic image contents")
        self.repository = Repository(str(root / "index.db"))
        self.repository.init_schema()
        self.scanner = ArchiveScanner(LocalArchiveSource(str(self.archive)), self.repository, PathParser())
        self.scanner.scan()
        self.app = ApplicationService(self.repository, static_owner_chat_ids=(10,), static_viewer_chat_ids=(20,))
        server = ApiServer(("127.0.0.1", 0), make_api_handler(
            self.app, api_chat_tokens=((10, "owner-example"), (20, "viewer-example")),
            image_fetcher=lambda path: self.fail("Context editing and search must not read originals"),
        ))
        self.address = server.server_address
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)

    def request(self, method, path, *, body=None, token="owner-example", cookie=None):
        connection = HTTPConnection(*self.address, timeout=3)
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if body is not None:
            headers["Content-Type"] = "application/json"
        if cookie:
            headers.update({"Cookie": cookie, "Origin": f"http://127.0.0.1:{self.address[1]}"})
        try:
            connection.request(method, "/api/v1" + path, json.dumps(body) if body is not None else None, headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def edit(self, item, changes, **credential):
        return self.request("PATCH", "/album-review/context", body={
            "path": ALBUM, "id": item["id"], "revision": item["context_revision"], "changes": changes,
        }, **credential)

    def test_shared_metadata_survives_reindex_and_preserves_originals(self):
        status, payload = self.request("GET", "/album-review?" + urlencode({"path": ALBUM}))
        self.assertEqual(status, 200)
        first = payload["item"]
        status, payload = self.edit(first, {
            "title": "Cumpleaños de la abuela", "event_date": "2023-04-21", "aliases": [ALIAS],
            "note": "Comida después del paseo.",
        })
        self.assertEqual(status, 200, payload)
        edited = payload["item"]
        self.assertEqual((edited["indexed_date"], edited["event_date"]), ("2024-04-21", "2023-04-21"))
        self.assertEqual((edited["indexed_year"], edited["year"]), (2024, 2023))
        self.assertEqual(edited["indexed_title"], first["title"])
        self.assertEqual(edited["revision"], first["revision"])
        self.assertEqual(edited["suggestions"], first["suggestions"])
        self.assertEqual(self.app.get_album_review(10)["path"], ALBUM)
        self.scanner.scan()
        self.assertEqual(self.app.get_album_review(10), edited)
        for search in (self.app.search_folders, self.app.search_images):
            alias_result, = search(f"{ALIAS} 2023")
            self.assertIn(f'album_alias="{ALIAS}"', alias_result.reason)
            self.assertIn("year_corrected=2023", alias_result.reason)
            self.assertIn("Cumpleaños de la abuela", alias_result.title)
            self.assertIn("album_title", search("cumpleanos de la abuela")[0].reason)
            self.assertEqual(search("beach trip")[0].folder_path, ALBUM)
            self.assertEqual(search("2024-04-21_beach_trip")[0].folder_path, ALBUM)
            self.assertEqual(search("Abuela’s birthday")[0].folder_path, ALBUM)
            self.assertEqual(search(f"{ALIAS} 2024"), [])
        self.assertEqual([year.year for year in self.app.list_years()], [2023])
        self.assertEqual(self.app.images_in_year(2023)[0].event_date, "2023-04-21")
        self.assertEqual(self.app.images_in_year(2024), [])
        self.assertEqual(self.app.images_in_folder(ALBUM)[0].year, 2023)
        self.assertEqual(self.photo.read_bytes(), b"synthetic image contents")
        self.assertEqual(self.edit(first, {"note": "Stale"})[0], 409)

    def test_legacy_db_validation_and_clearing(self):
        with self.repository.session() as connection:
            connection.execute("DROP VIEW album_metadata")
            connection.execute("DROP TABLE album_context")
        self.repository.init_schema()
        original = self.app.get_album_review(10)
        self.assertEqual(original["context_revision"], 0)
        for changes in ({"event_date": "2023-02-29"}, {"aliases": ["a"] * 9}, {"unexpected": ""}):
            self.assertEqual(self.edit(original, changes)[0], 400)
        self.assertEqual(self.app.get_album_review(10), original)
        saved = self.edit(original, {"title": "Família", "aliases": ["Páscoa", "pascoa"]})[1]["item"]
        self.assertEqual(saved["aliases"], ["Páscoa"])
        self.assertEqual(self.edit(saved, {"title": "Família"})[1]["item"]["context_revision"], 1)
        cleared = self.edit(saved, {"title": "", "aliases": []})[1]["item"]
        self.assertEqual(cleared["title"], original["indexed_title"])
        self.assertEqual(cleared["context_revision"], 2)
        self.assertEqual(self.app.search_folders("pascoa"), [])

    def test_family_session_edits_using_same_permission_and_telegrams_share_context(self):
        item = self.app.get_album_review(10)
        self.assertEqual(self.edit(item, {"note": "forbidden"}, token="viewer-example")[0], 403)
        identity, code = self.app.family_access.invite("Navegador de prueba")
        secret = self.app.family_access.redeem(code)
        cookie = f"chromantis_family={secret}"
        updated = self.edit(item, {"aliases": [ALIAS]}, token=None, cookie=cookie)[1]["item"]
        self.assertEqual(updated["aliases"], [ALIAS])
        bot = TelegramBotService(self.app)
        command = f"/album {ALBUM}"
        self.assertIn("Only an administrator", bot.handle_command(command, chat_id=20).text)
        self.assertIn(ALIAS, bot.handle_command(command, chat_id=10).text)
        self.assertIn("Mensaje breve", bot.handle_command(f"{command} | note | Mensaje breve", chat_id=10).text)
        self.assertIn(ALBUM, bot.handle_command(f"/folders {ALIAS}", chat_id=20).text)
        self.assertEqual(self.app.get_album_review(10)["note"], "Mensaje breve")
        self.app.family_access.revoke(identity)
        self.assertEqual(self.edit(updated, {"note": "revoked"}, token=None, cookie=cookie)[0], 401)


if __name__ == "__main__":
    unittest.main()
