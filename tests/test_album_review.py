from __future__ import annotations

import json
import tempfile
import unittest
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from unittest.mock import Mock, patch
from urllib.parse import urlencode

from chromantis.api.server import ApiServer, make_api_handler
from chromantis.app import ApplicationService
from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser
from chromantis.source import ArchiveScanner, LocalArchiveSource


ALBUM_PATH = "2024/2024-04-21_birthday_beach_trip"
AMBIGUOUS_PATH = "2024/IMG_0042"


class AlbumReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.archive = Path(directory.name) / "archive"
        self.repository = Repository(str(Path(directory.name) / "index.db"))
        self.repository.init_schema()
        self.add_photo(ALBUM_PATH)
        self.add_photo(AMBIGUOUS_PATH)
        self.scanner = ArchiveScanner(LocalArchiveSource(str(self.archive)), self.repository, PathParser())
        self.scanner.scan()
        self.ana = self.repository.create_person("Ana")
        self.repository.add_person_alias(self.ana.id, "Ani")
        self.repository.authorize_chat(20, role="viewer")
        self.repository.authorize_chat(30, role="viewer")
        self.app = ApplicationService(self.repository, static_owner_chat_ids=(10,), curator_chat_ids=(20,))
        self.image_fetcher = Mock(side_effect=FileNotFoundError)
        server = ApiServer(("127.0.0.1", 0), make_api_handler(
            self.app, api_token="shared-read", image_fetcher=self.image_fetcher,
            api_chat_tokens=((10, "owner"), (20, "curator"), (30, "viewer")),
        ))
        self.address = server.server_address
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)

    def add_photo(self, album: str) -> None:
        folder = self.archive / album
        folder.mkdir(parents=True)
        (folder / "SYNTHETIC.jpg").write_bytes(b"not opened by metadata indexing")

    def request(self, method, path, data=None, token="curator"):
        connection = HTTPConnection(*self.address, timeout=2)
        try:
            connection.request(method, "/api/v1" + path, json.dumps(data) if data else None,
                               {"Authorization": f"Bearer {token}"})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def review(self, path=ALBUM_PATH):
        status, payload = self.request("GET", "/album-review?" + urlencode({"path": path}))
        self.assertEqual(status, 200)
        return payload["item"]

    def save(self, item, **values):
        return self.request("POST", "/album-review", {
            **{key: item[key] for key in ("path", "id", "revision")}, **values,
        })

    def test_curator_reviews_offline_and_finds_ana_after_reindex(self):
        offline_path = self.archive.with_name("disconnected")
        self.archive.rename(offline_path)
        with patch("socket.socket", side_effect=AssertionError("Name rules must work offline")):
            self.assertEqual(self.app.get_album_review(20, path=ALBUM_PATH)["event_date"], "2024-04-21")
        status, directory = self.request("GET", "/album-review/people")
        self.assertEqual((status, directory["items"]), (200, [
            {"id": self.ana.id, "display_name": "Ana", "aliases": ["Ani"]},
        ]))
        item = self.review()
        self.assertEqual(set(item["suggestions"]), {"cumpleanos", "playa", "viaje"})
        self.assertEqual(item["suggestions"]["cumpleanos"]["evidence"], "birthday")
        self.assertEqual(self.review(AMBIGUOUS_PATH)["suggestions"], {})
        self.assertEqual(self.save(
            item, add_people=[self.ana.id], new_person="Elena",
            decisions={"playa": "playa", "viaje": "vacaciones", "cumpleanos": None},
            manual_add=["familia"],
        )[0], 200)
        self.image_fetcher.assert_not_called()
        for query in ("Ana", "Ani", "Elena", "playa", "vacaciones", "familia"):
            with self.subTest(query=query):
                for endpoint in ("folders", "images"):
                    status, matches = self.request("GET", f"/{endpoint}?" + urlencode({"q": query}))
                    self.assertEqual(status, 200)
                    self.assertEqual(len(matches["items"]), 1)
        self.assertEqual(self.app.search_folders("cumpleaños"), [])

        offline_path.rename(self.archive)
        self.add_photo("2024/2024-12-25_christmas")
        self.scanner.scan(incremental=True)
        self.scanner.scan()
        self.repository.init_schema()
        updated = self.review()
        self.assertEqual(updated["manual_tags"], ["familia"])
        self.assertEqual({key: value["state"] for key, value in updated["suggestions"].items()},
                         {"playa": "accepted", "viaje": "corrected", "cumpleanos": "rejected"})
        pending = self.request("GET", "/album-review")[1]["item"]
        self.assertEqual(pending["path"], AMBIGUOUS_PATH)
        next_album = self.request("GET", f"/album-review?after={pending['id']}")[1]["item"]
        self.assertEqual(next_album["path"], "2024/2024-12-25_christmas")
        self.assertEqual(self.request("GET", "/album-review?reviewed=true")[1]["item"]["path"], ALBUM_PATH)
        self.assertEqual(self.save(updated, remove_people=[self.ana.id], manual_remove=["familia"])[0], 200)
        self.assertEqual(self.app.search_folders("Ana"), [])
        self.assertEqual(self.app.search_folders("familia"), [])
        self.assertEqual(self.save(updated, add_people=[self.ana.id])[0], 409)

    def test_partial_review_requires_explicit_decisions_and_save_is_atomic(self):
        item = self.review()
        self.assertEqual(self.save(item, add_people=[999], decisions={"playa": "playa"})[0], 400)
        self.assertEqual(self.review(), item)
        self.assertEqual(self.save(item, decisions={"playa": "playa"})[0], 200)
        self.assertEqual(self.request("GET", "/album-review?reviewed=true")[1]["item"], None)
        self.assertEqual(self.review()["suggestions"]["playa"]["state"], "accepted")
        self.assertEqual(self.review()["suggestions"]["viaje"]["state"], "pending")

    def test_quick_review_accepts_only_the_displayed_tag_and_skip_keeps_pending(self):
        self.archive.rename(self.archive.with_name("disconnected"))
        _, payload = self.request("GET", "/album-review")
        item = payload["item"]
        self.assertEqual(item["path"], ALBUM_PATH)
        self.assertEqual(self.save(item, decisions={"playa": "playa"})[0], 200)

        _, payload = self.request("GET", "/album-review")
        partial = payload["item"]
        self.assertEqual(partial["id"], item["id"])
        self.assertEqual(
            {key: value["state"] for key, value in partial["suggestions"].items()},
            {"playa": "accepted", "viaje": "pending", "cumpleanos": "pending"},
        )
        _, payload = self.request("GET", f"/album-review?after={partial['id']}")
        self.assertEqual(payload["item"]["path"], AMBIGUOUS_PATH)
        self.assertEqual(self.review(), partial)
        self.assertEqual(self.save(partial, decisions={"viaje": "viaje", "cumpleanos": None})[0], 200)
        _, payload = self.request("GET", "/album-review")
        self.assertEqual(payload["item"]["path"], AMBIGUOUS_PATH)
        self.image_fetcher.assert_not_called()

    def test_batch_accepts_and_rejects_shared_suggestion_offline_and_survives_reindex(self):
        accepted_paths = [ALBUM_PATH, "2024/2024-05-01_beach_picnic"]
        rejected_path = "2024/2024-06-01_playa_dudosa"
        self.add_photo(accepted_paths[1])
        self.add_photo(rejected_path)
        self.scanner.scan(incremental=True)
        offline_path = self.archive.with_name("disconnected-batch")
        self.archive.rename(offline_path)

        status, payload = self.request("GET", "/album-review/batch?limit=50")
        self.assertEqual(status, 200)
        playa = next(group for group in payload["groups"] if group["key"] == "playa")
        by_path = {album["path"]: album for album in playa["albums"]}
        self.assertEqual(set(by_path), {*accepted_paths, rejected_path})
        items = [{
            **{key: by_path[path][key] for key in ("id", "path", "revision")},
            "label": "playa",
            "decision": "accepted" if path in accepted_paths else "rejected",
        } for path in (*accepted_paths, rejected_path)]
        stale = [dict(item) for item in items]
        stale[-1]["revision"] += 1
        self.assertEqual(self.request("POST", "/album-review/batch", {"items": stale})[0], 409)
        self.assertEqual(self.review(accepted_paths[0])["suggestions"]["playa"]["state"], "pending")
        self.assertEqual(self.request("POST", "/album-review/batch", {"items": items})[0], 200)

        for path in accepted_paths:
            self.assertEqual(self.review(path)["suggestions"]["playa"]["state"], "accepted")
        self.assertEqual(self.review(rejected_path)["suggestions"]["playa"]["state"], "rejected")
        self.image_fetcher.assert_not_called()
        self.assertEqual(self.repository.list_audit_events(limit=1)[0].action, "save_album_review_batch")

        offline_path.rename(self.archive)
        self.scanner.scan()
        for path in accepted_paths:
            self.assertEqual(self.review(path)["suggestions"]["playa"]["state"], "accepted")
        self.assertEqual(self.review(rejected_path)["suggestions"]["playa"]["state"], "rejected")

    def test_ambiguous_albums_do_not_hide_later_batch_suggestions(self):
        item = self.review()
        self.assertEqual(self.save(
            item, decisions={label: label for label in item["suggestions"]}
        )[0], 200)
        for number in range(199):
            self.add_photo(f"2024/archivo_{number:03d}")
        target = "2024/2024-07-01_playa"
        self.add_photo(target)
        self.scanner.scan(incremental=True)

        status, payload = self.request("GET", "/album-review/batch?limit=50")
        self.assertEqual(status, 200)
        playa = next(group for group in payload["groups"] if group["key"] == "playa")
        self.assertEqual([album["path"] for album in playa["albums"]], [target])
        self.image_fetcher.assert_not_called()

    def test_curator_cannot_administer_and_revocation_is_live(self):
        self.assertEqual(self.request("GET", "/auth/me")[1]["can_curate_albums"], True)
        self.assertEqual(self.request("GET", "/admin/config")[0], 403)
        self.assertEqual(self.request("POST", "/admin/people", {"display_name": "New"})[0], 403)
        for token, status in (("shared-read", 401), ("viewer", 403)):
            self.assertEqual(self.request("GET", "/album-review", token=token)[0], status)
            self.assertEqual(self.request("GET", "/album-review/batch", token=token)[0], status)
        self.assertEqual(self.request("GET", "/album-review", token="owner")[0], 200)
        self.repository.revoke_chat(20)
        self.assertEqual(self.request("GET", "/album-review")[0], 401)

    def test_preview_lists_at_most_three_indexed_paths_without_opening_images(self):
        folder = self.archive / ALBUM_PATH
        for number in range(4):
            (folder / f"FIGURE_{number}.jpg").write_bytes(b"synthetic")
        self.scanner.scan()
        status, previews = self.request("GET", "/album-review/photos?" + urlencode({"path": ALBUM_PATH}))
        self.assertEqual(status, 200)
        self.assertEqual(len(previews["items"]), 3)
        self.assertTrue(all(preview["folder_path"] == ALBUM_PATH for preview in previews["items"]))
        self.image_fetcher.assert_not_called()
        self.assertEqual(self.request("GET", "/image?" + urlencode({"path": previews["items"][0]["path"]}))[0], 404)
        self.image_fetcher.assert_called_once()

    def test_existing_index_migrates_without_losing_person_links(self):
        self.repository.link_person_to_folder(self.ana.id, ALBUM_PATH)
        with self.repository.session() as connection:
            connection.execute("DROP TABLE album_tag_decisions")
            connection.execute("DROP TABLE album_reviews")
        self.repository.init_schema()
        item = self.review()
        self.assertEqual(item["person_ids"], [self.ana.id])
        self.assertEqual(item["revision"], 0)


if __name__ == "__main__":
    unittest.main()
