from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from unittest.mock import Mock
from urllib.parse import urlencode

from chromantis.api.server import ApiServer, make_api_handler
from chromantis.app import ApplicationService
from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser
from chromantis.source import ArchiveScanner, LocalArchiveSource


ALBUM = "2024/2024-03-16_picnic"
PHOTOS = tuple(f"{ALBUM}/synthetic_{number}.jpg" for number in range(1, 4))
PHOTO_PATH, SECOND_PATH, THIRD_PATH = PHOTOS


class PhotoTagTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.archive = Path(directory.name) / "archive"
        (self.archive / ALBUM).mkdir(parents=True)
        for number, path in enumerate(PHOTOS):
            (self.archive / path).write_bytes(f"Synthetic photo {number}".encode())
        self.repository = Repository(str(Path(directory.name) / "index.db"))
        self.repository.init_schema()
        source = LocalArchiveSource(str(self.archive))
        source.read_bytes = Mock(side_effect=AssertionError("Photo curation must not open originals"))
        self.scanner = ArchiveScanner(source, self.repository, PathParser())
        self.scanner.scan()
        self.ana = self.repository.create_person("Ana")
        self.repository.add_person_alias(self.ana.id, "Anita")
        for chat_id in (20, 30):
            self.repository.authorize_chat(chat_id, role="viewer")
        self.app = ApplicationService(self.repository, curator_chat_ids=(20,))
        server = ApiServer(("127.0.0.1", 0), make_api_handler(
            self.app, api_token="shared-read", api_chat_tokens=((20, "curator"), (30, "reader")),
            image_fetcher=source.read_bytes,
        ))
        self.address = server.server_address
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)

    def request(self, method, path, data=None, *, token="curator", cookie=None, same_origin=True):
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = f"chromantis_family={cookie}"
            if same_origin:
                headers["Origin"] = f"http://{self.address[0]}:{self.address[1]}"
        elif token:
            headers["Authorization"] = f"Bearer {token}"
        connection = HTTPConnection(*self.address, timeout=2)
        try:
            connection.request(method, f"/api/v1{path}", json.dumps(data) if data is not None else None, headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def tags(self, *paths):
        status, payload = self.request("GET", "/photo-tags?" + urlencode([("path", path) for path in paths]))
        self.assertEqual(status, 200, payload)
        return payload["items"]

    def edit(self, items, *, token="curator", **changes):
        photos = [{key: item[key] for key in ("path", "identity")} for item in items]
        return self.request("PATCH", "/photo-tags", {"photos": photos, **changes}, token=token)

    def find(self, endpoint, **params):
        status, payload = self.request("GET", f"/{endpoint}?" + urlencode(params), token="reader")
        self.assertEqual(status, 200, payload)
        return [item["path"] for item in payload["items"]]

    def archive_contents(self):
        contents = {}
        for path in (self.archive / ALBUM).iterdir():
            stat = path.stat()
            contents[path.name] = (path.read_bytes(), stat.st_mtime_ns, stat.st_mode)
        return contents

    def test_family_batch_from_different_albums_is_atomic_and_works_offline(self):
        other = "2023/2023-10-05_excursion/synthetic_1.jpg"
        (self.archive / other).parent.mkdir(parents=True)
        (self.archive / other).write_bytes(b"Another synthetic original")
        self.scanner.scan(incremental=True)
        first, second = self.tags(PHOTO_PATH, other)
        _, code = self.app.family_access.invite("Synthetic curator")
        secret = self.app.family_access.redeem(code)
        self.archive.rename(self.archive.with_name("disconnected"))
        photos = [{"path": photo["path"], "identity": photo["identity"]} for photo in (first, second)]
        status, _ = self.request("PATCH", "/photo-tags", {
            "photos": photos, "add_people": [self.ana.id], "manual_add": ["romería"],
        }, cookie=secret)
        self.assertEqual(status, 200)
        self.assertEqual(set(self.find("confirmed-images", person="Anita", tag="ROMERIA")), {PHOTO_PATH, other})
        stale = [photos[0], {**photos[1], "identity": "0" * 32}]
        status, _ = self.request("PATCH", "/photo-tags", {
            "photos": stale, "remove_people": [self.ana.id], "manual_remove": ["romeria"],
        }, cookie=secret)
        self.assertEqual(status, 409)
        self.assertEqual(set(self.find("confirmed-images", person="Ana", tag="romeria")), {PHOTO_PATH, other})
        status, _ = self.request("PATCH", "/photo-tags", {
            "photos": photos, "remove_people": [self.ana.id], "manual_remove": ["romeria"],
        }, cookie=secret)
        self.assertEqual(status, 200)
        self.assertEqual(self.find("confirmed-images", person="Ana", tag="romeria"), [])
        self.assertEqual(self.tags(SECOND_PATH)[0]["people"], [])
        self.assertEqual(self.tags(THIRD_PATH)[0]["manual_tags"], [])
        self.scanner.source.read_bytes.assert_not_called()

    def test_manual_people_and_tags_survive_reindex_without_changing_originals(self):
        album_dir = self.archive / ALBUM
        for path in PHOTOS:
            original = self.archive / path
            original.chmod(0o444)
            self.addCleanup(original.chmod, 0o644)
        album_dir.chmod(0o555)
        self.addCleanup(album_dir.chmod, 0o755)
        originals = self.archive_contents()

        self.repository.link_person_to_folder("Anita", ALBUM)
        self.assertEqual(self.find("folders", q="Anita"), [ALBUM])
        self.assertEqual(self.find("images", q="Anita"), list(PHOTOS))
        self.assertEqual(self.find("confirmed-images", person="Ana"), [])

        first, second, third = self.tags(*PHOTOS)
        denied, payload = self.edit([third], token="reader", add_people=[self.ana.id])
        self.assertEqual((denied, payload["code"]), (403, "album_curation_required"))
        self.assertEqual(self.edit([third], token="shared-read", add_people=[self.ana.id])[0], 401)
        self.assertEqual(self.edit([third], token=None, add_people=[self.ana.id])[0], 401)
        self.assertEqual(self.tags(THIRD_PATH), [third])

        status, payload = self.edit([second, first], add_people=[self.ana.id], manual_add=["Álbum"])
        self.assertEqual(status, 200, payload)
        self.assertEqual([item["path"] for item in payload["items"]], [SECOND_PATH, PHOTO_PATH])
        for item in payload["items"]:
            self.assertEqual(item["people"], [{"person_id": self.ana.id, "origin": "manual"}])
            self.assertEqual(item["manual_tags"], [{"tag": "album", "origin": "manual"}])
        self.assertEqual(self.find("confirmed-images", person="aníta"), [PHOTO_PATH, SECOND_PATH])
        self.assertEqual(self.find("confirmed-images", person_id=self.ana.id), [PHOTO_PATH, SECOND_PATH])
        self.assertEqual(self.find("confirmed-images", person="Unknown"), [])
        status, page = self.request("GET", "/confirmed-images?person=Ana&limit=1")
        self.assertEqual((status, page["next_offset"], page["items"][0]["reason"]),
                         (200, 1, 'confirmed_person="Ana"'))
        self.assertEqual(self.find("confirmed-images", person="Ana", offset=1), [SECOND_PATH])
        self.assertEqual(self.find("images", q="album"), [PHOTO_PATH, SECOND_PATH])
        self.assertEqual(self.find("folders", q="album"), [])

        self.assertEqual(self.edit([second], remove_people=[self.ana.id], manual_remove=["Álbum"])[0], 200)
        self.scanner.scan(incremental=True)
        self.scanner.scan()
        self.repository.init_schema()

        self.assertEqual(self.find("confirmed-images", person="Ana"), [PHOTO_PATH])
        self.assertEqual(self.find("images", q="Ana"), list(PHOTOS))
        self.assertEqual(self.find("images", q="album"), [PHOTO_PATH])
        remaining, removed = self.tags(PHOTO_PATH, SECOND_PATH)
        self.assertEqual(remaining, payload["items"][1])
        self.assertEqual(removed, second)
        removal, *additions = [
            event for event in self.repository.list_audit_events() if event.action == "save_photo_tags"
        ]
        self.assertEqual((removal.target_id, removal.actor_chat_id, len(additions)), (SECOND_PATH, 20, 2))
        self.assertEqual(json.loads(removal.details_json)["remove_people"], [self.ana.id])
        self.assertEqual(json.loads(removal.details_json)["origin"], "manual")
        self.scanner.source.read_bytes.assert_not_called()
        self.assertEqual(self.archive_contents(), originals)

    def test_replaced_photo_changes_identity_and_stale_batch_is_atomic(self):
        first, second = self.tags(PHOTO_PATH, SECOND_PATH)
        self.assertEqual(self.edit([first, second], add_people=[self.ana.id], manual_add=["family"])[0], 200)
        (self.archive / SECOND_PATH).write_bytes(b"Different synthetic original with different size")
        self.scanner.scan(incremental=True)

        self.assertEqual(self.find("confirmed-images", person="Ana"), [PHOTO_PATH])
        current = self.tags(SECOND_PATH)[0]
        self.assertNotEqual(current["identity"], second["identity"])
        self.assertEqual((current["people"], current["manual_tags"]), ([], []))
        self.assertEqual(self.edit([first, second], remove_people=[self.ana.id])[0], 409)
        self.assertEqual(self.find("confirmed-images", person="Ana"), [PHOTO_PATH])
        self.assertEqual(self.edit([first], manual_add=["family"], add_people=[999])[0], 400)
        self.assertEqual(self.edit([first], manual_add=["niño"], manual_remove=["nino"])[0], 400)

        previous_events = self.repository.list_audit_events()
        self.assertEqual(self.edit([first], add_people=[self.ana.id], manual_add=["family"])[0], 200)
        self.assertEqual(self.repository.list_audit_events(), previous_events)
        replacement_root = self.archive.with_name("another-root")
        self.archive.rename(replacement_root)
        ArchiveScanner(LocalArchiveSource(str(replacement_root)), self.repository, PathParser()).scan()
        self.assertEqual(self.find("confirmed-images", person="Ana"), [])
        self.assertNotEqual(self.tags(PHOTO_PATH)[0]["identity"], first["identity"])

    def test_missing_source_metadata_preserves_last_known_photo_identity(self):
        photo = self.tags(PHOTO_PATH)[0]
        self.assertEqual(self.edit([photo], add_people=[self.ana.id])[0], 200)
        entries = list(self.scanner.source.iter_entries())
        incomplete_entries = [
            replace(entry, modified_at=None, size=None) if entry.path == PHOTO_PATH else entry
            for entry in entries
        ]
        self.scanner.source.iter_entries = Mock(return_value=incomplete_entries)
        self.scanner.scan(incremental=True)
        self.assertEqual(self.repository.indexed_image_fingerprint(PHOTO_PATH)[1:], (None, None))
        self.assertEqual(self.tags(PHOTO_PATH)[0]["identity"], photo["identity"])
        self.assertEqual(self.find("confirmed-images", person="Ana"), [PHOTO_PATH])

        self.scanner.source.iter_entries.return_value = entries
        self.scanner.scan()
        self.assertEqual(self.tags(PHOTO_PATH)[0]["identity"], photo["identity"])

        self.scanner.source.iter_entries.return_value = incomplete_entries
        self.scanner.scan(incremental=True)
        self.scanner.source.iter_entries.return_value = [
            replace(entry, modified_at=None, size=entry.size + 1) if entry.path == PHOTO_PATH else entry
            for entry in entries
        ]
        self.scanner.scan(incremental=True)
        replacement = self.tags(PHOTO_PATH)[0]
        self.assertNotEqual(replacement["identity"], photo["identity"])
        self.assertEqual(self.find("confirmed-images", person="Ana"), [])
        self.assertEqual(self.edit([replacement], add_people=[self.ana.id])[0], 200)

        self.scanner.source.iter_entries.return_value = [
            replace(entry, modified_at="2024-03-17T00:00:00+00:00", size=entry.size + 1)
            if entry.path == PHOTO_PATH else entry for entry in entries
        ]
        self.scanner.scan(incremental=True)
        self.assertEqual(self.tags(PHOTO_PATH)[0]["identity"], replacement["identity"])
        self.assertEqual(self.find("confirmed-images", person="Ana"), [PHOTO_PATH])

    def test_family_session_reuses_curation_permission_and_revocation(self):
        _, code = self.app.family_access.invite("Family curator")
        secret = self.app.family_access.redeem(code)
        session = self.app.family_access.resolve(secret)
        first = self.tags(PHOTO_PATH)[0]
        data = {
            "photos": [{key: first[key] for key in ("path", "identity")}],
            "add_people": [self.ana.id],
        }
        self.assertEqual(self.request("PATCH", "/photo-tags", data, cookie=secret, same_origin=False)[0], 403)
        self.assertEqual(self.request("PATCH", "/photo-tags", data, cookie=secret)[0], 200)
        status, confirmed = self.request("GET", "/confirmed-images?person=Anita", cookie=secret)
        self.assertEqual((status, [item["path"] for item in confirmed["items"]]), (200, [PHOTO_PATH]))
        event = self.repository.list_audit_events()[0]
        self.assertEqual(json.loads(event.details_json)["family_access_id"], session.id)
        self.app.family_access.revoke(session.id)
        self.assertEqual(self.request("PATCH", "/photo-tags", data, cookie=secret)[0], 401)
        self.assertEqual(self.request("GET", "/confirmed-images?person=Anita", cookie=secret)[0], 401)

    def test_manual_tag_search_uses_only_photo_tags_with_the_archive_disconnected(self):
        first, second, _ = self.tags(*PHOTOS)
        self.assertEqual(self.edit([first, second], manual_add=["Pícnic"])[0], 200)
        with self.repository.connect() as connection:
            connection.execute("DROP INDEX idx_photo_manual_tags_tag")
        self.repository.init_schema()
        with self.repository.connect() as connection:
            indexes = connection.execute("PRAGMA index_list(photo_manual_tags)")
            self.assertIn("idx_photo_manual_tags_tag", {row["name"] for row in indexes})
        self.scanner.scan(incremental=True)
        self.archive.rename(self.archive.with_name("disconnected"))
        self.assertEqual(self.find("confirmed-images", tag="PÍCNIC"), [PHOTO_PATH, SECOND_PATH])
        self.assertEqual(self.find("confirmed-images", tag="pic"), [])
        self.assertEqual(self.find("folders", q="picnic"), [ALBUM])

        _, code = self.app.family_access.invite("Family curator")
        secret = self.app.family_access.redeem(code)
        route = "/confirmed-images?tag=picnic&limit=1"
        status, page = self.request("GET", route, cookie=secret)
        self.assertEqual((status, page["next_offset"]), (200, 1))
        self.assertEqual((page["items"][0]["path"], page["items"][0]["reason"]),
                         (PHOTO_PATH, 'manual_tag="picnic"'))
        status, page = self.request("GET", route + "&offset=1", cookie=secret)
        self.assertEqual((status, page["next_offset"], page["items"][0]["path"]), (200, None, SECOND_PATH))
        for invalid in ("tag=", "tag=picnic&tag=playa", "tag=picnic&person=", "tag=dos+palabras"):
            self.assertEqual(self.request("GET", "/confirmed-images?" + invalid, cookie=secret)[0], 400)
        self.assertEqual(self.request("GET", route, token=None)[0], 401)
        self.assertEqual(self.edit([first], manual_remove=["picnic"])[0], 200)
        self.assertEqual(self.find("confirmed-images", tag="picnic"), [SECOND_PATH])
        self.app.family_access.revoke(self.app.family_access.resolve(secret).id)
        self.assertEqual(self.request("GET", route, cookie=secret)[0], 401)
        self.scanner.source.read_bytes.assert_not_called()

    def test_confirmed_person_and_manual_tag_match_the_same_photo(self):
        first, second, third = self.tags(*PHOTOS)
        self.repository.link_person_to_folder(self.ana.id, ALBUM)
        self.assertEqual(self.edit([first, second], add_people=[self.ana.id])[0], 200)
        self.assertEqual(self.edit([second, third], manual_add=["Romería"])[0], 200)
        self.scanner.scan(incremental=True)
        self.archive.rename(self.archive.with_name("disconnected"))
        self.assertEqual(self.find("confirmed-images", person="Anita", tag="ROMERIA"), [SECOND_PATH])
        self.assertEqual(self.find("confirmed-images", person_id=self.ana.id, tag="romería"), [SECOND_PATH])
        self.assertEqual(self.find("confirmed-images", person="Ana", tag="rom"), [])
        self.assertEqual(self.find("confirmed-images", person="Unknown", tag="romeria"), [])
        self.assertEqual(self.find("confirmed-images", tag="romeria"), [SECOND_PATH, THIRD_PATH])
        _, code = self.app.family_access.invite("Family curator")
        secret = self.app.family_access.redeem(code)
        route = "/confirmed-images?" + urlencode({"person": "Anita", "tag": "romería", "limit": 1})
        status, result = self.request("GET", route, cookie=secret)
        self.assertEqual((status, result["next_offset"]), (200, None))
        self.assertEqual(result["items"][0]["reason"], 'confirmed_person="Ana" manual_tag="romeria"')
        self.assertEqual(self.edit([second], manual_remove=["romeria"])[0], 200)
        self.assertEqual(self.request("GET", route, cookie=secret)[1]["items"], [])
        for invalid in ("person=Ana&person_id=1&tag=romeria", "person=Ana&tag=", "person=Ana&tag=two+words"):
            self.assertEqual(self.request("GET", "/confirmed-images?" + invalid, cookie=secret)[0], 400)
        self.scanner.source.read_bytes.assert_not_called()

    def test_removed_photo_does_not_inherit_decisions_when_path_returns(self):
        third = self.tags(THIRD_PATH)[0]
        self.assertEqual(self.edit([third], add_people=[self.ana.id], manual_add=["family"])[0], 200)
        original = self.archive / THIRD_PATH
        held = self.archive.with_name("held.jpg")
        original.rename(held)
        self.scanner.scan()
        self.assertEqual(self.request("GET", "/photo-tags?" + urlencode({"path": THIRD_PATH}))[0], 404)
        held.rename(original)
        self.scanner.scan()
        current = self.tags(THIRD_PATH)[0]
        self.assertNotEqual(current["identity"], third["identity"])
        self.assertEqual((current["people"], current["manual_tags"]), ([], []))
        self.assertEqual(self.edit([third], add_people=[self.ana.id])[0], 409)


class PhotoTagMigrationTests(unittest.TestCase):
    def test_existing_index_preserves_album_links_and_can_curate_existing_photos(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "index.db")
            with sqlite3.connect(db_path) as connection:
                connection.executescript("""
                    CREATE TABLE folders (
                        id INTEGER PRIMARY KEY, folder_path TEXT UNIQUE, ftp_root_path TEXT,
                        year INTEGER, folder_name_raw TEXT, folder_slug TEXT, title TEXT,
                        event_date TEXT, scan_seen_at TEXT
                    );
                    CREATE TABLE images (
                        id INTEGER PRIMARY KEY, folder_id INTEGER REFERENCES folders(id),
                        file_path TEXT UNIQUE, filename TEXT, extension TEXT, ftp_modified_at TEXT,
                        file_size INTEGER, scan_seen_at TEXT
                    );
                    INSERT INTO folders VALUES (
                        13, '2024/picnic', 'synthetic', 2024, 'picnic', 'picnic', 'picnic', NULL, 'seen'
                    );
                    INSERT INTO images VALUES (
                        21, 13, '2024/picnic/fixture.jpg', 'fixture.jpg', '.jpg', NULL, 100, 'seen'
                    );
                    CREATE TABLE people (id INTEGER PRIMARY KEY, display_name TEXT, normalized_name TEXT UNIQUE);
                    CREATE TABLE folder_people (
                        folder_id INTEGER REFERENCES folders(id), person_id INTEGER REFERENCES people(id),
                        UNIQUE (folder_id, person_id)
                    );
                    INSERT INTO people VALUES (7, 'Ana', 'ana');
                    INSERT INTO folder_people VALUES (13, 7);
                """)
            repository = Repository(db_path)
            repository.init_schema()
            app = ApplicationService(repository, static_owner_chat_ids=(10,))
            path = "2024/picnic/fixture.jpg"
            photo = app.get_photo_tags(10, [path])[0]
            self.assertEqual(photo["people"], [])
            self.assertRegex(photo["identity"], r"^[0-9a-f]{32}$")
            self.assertEqual([item.path for item in app.search_folders("Ana")], ["2024/picnic"])
            self.assertEqual(app.search_confirmed_images("Ana"), [])
            updated = app.save_photo_tags(
                10, {path: photo["identity"]}, add_people={7}, remove_people=set(),
                manual_add={"gallery"}, manual_remove=set(),
            )
            repository.init_schema()
            self.assertEqual(app.get_photo_tags(10, [path]), updated)
            self.assertEqual([item.path for item in app.search_confirmed_images(7)], [path])
            with repository.session() as connection:
                self.assertEqual(connection.execute("SELECT id FROM images").fetchone()["id"], 21)
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
