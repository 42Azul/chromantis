from __future__ import annotations

import unittest

from chromantis.parsing.path_parser import PathParseError, PathParser, extract_event_date


class PathParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = PathParser()

    def test_parse_dated_folder_and_tags(self) -> None:
        record = self.parser.parse_image_path(
            source_root="/photos",
            relative_path="2021/2021-08-15_city_trip/IMG_001.jpg",
            file_size=123,
            modified_at="2024-01-01T00:00:00+00:00",
        )
        self.assertEqual(record.year, 2021)
        self.assertEqual(record.event_date, "2021-08-15")
        self.assertIn(("city", "path"), record.folder_tags)
        self.assertIn(("summer", "rule"), record.folder_tags)
        self.assertEqual(record.folder_slug, "2021 08 15 city trip")

    def test_compact_year_first_folder_dates(self) -> None:
        record = self.parser.parse_image_path(
            "/photos", "2024(2)/20240229 - Reunión/IMG_0001.jpg", 123, None
        )
        self.assertEqual(record.event_date, "2024-02-29")
        self.assertIn(("2024-02", "rule"), record.folder_tags)
        for name in ("20240230 - Reunión", "20230228 - Reunión", "29022024 - Reunión", "202402291"):
            with self.subTest(name=name):
                self.assertIsNone(extract_event_date(name, year=2024))

    def test_parse_undated_folder(self) -> None:
        record = self.parser.parse_image_path(
            source_root="/photos",
            relative_path="2023/winter_family_dinner/DSC_1203.jpg",
            file_size=10,
            modified_at=None,
        )
        self.assertIsNone(record.event_date)
        self.assertIn(("winter", "path"), record.folder_tags)

    def test_parse_allows_year_segment_with_suffix(self) -> None:
        record = self.parser.parse_image_path(
            source_root="/photos",
            relative_path="2004(2)/2004-01-05_archived_event/IMG_0001.jpg",
            file_size=10,
            modified_at=None,
        )
        self.assertEqual(record.year, 2004)
        self.assertEqual(record.folder_path, "2004(2)/2004-01-05_archived_event")

    def test_parse_rejects_invalid_year(self) -> None:
        with self.assertRaises(PathParseError):
            self.parser.parse_image_path(
                source_root="/photos",
                relative_path="misc/winter_family_dinner/DSC_1203.jpg",
                file_size=10,
                modified_at=None,
            )

    def test_parse_rejects_invalid_depth(self) -> None:
        with self.assertRaises(PathParseError):
            self.parser.parse_image_path(
                source_root="/photos",
                relative_path="2023/winter_family_dinner/nested/DSC_1203.jpg",
                file_size=10,
                modified_at=None,
            )
