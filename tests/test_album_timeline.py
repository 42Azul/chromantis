from __future__ import annotations

import json
import tempfile
import unittest
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode

from chromantis.api.server import ApiServer, make_api_handler
from chromantis.app import ApplicationService
from chromantis.bot.telegram_bot import TelegramBotService
from chromantis.db.repository import Repository
from chromantis.db.schema import ALBUM_METADATA_VIEW_SQL
from chromantis.parsing.path_parser import PathParser
from chromantis.source import ArchiveScanner, LocalArchiveSource


SUMMER = "2024/2024-06-30_summer"
AUTUMN = "2023/2023-10-01_autumn"
UNDATED = "2024/albums"
OTHER = "2024/2024-08-01_other"


class AlbumTimelineTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "archive"
        for album in (SUMMER, AUTUMN, UNDATED, OTHER):
            file = self.root / album / "fixture.jpg"
            file.parent.mkdir(parents=True)
            file.write_bytes(b"synthetic")
        self.repository = Repository(str(Path(temp.name) / "index.db"))
        self.repository.init_schema()
        self.scanner = ArchiveScanner(LocalArchiveSource(str(self.root)), self.repository, PathParser())
        self.scanner.scan()
        self.app = ApplicationService(self.repository, static_owner_chat_ids=(10,), static_viewer_chat_ids=(20,))

    def edit(self, path, **changes):
        item = self.app.get_album_review(10, path=path)
        return self.app.edit_album_context(10, path, item["id"], item["context_revision"], changes)

    def test_place_is_editable_offline_and_timeline_uses_corrected_date(self):
        detached = self.root.with_name("disconnected")
        self.root.rename(detached)
        self.edit(SUMMER, place="Cabo de Pálos")
        self.edit(AUTUMN, place="Cabo de Palos, Murcia", event_date="2024-10-01")
        self.edit(UNDATED, place="Cabo de Palos")
        self.edit(OTHER, place="Cabo de Paloma")
        results = self.app.search_folders("2024", place="cabo de palos", chronological=True)
        self.assertEqual([item.path for item in results], [AUTUMN, SUMMER, UNDATED])
        self.assertEqual([item.event_date_source for item in results], ["album_correction", "folder_name", None])
        self.assertEqual(results[0].event_date, "2024-10-01")
        self.assertIn('place="Cabo de Palos, Murcia"', results[0].reason)
        self.assertEqual(self.app.search_folders("pálos 2024", chronological=True), results)
        dated = self.app.search_folders("", place="palos", date_from="2024-06-30", date_to="2024-10-01",
                                        chronological=True, limit=1, offset=1)
        self.assertEqual([item.path for item in dated], [SUMMER])
        detached.rename(self.root)
        self.scanner.scan()
        self.assertEqual(self.app.get_album_review(10, path=AUTUMN)["place"], "Cabo de Palos, Murcia")
        self.assertEqual((self.root / AUTUMN / "fixture.jpg").read_bytes(), b"synthetic")
        with self.assertRaises(ValueError):
            self.edit(AUTUMN, place="Madrid\nBarcelona")
        cleared = self.edit(AUTUMN, place="")
        self.assertIsNone(cleared["place"])
        self.assertEqual(cleared["event_date"], "2024-10-01")

    def test_api_timeline_carries_provenance_and_family_permissions(self):
        self.edit(AUTUMN, place="Cartagena", event_date="2024-10-01")
        identity, code = self.app.family_access.invite("Synthetic")
        session = self.app.family_access.redeem(code)
        server = ApiServer(("127.0.0.1", 0), make_api_handler(self.app, api_chat_tokens=((10, "owner-fixture"),)))
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)

        def request(filters, *, cookie=None, owner=False):
            connection = HTTPConnection(*server.server_address, timeout=2)
            try:
                headers = {"Cookie": cookie} if cookie else {}
                if owner:
                    headers["Authorization"] = "Bearer owner-fixture"
                connection.request("GET", "/api/v1/folders?" + urlencode(filters), headers=headers)
                response = connection.getresponse()
                return response.status, json.loads(response.read())
            finally:
                connection.close()

        params = {"sort": "timeline", "place": "cartagena", "q": "2024", "date_from": "2024-09-01",
                  "date_to": "2024-10-01"}
        self.assertEqual(request(params)[0], 401)
        status, body = request(params, cookie=f"chromantis_family={session}")
        self.assertEqual(status, 200)
        item, = body["items"]
        self.assertEqual((item["place"], item["event_date_source"]), ("Cartagena", "album_correction"))
        self.assertEqual(request(params, owner=True)[0], 200)
        self.assertEqual(self.repository.list_saved_searches(10, False, 10), [])
        for invalid in ({"date_from": "2024-02-30"}, {"date_from": "2025-01-01"}, {"offset": "-1"},
                        {"place": "*"}, {"sort": "unknown"}):
            self.assertEqual(request({**params, **invalid}, owner=True)[0], 400)
        self.edit(OTHER, event_date="2020-06-30")
        self.root.rename(self.root.with_name("disconnected"))
        anniversary = {"month_day": "06-30", "sort": "timeline"}
        self.assertEqual(request(anniversary)[0], 401)
        status, body = request(anniversary, cookie=f"chromantis_family={session}")
        self.assertEqual(status, 200)
        self.assertEqual(body["month_day"], anniversary["month_day"])
        self.assertEqual(
            [(item["path"], item["event_date"], item["event_date_source"]) for item in body["items"]],
            [(SUMMER, "2024-06-30", "folder_name"), (OTHER, "2020-06-30", "album_correction")],
        )
        self.assertEqual(request({**anniversary, "limit": 1, "offset": 1}, owner=True)[1]["items"][0]["path"], OTHER)
        self.assertEqual(request({"month_day": "08-01"}, owner=True)[1]["items"], [])
        self.assertEqual(request({"month_day": "02-29"}, owner=True)[0], 200)
        self.assertEqual(request({"month_day": "02-30"}, owner=True)[0], 400)
        self.assertEqual(self.repository.list_saved_searches(10, False, 10), [])
        self.app.family_access.revoke(identity)
        self.assertEqual(request(params, cookie=f"chromantis_family={session}")[0], 401)

    def test_telegram_reads_and_writes_the_same_place_and_date_filters(self):
        bot = TelegramBotService(self.app)
        self.app.set_chat_language(20, "es", actor_chat_id=20)
        place = bot.handle_command(f"/album {AUTUMN} | place | Cartagena", chat_id=10)
        self.assertIn("Place: Cartagena", place.text)
        self.edit(AUTUMN, event_date="2024-10-01")
        for command in ("/timeline 2024 | Cartagena", "/timeline 2024-09-01..2024-10-01 | Cartagena"):
            response = bot.handle_command(command, chat_id=20)
            self.assertIn("Cronología de álbumes", response.text)
            self.assertIn("2024-10-01 (fecha corregida)", response.text)
            self.assertIn(AUTUMN, response.text)
        self.assertNotIn(AUTUMN, bot.handle_command("/timeline 2023 | Cartagena", chat_id=20).text)
        self.assertIn("Solo un administrador", bot.handle_command(f"/album {AUTUMN} | place | Other", chat_id=20).text)

    def test_migration_preserves_existing_edits_and_is_repeatable(self):
        self.edit(AUTUMN, title="Recuerdo", note="Una nota", aliases=["Recuerdo otoñal"])
        with self.repository.write_transaction() as connection:
            connection.execute("DROP VIEW album_metadata")
            connection.execute("ALTER TABLE album_context RENAME TO album_context_fixture")
            connection.execute(
                """CREATE TABLE album_context (
                   folder_id INTEGER PRIMARY KEY REFERENCES folders(id) ON DELETE CASCADE,
                   title TEXT, event_date TEXT, note TEXT, aliases_json TEXT NOT NULL, revision INTEGER NOT NULL
                )"""
            )
            connection.execute("""INSERT INTO album_context
                SELECT folder_id, title, event_date, note, aliases_json, revision FROM album_context_fixture""")
            connection.execute("DROP TABLE album_context_fixture")
            connection.execute(ALBUM_METADATA_VIEW_SQL.replace(", c.place", ""))
        self.repository.init_schema()
        self.repository.init_schema()
        result = self.edit(AUTUMN, place="Murcia")
        self.assertEqual((result["title"], result["note"], result["aliases"]),
                         ("Recuerdo", "Una nota", ["Recuerdo otoñal"]))
        self.assertEqual(result["place"], "Murcia")


if __name__ == "__main__":
    unittest.main()
