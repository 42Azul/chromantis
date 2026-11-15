from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from chromantis.db.repository import ResolvedPerson
from chromantis.search.query_parser import parse_query
from chromantis.search.service import SearchResult
from scripts.evaluate_visual_search import ASSETS, eligible, verify_assets


class VisualSearchTrialTests(unittest.TestCase):
    def test_similarity_candidates_require_both_year_and_curated_person_link(self):
        ana = ResolvedPerson(1, "Ana", ("ana", "ani"))
        query = parse_query("red bicycle Ani 2024", {"ani": ana})
        linked = "2024/linked"
        person_folders = {1: {linked, "2023/linked"}}
        for folder, year, expected in ((linked, 2024, True), ("2023/linked", 2023, False),
                                       ("2024/ana in title", 2024, False)):
            candidate = SearchResult("image", folder + "/photo.png", folder, "fixture", year, folder)
            self.assertEqual(eligible(candidate, query, person_folders), expected)
        self.assertFalse(eligible(SearchResult("image", linked + "/photo.png", "", "", 2024, linked), query, {}))

    def test_unverified_model_files_are_rejected_before_inference(self):
        with tempfile.TemporaryDirectory() as path:
            directory = Path(path)
            first_asset = next(iter(ASSETS))
            (directory / first_asset).write_bytes(b"synthetic corrupt checkpoint")
            with self.assertRaisesRegex(ValueError, "Unexpected checksum"):
                verify_assets(directory)


if __name__ == "__main__":
    unittest.main()
