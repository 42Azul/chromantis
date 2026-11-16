from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_search.py"


@unittest.skipUnless(importlib.util.find_spec("PIL"), "The optional Pillow extra draws the synthetic fixtures")
class SearchEvaluationTests(unittest.TestCase):
    def test_report_exercises_the_baseline_without_using_the_configured_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            env = dict(os.environ, SOURCE_TYPE="invalid", SOURCE_ROOT=str(root / "absent"),
                       SQLITE_PATH=str(root / "untouched.db"))
            result = subprocess.run([sys.executable, str(SCRIPT), "--repeat", "1"], cwd=root, env=env,
                                    capture_output=True, check=True, text=True)
            self.assertFalse((root / "untouched.db").exists())
        report = json.loads(result.stdout)
        self.assertEqual(report["images"], 9)
        self.assertEqual(report["lexical"]["exact_at_5_by_category"]["metadata"]["exact"], 4)
        self.assertEqual(report["lexical"]["recall_at_5_by_category"]["written_text"], 0)
        self.assertEqual(report["lexical"]["recall_at_5_by_category"]["visual"], 0)
        self.assertIsNone(report["lexical"]["recall_at_5_by_category"]["negative"])
        self.assertTrue(any(case["matches"] and "album_person=" in case["matches"][0]["reason"]
                            for case in report["lexical"]["cases"] if case["id"] == "person_alias"))


if __name__ == "__main__":
    unittest.main()
