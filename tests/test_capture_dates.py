from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from unittest.mock import MagicMock, call, patch
from urllib.parse import urlencode

from chromantis.api.server import ApiServer, make_api_handler
from chromantis.app import ApplicationService
from chromantis.app.capture_dates import EXIF_PREFIX_BYTES, index_capture_dates, jpeg_capture_date
from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser
from chromantis.source import ArchiveScanner, LocalArchiveSource
from chromantis.source.adapters import FtpArchiveSource


ALBUM = "2024/2024-08-04_beach"
PATH = ALBUM + "/001.jpg"
REPO = Path(__file__).resolve().parents[1]


class CaptureDatesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.archive = self.directory / "archive"
        self.photo = self.archive / PATH
        self.photo.parent.mkdir(parents=True)
        self.source = LocalArchiveSource(str(self.archive))
        self.repository = Repository(str(self.directory / "index.db"))
        self.repository.init_schema()
        self.scanner = ArchiveScanner(self.source, self.repository, PathParser())

    def save_jpeg(self, path, capture=None):
        try:
            from PIL import ExifTags, Image
        except ImportError:
            self.skipTest("Install chromantis[thumbnails] to test real EXIF extraction")
        with Image.new("RGB", (32, 24), "red") as image:
            exif = image.getexif()
            exif[ExifTags.Base.DateTime] = "2024:08:06 18:20:00"
            if capture is not None:
                exif[ExifTags.IFD.Exif] = {ExifTags.Base.DateTimeOriginal: capture}
            exif[ExifTags.IFD.GPSInfo] = {1: "N", 2: (1, 2, 3), 3: "E", 4: (4, 5, 6)}
            image.save(path, exif=exif)

    def test_real_exif_is_bounded_resumable_and_does_not_decode_pixels(self):
        self.save_jpeg(self.photo, "2023:02:02 12:30:00")
        without_capture = self.photo.with_name("002.jpg")
        self.save_jpeg(without_capture)
        with without_capture.open("ab") as handle:
            handle.write(b"\x00" * EXIF_PREFIX_BYTES)
        self.scanner.scan()
        original = self.photo.read_bytes()
        with patch("PIL.JpegImagePlugin.JpegImageFile.load", side_effect=AssertionError("Must not decode pixels")):
            with patch.object(self.source, "read_prefix", wraps=self.source.read_prefix) as reader:
                self.assertEqual(index_capture_dates(self.source, self.repository, 1, ALBUM).found, 1)
                self.assertEqual(index_capture_dates(self.source, self.repository, 1, ALBUM).missing, 1)
                self.assertEqual(index_capture_dates(self.source, self.repository, 1, ALBUM).found, 0)
                self.assertEqual(reader.call_args_list, [
                    call(PATH, EXIF_PREFIX_BYTES), call(ALBUM + "/002.jpg", EXIF_PREFIX_BYTES),
                ])
        indexed = self.repository.image_dates(PATH)
        self.assertEqual(indexed["capture_date"], "2023-02-02")
        self.assertEqual(indexed["event_date"], "2024-08-04")
        self.assertEqual(indexed["capture_date_confidence"], "camera_reported")
        self.assertNotIn("gps", json.dumps(indexed).lower())
        self.assertIsNone(self.repository.image_dates(ALBUM + "/002.jpg")["capture_date"])
        self.scanner.scan()
        self.assertEqual(self.repository.image_dates(PATH), indexed)
        self.assertEqual(self.photo.read_bytes(), original)

    def test_capture_date_refreshes_after_source_changes_and_stale_writes_are_rejected(self):
        self.save_jpeg(self.photo, "2023:02:02 12:30:00")
        self.scanner.scan()
        previous, = self.repository.capture_date_candidates(self.source.source_root, 1)
        self.assertEqual(index_capture_dates(self.source, self.repository, 1).found, 1)
        timestamp = self.photo.stat().st_mtime
        self.save_jpeg(self.photo, "2023:03:07 12:30:00")
        os.utime(self.photo, (timestamp + 5, timestamp + 5))
        self.scanner.scan(incremental=True)
        self.assertIsNone(self.repository.image_dates(PATH)["capture_date"])
        self.assertFalse(self.repository.save_capture_date(previous, "2023-02-02"))
        self.assertEqual(index_capture_dates(self.source, self.repository, 1).found, 1)
        self.assertEqual(self.repository.image_dates(PATH)["capture_date"], "2023-03-07")
        self.save_jpeg(self.photo, "2023:02:31 12:30:00")
        self.assertIsNone(jpeg_capture_date(self.photo.read_bytes()))

    def test_retryable_read_error_does_not_block_next_album_photo(self):
        self.save_jpeg(self.photo, "2023:02:02 12:30:00")
        self.save_jpeg(self.photo.with_name("002.jpg"), "2023:03:01 12:30:00")
        self.scanner.scan()
        self.photo.unlink()
        self.assertEqual(index_capture_dates(self.source, self.repository, 1).retry, 1)
        self.assertEqual(index_capture_dates(self.source, self.repository, 1).found, 1)
        self.assertEqual(self.repository.image_dates(ALBUM + "/002.jpg")["capture_date"], "2023-03-01")

    def test_metadata_api_authorization_and_legacy_database(self):
        self.photo.write_bytes(b"synthetic")
        self.scanner.scan()
        with self.repository.session() as connection:
            connection.execute("DROP TABLE image_capture_dates")
        self.repository.init_schema()
        app = ApplicationService(self.repository, static_owner_chat_ids=(10,))
        album = app.get_album_review(10)
        app.edit_album_context(10, ALBUM, album["id"], album["context_revision"], {"event_date": "2024-08-05"})
        _, code = app.family_access.invite("Synthetic")
        secret = app.family_access.redeem(code)
        server = ApiServer(("127.0.0.1", 0), make_api_handler(app, api_chat_tokens=((10, "owner-fixture"),)))
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)

        def get(path, cookie=None):
            connection = HTTPConnection(*server.server_address, timeout=2)
            try:
                headers = {"Cookie": cookie} if cookie else {}
                connection.request("GET", "/api/v1/image-dates?" + urlencode({"path": path}), headers=headers)
                response = connection.getresponse()
                return response.status, json.loads(response.read())
            finally:
                connection.close()

        self.assertEqual(get(PATH)[0], 401)
        cookie = f"chromantis_family={secret}"
        self.assertEqual(get("unindexed.jpg", cookie)[0], 404)
        status, response = get(PATH, cookie)
        self.assertEqual(status, 200)
        dates = response["item"]
        self.assertEqual(dates["event_date_source"], "album_correction")
        self.assertEqual(dates["event_date"], "2024-08-05")
        self.assertEqual(dates["indexed_event_date"], "2024-08-04")
        self.assertIsNotNone(dates["source_modified_at"])
        self.assertIsNone(dates["capture_date"])

    def test_cli_honors_album_scope_with_existing_database(self):
        self.save_jpeg(self.photo, "2023:02:02 12:30:00")
        another = self.archive / "2024/other/cover.jpg"
        another.parent.mkdir()
        self.save_jpeg(another, "2023:02:03 12:30:00")
        self.scanner.scan()
        env = dict(os.environ, SOURCE_TYPE="local", SOURCE_ROOT=str(self.archive), SQLITE_PATH=self.repository.sqlite_path)
        result = subprocess.run(
            [sys.executable, str(REPO / "scripts/index_capture_dates.py"), "--album", ALBUM, "--limit", "1"],
            env=env, cwd=self.directory, capture_output=True, text=True, check=True,
        )
        self.assertIn("Con fecha: 1", result.stdout)
        self.assertEqual(self.repository.image_dates(PATH)["capture_date"], "2023-02-02")
        self.assertIsNone(self.repository.image_dates("2024/other/cover.jpg")["capture_date"])

    def test_ftp_prefix_stops_and_closes_partial_transfer(self):
        source = FtpArchiveSource("synthetic", "synthetic", "synthetic", "/photos")
        ftp = MagicMock()
        ftp.__enter__.return_value = ftp

        def transfer(command, receive):
            self.assertEqual(command, f"RETR /photos/{PATH}")
            receive(b"abc")
            receive(b"def")
            self.fail("Continued reading after the requested prefix")

        ftp.retrbinary.side_effect = transfer
        with patch.object(source, "_connect", return_value=ftp):
            self.assertEqual(source.read_prefix(PATH, 4), b"abcd")
        ftp.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
