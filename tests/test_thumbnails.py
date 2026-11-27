from __future__ import annotations

import os
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from ftplib import error_perm, error_temp
from http.client import HTTPConnection
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from threading import Thread
from unittest.mock import Mock, patch
from urllib.parse import urlencode

from chromantis.api.server import ApiServer, make_api_handler
from chromantis.api.thumbnails import SOURCE_BYTES, ThumbnailCache, build_thumbnail_cache
from chromantis.app import ApplicationService
from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser
from chromantis.source import ArchiveScanner, LocalArchiveSource
from chromantis.source.adapters import ArchiveReadLimit, FtpArchiveSource


IMAGE_PATH = "2024/beach/fixture.jpg"


class ThumbnailTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.archive = self.root / "archive"
        self.photo = self.archive / IMAGE_PATH
        self.photo.parent.mkdir(parents=True)
        self.photo.write_bytes(b"synthetic original")
        self.source = LocalArchiveSource(str(self.archive))
        self.repository = Repository(str(self.root / "index.db"))
        self.repository.init_schema()
        self.scanner = ArchiveScanner(self.source, self.repository, PathParser())
        self.scanner.scan()
        self.app = ApplicationService(self.repository, static_owner_chat_ids=(10,))
        self.reader = Mock(wraps=self.source.read_bytes)
        original_reader = self.source.read_bytes
        self.source.read_bytes = self.reader
        self.cache_dir = self.root / "cache"
        self.cache = ThumbnailCache(self.cache_dir, 10, self.source, lambda content: content[:7])
        self.start_server(self.cache, original_reader)

    def start_server(self, cache, original_reader):
        server = ApiServer(("127.0.0.1", 0), make_api_handler(
            self.app, api_chat_tokens=((10, "owner-test"),), image_fetcher=original_reader, thumbnails=cache,
        ))
        self.address = server.server_address
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)

    def request(self, path, *, token="owner-test", cookie=None):
        connection = HTTPConnection(*self.address, timeout=3)
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if cookie:
            headers["Cookie"] = cookie
        try:
            connection.request("GET", "/api/v1" + path, headers=headers)
            response = connection.getresponse()
            self.assertEqual(response.getheader("Cache-Control"), "no-store")
            return response.status, response.getheader("Content-Type"), response.read()
        finally:
            connection.close()

    def test_album_cover_is_stable_and_skips_an_unavailable_candidate(self):
        album = self.photo.parent
        other = album / "second.jpg"
        other.write_bytes(b"second synthetic original")
        self.scanner.scan(incremental=True)
        paths = sorted(
            (IMAGE_PATH, other.relative_to(self.archive).as_posix()),
            key=lambda path: sha256(path.encode()).digest(),
        )
        broken = self.archive / paths[0]
        broken.unlink()
        route = "/album-cover?" + urlencode({"path": album.relative_to(self.archive)})
        grant, code = self.app.family_access.invite("synthetic")
        cookie = "chromantis_family=" + self.app.family_access.redeem(code)
        self.assertEqual(self.request(route, token=None)[0], 401)
        expected = (self.archive / paths[1]).read_bytes()[:7]
        for _ in range(2):
            self.assertEqual(self.request(route, token=None, cookie=cookie), (200, "image/jpeg", expected))
        self.app.family_access.revoke(grant)
        self.assertEqual(self.request(route, token=None, cookie=cookie)[0], 401)

    def test_ftp_album_cover_skips_a_retr_550_but_stops_on_source_failure(self):
        other = self.photo.parent / "second.jpg"
        other.write_bytes(b"second synthetic original")
        self.scanner.scan(incremental=True)
        album = self.photo.parent.relative_to(self.archive).as_posix()
        paths = sorted((IMAGE_PATH, f"{album}/second.jpg"), key=lambda path: sha256(path.encode()).digest())
        source = FtpArchiveSource("example", "example", "example", self.source.source_root)
        cache = ThumbnailCache(self.cache_dir, 0, source, lambda content: content[:7])
        self.start_server(cache, self.source.read_bytes)
        route = "/album-cover?" + urlencode({"path": album})

        expected = (self.archive / paths[1]).read_bytes()

        def refuse_first(command, collect):
            if command.endswith("/" + paths[0]):
                raise error_perm("550 File unavailable")
            collect(expected)

        with patch.object(source, "_connect") as connect:
            ftp = connect.return_value.__enter__.return_value
            ftp.retrbinary.side_effect = error_temp("421 Service unavailable")
            self.assertEqual(self.request(route)[0], 502)
            ftp.retrbinary.assert_called_once()
            ftp.retrbinary.reset_mock()
            ftp.retrbinary.side_effect = refuse_first
            self.assertEqual(self.request(route), (200, "image/jpeg", expected[:7]))
            self.assertEqual(ftp.retrbinary.call_count, 2)

    def test_album_cover_uses_cached_fallback_without_more_archive_requests(self):
        other = self.photo.parent / "second.jpg"
        other.write_bytes(b"second synthetic original")
        self.scanner.scan(incremental=True)
        album = self.photo.parent.relative_to(self.archive).as_posix()
        first, fallback = sorted(
            (IMAGE_PATH, f"{album}/second.jpg"), key=lambda path: sha256(path.encode()).digest(),
        )
        expected = (self.archive / fallback).read_bytes()[:7]
        self.assertEqual(self.request("/thumbnail?" + urlencode({"path": fallback})),
                         (200, "image/jpeg", expected))
        _, code = self.app.family_access.invite("synthetic")
        cookie = "chromantis_family=" + self.app.family_access.redeem(code)
        self.archive.rename(self.root / "disconnected")
        self.reader.reset_mock()
        route = "/album-cover?" + urlencode({"path": album})
        self.assertEqual(self.request(route, token=None, cookie=cookie), (200, "image/jpeg", expected))
        self.reader.assert_called_once_with(first, max_bytes=SOURCE_BYTES)

    def test_album_cover_skips_oversized_photos_before_limiting_candidates(self):
        for number in range(12):
            with (self.photo.parent / f"00-{number:02}.jpg").open("wb") as file:
                file.truncate(SOURCE_BYTES + 1)
        self.scanner.scan(incremental=True)
        route = "/album-cover?" + urlencode({"path": self.photo.parent.relative_to(self.archive)})
        self.assertEqual(self.request(route), (200, "image/jpeg", b"synthet"))
        self.reader.assert_called_once_with(IMAGE_PATH, max_bytes=SOURCE_BYTES)

    def test_family_index_status_survives_source_disconnect_and_failed_scan(self):
        grant, code = self.app.family_access.invite("synthetic")
        cookie = "chromantis_family=" + self.app.family_access.redeem(code)
        previous = self.repository.archive_index_status()["indexed_at"]
        self.archive.rename(self.root / "disconnected")
        scan_id, _ = self.repository.begin_scan(incremental=True)
        for state in ("running", "failed"):
            if state == "failed":
                self.repository.finish_scan(scan_id, "failed", error="SyntheticFailure")
            status, _, body = self.request("/archive-status", token=None, cookie=cookie)
            self.assertEqual(status, 200)
            item = json.loads(body)["item"]
            self.assertEqual(item["sync_status"], state)
            self.assertEqual(item["indexed_at"], previous)
        self.reader.assert_not_called()
        self.assertFalse(self.cache_dir.exists())
        self.app.family_access.revoke(grant)
        self.assertEqual(self.request("/archive-status", token=None, cookie=cookie)[0], 401)

    def test_cache_auth_invalidation_budget_and_original(self):
        preview = "/thumbnail?" + urlencode({"path": IMAGE_PATH})
        self.assertFalse(self.cache_dir.exists())
        self.assertEqual(self.request(preview, token=None)[0], 401)
        self.assertEqual(self.request("/thumbnail?path=unknown")[0], 404)
        self.reader.assert_not_called()
        self.assertEqual(self.request(preview), (200, "image/jpeg", b"synthet"))
        self.reader.assert_called_once_with(IMAGE_PATH, max_bytes=SOURCE_BYTES)
        self.assertEqual(self.request(preview)[2], b"synthet")
        self.assertEqual(self.reader.call_count, 1)

        # A warmed cache remains useful with no archive connection or original reads.
        self.reader.side_effect = OSError("offline")
        self.assertEqual(self.request(preview)[2], b"synthet")
        self.assertEqual(self.reader.call_count, 1)
        self.reader.side_effect = None
        original = b"another synthetic original"
        self.photo.write_bytes(original)
        self.scanner.scan(incremental=True)
        self.assertEqual(self.request(preview)[2], b"another")
        self.assertEqual(self.reader.call_count, 2)
        self.assertEqual(sum(path.stat().st_size for path in self.cache_dir.iterdir()), 7)
        self.assertEqual(self.request("/image?" + urlencode({"path": IMAGE_PATH}))[2], original)

        _, code = self.app.family_access.invite("synthetic")
        cookie = "chromantis_family=" + self.app.family_access.redeem(code)
        self.assertEqual(self.request(preview, token=None, cookie=cookie)[2], b"another")
        status, _, data = self.request("/archive-status", token=None, cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn(b'"thumbnails": true', data)
        self.assertIn(b'"sync_status": "succeeded"', data)

    def test_uses_fingerprint_even_when_file_size_is_unchanged(self):
        before = self.repository.indexed_image_fingerprint(IMAGE_PATH)
        self.assertEqual(self.cache.get(IMAGE_PATH, before), b"synthet")
        timestamp = self.photo.stat().st_mtime
        self.photo.write_bytes(b"another byte scope")
        self.assertEqual(self.photo.stat().st_size, before[1])
        os.utime(self.photo, (timestamp + 5, timestamp + 5))
        self.scanner.scan(incremental=True)
        after = self.repository.indexed_image_fingerprint(IMAGE_PATH)
        self.assertNotEqual(before, after)
        self.assertEqual(self.cache.get(IMAGE_PATH, after), b"another")

    def test_parallel_requests_share_one_render_and_incomplete_metadata_is_uncached(self):
        fingerprint = self.repository.indexed_image_fingerprint(IMAGE_PATH)
        with ThreadPoolExecutor(4) as pool:
            previews = list(pool.map(lambda _: self.cache.get(IMAGE_PATH, fingerprint), range(4)))
        self.assertEqual(previews, [b"synthet"] * 4)
        self.assertEqual(self.reader.call_count, 1)
        for _ in range(2):
            self.cache.get(IMAGE_PATH, (self.source.source_root, None, None))
        self.assertEqual(self.reader.call_count, 3)
        self.assertEqual(len(list(self.cache_dir.iterdir())), 1)

    def test_only_sanitized_status_and_no_automatic_original_after_failure(self):
        self.reader.side_effect = OSError("synthetic source details")
        self.assertEqual(self.request("/thumbnail?" + urlencode({"path": IMAGE_PATH}))[0], 502)
        scan_id, _ = self.repository.begin_scan(incremental=True)
        self.repository.finish_scan(scan_id, "failed", error="private fixture path")
        status, _, data = self.request("/archive-status")
        self.assertEqual(status, 200)
        self.assertIn(b'"sync_status": "failed"', data)
        self.assertIn(b'"indexed_at": "', data)
        self.assertNotIn(b"private fixture path", data)
        self.assertFalse(list(self.cache_dir.iterdir()))
        self.assertIsNone(build_thumbnail_cache(str(self.archive / "index.db"), 1, self.source))

    def test_local_and_ftp_preview_source_reads_have_a_real_byte_limit(self):
        with self.assertRaises(ArchiveReadLimit):
            self.source.read_bytes(IMAGE_PATH, max_bytes=4)
        source = FtpArchiveSource("example", "example", "example", "/synthetic")
        client = Mock()
        manager = Mock()
        manager.__enter__ = Mock(return_value=client)
        manager.__exit__ = Mock(return_value=False)

        def stream(command, receive):
            self.assertEqual(command, f"RETR /synthetic/{IMAGE_PATH}")
            receive(b"123")
            receive(b"456")
            self.fail("Read more than the budget")

        client.retrbinary.side_effect = stream
        with patch.object(source, "_connect", return_value=manager):
            with self.assertRaises(ArchiveReadLimit):
                source.read_bytes(IMAGE_PATH, max_bytes=4)
        client.close.assert_called_once()

    def test_pillow_generates_small_oriented_jpeg_without_original_metadata(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Install chromantis[thumbnails] to exercise actual rendering")
        with Image.new("RGB", (960, 720), "red") as photo:
            exif = photo.getexif()
            exif[274] = 6  # Rotate to portrait.
            exif[315] = "Synthetic photographer"
            photo.save(self.photo, exif=exif)
        original = self.photo.read_bytes()
        self.scanner.scan()
        cache = build_thumbnail_cache(self.repository.sqlite_path, 1, self.source)
        thumbnail = cache.get(IMAGE_PATH, self.repository.indexed_image_fingerprint(IMAGE_PATH))
        with Image.open(BytesIO(thumbnail)) as rendered:
            self.assertEqual(rendered.size, (360, 480))
            self.assertEqual(rendered.format, "JPEG")
            self.assertFalse(rendered.getexif())
        self.assertLess(len(thumbnail), len(original))
        self.assertEqual(self.photo.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
