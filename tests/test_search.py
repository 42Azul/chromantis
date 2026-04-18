from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser
from chromantis.search.service import SearchService
from chromantis.source import ArchiveScanner, LocalArchiveSource


PHOTOS_ROOT = Path(__file__).parent / "fixtures" / "ftp_tree" / "server_root" / "photos" / "archive"


class SearchServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = str(Path(self.temp_dir.name) / "chromantis.db")
        self.repository = Repository(db_path)
        self.repository.init_schema()
        scanner = ArchiveScanner(LocalArchiveSource(str(PHOTOS_ROOT)), self.repository, PathParser())
        scanner.scan()
        self.service = SearchService(self.repository)
        self.service.create_person("Pablo")
        self.service.add_person_alias("Pablo", "pablito")
        self.service.link_person_to_folder("Pablo", "2021/2021-08-15_city_trip")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_search_folders_by_year_and_keyword(self) -> None:
        results = self.service.search_folders("2023 winter")
        self.assertEqual(len(results), 1)
        self.assertIn("year=2023", results[0].reason)
        self.assertIn('title~"winter"', results[0].reason)

    def test_search_images_by_tag(self) -> None:
        results = self.service.search_images("city")
        self.assertEqual(len(results), 2)
        self.assertTrue(all("city" in result.reason for result in results))

    def test_search_images_by_person_alias_and_year_range(self) -> None:
        results = self.service.search_images("pablito 2020-2021")

        self.assertEqual(len(results), 2)
        self.assertTrue(all('person="Pablo"' in result.reason for result in results))
        self.assertTrue(all("year_range=2020-2021" in result.reason for result in results))

    def test_search_images_by_person_text_without_folder_link(self) -> None:
        self.service.create_person("Winter")

        results = self.service.search_images("winter")

        self.assertGreaterEqual(len(results), 1)
        self.assertTrue(any('person_text="Winter"' in result.reason for result in results))

    def test_search_folders_by_person(self) -> None:
        results = self.service.search_folders("Pablo")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].folder_path, "2021/2021-08-15_city_trip")
        self.assertIn('person="Pablo"', results[0].reason)

    def test_random_image_is_filtered(self) -> None:
        result = self.service.random_image("2019")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2019)
