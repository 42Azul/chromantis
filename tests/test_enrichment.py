from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chromantis.app.enrichment import CommandImageEnricher, enrich_images
from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser
from chromantis.search.service import SearchService
from chromantis.source import ArchiveScanner, LocalArchiveSource


class EnrichmentTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "photos"
        self.path = "2021/city/photo.jpg"
        image = root / self.path
        image.parent.mkdir(parents=True)
        image.write_bytes(b"example-test-photo")
        self.source = LocalArchiveSource(str(root))
        self.repository = Repository(str(Path(temp.name) / "old.db"))
        self.repository.init_schema()
        # Install the new table on a database that already holds real index data.
        with self.repository.session() as connection:
            connection.execute("DROP TABLE image_enrichment")
        ArchiveScanner(self.source, self.repository, PathParser()).scan()
        self.repository.init_schema()

    @staticmethod
    def provider(code: str, version: str = "1") -> CommandImageEnricher:
        return CommandImageEnricher("test-model", version, (sys.executable, "-c", code), 2)

    def test_archive_enrichment_keeps_provenance_and_optional_search_signals(self) -> None:
        provider = self.provider("""
import json
import sys
assert sys.stdin.buffer.read() == b"example-test-photo"
json.dump({"caption": "A kite in town", "ocr_text": "PAPER LANTERNS", "object_tags": ["bicycle"]}, sys.stdout)
""")
        self.assertEqual(enrich_images(self.source, self.repository, provider, 10).enriched, 1)
        self.assertEqual(enrich_images(self.source, self.repository, provider, 10).enriched, 0)
        with self.repository.connect() as connection:
            row = connection.execute("SELECT * FROM image_enrichment").fetchone()
            self.assertEqual((row["model"], row["version"]), ("test-model", "1"))
            self.assertEqual(json.loads(row["object_tags_json"]), ["bicycle"])
        self.assertEqual(SearchService(self.repository).search_images("kite"), [])
        search = SearchService(self.repository, include_enrichment=True)
        for keyword in ("kite", "lanterns", "bicycle"):
            result, = search.search_images(f"2021 city {keyword}")
            self.assertEqual(result.path, self.path)
            self.assertIn(f'enrichment~"{keyword}"', result.reason)
        self.assertEqual(search.search_images("2020 kite"), [])
        candidate = self.repository.list_enrichment_candidates(self.source.source_root, "test-model", "2", 1)[0]
        with self.repository.session() as connection:
            connection.execute("UPDATE images SET file_size = file_size + 1")
        self.assertFalse(self.repository.save_image_enrichment(candidate, "test-model", "2", "kite", "", ()))
        self.assertEqual(search.search_images("kite"), [])
        self.assertEqual(len(self.repository.list_enrichment_candidates(self.source.source_root, "test-model", "1", 1)), 1)

    def test_failed_enrichment_can_be_retried(self) -> None:
        failed = self.provider("print('invalid JSON')")
        with self.assertLogs("chromantis.app.enrichment", level="WARNING"):
            summary = enrich_images(self.source, self.repository, failed, 1)
        self.assertEqual(summary.failed, 1)
        valid = self.provider("""print('{"caption":"kite","ocr_text":"","object_tags":[]}')""")
        self.assertEqual(enrich_images(self.source, self.repository, valid, 1).enriched, 1)

    def test_enrichment_can_be_resumed_within_one_album(self) -> None:
        second = Path(self.source.source_root) / "2021/city/second.jpg"
        second.write_bytes(b"selected album")
        other = Path(self.source.source_root) / "2021/city_other/untouched.jpg"
        other.parent.mkdir()
        other.write_bytes(b"other album")
        ArchiveScanner(self.source, self.repository, PathParser()).scan()
        provider = self.provider("""print('{"caption":"","ocr_text":"kite","object_tags":[]}')""")
        with patch.object(self.source, "read_bytes", wraps=self.source.read_bytes) as read:
            self.assertEqual(enrich_images(self.source, self.repository, provider, 1, album="2021/city").enriched, 1)
            self.assertEqual(enrich_images(self.source, self.repository, provider, 1, album="2021/city").enriched, 1)
            self.assertEqual(enrich_images(self.source, self.repository, provider, 1, album="2021/city").enriched, 0)
            self.assertEqual({args[0] for args, _ in read.call_args_list}, {self.path, "2021/city/second.jpg"})
        pending = self.repository.list_enrichment_candidates(self.source.source_root, provider.model, provider.version, 1)
        self.assertEqual([candidate.path for candidate in pending], ["2021/city_other/untouched.jpg"])
