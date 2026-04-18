from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser
from chromantis.source import ArchiveScanner, LocalArchiveSource


FIXTURES_ROOT = Path(__file__).parent / "fixtures" / "ftp_tree" / "server_root"
PHOTOS_ROOT = FIXTURES_ROOT / "photos" / "archive"


class FTPScannerTests(unittest.TestCase):
    def _build_scanner(self, db_path: str, source_root: Path) -> tuple[Repository, ArchiveScanner]:
        repository = Repository(db_path)
        repository.init_schema()
        scanner = ArchiveScanner(
            source=LocalArchiveSource(str(source_root)),
            repository=repository,
            parser=PathParser(),
        )
        return repository, scanner

    def test_scan_indexes_only_files_under_configured_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "chromantis.db")
            repository, scanner = self._build_scanner(db_path, PHOTOS_ROOT)
            result = scanner.scan()

            self.assertEqual(result.summary.images_indexed, 5)
            self.assertEqual(result.summary.skipped_paths, 0)
            self.assertEqual(len(result.skipped_paths), 0)

            with repository.connect() as connection:
                folders = connection.execute("SELECT COUNT(*) FROM folders").fetchone()[0]
                images = connection.execute("SELECT COUNT(*) FROM images").fetchone()[0]
                self.assertEqual(folders, 3)
                self.assertEqual(images, 5)

    def test_reindex_prunes_stale_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "chromantis.db")
            local_root = Path(temp_dir) / "photos" / "archive"
            local_root.mkdir(parents=True)
            first_file = local_root / "2024" / "2024-01-01_new_year"
            first_file.mkdir(parents=True)
            image_path = first_file / "IMG_0001.jpg"
            image_path.write_text("image", encoding="utf-8")

            repository, scanner = self._build_scanner(db_path, local_root)
            scanner.scan()

            image_path.unlink()
            result = scanner.scan()

            self.assertEqual(result.summary.deleted_images, 1)

            with repository.connect() as connection:
                images = connection.execute("SELECT COUNT(*) FROM images").fetchone()[0]
                self.assertEqual(images, 0)

    def test_scan_does_not_descend_beyond_year_folder_image_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "chromantis.db")
            repository, scanner = self._build_scanner(db_path, PHOTOS_ROOT)
            result = scanner.scan()

            self.assertEqual(result.summary.images_indexed, 5)

            with repository.connect() as connection:
                nested = connection.execute(
                    "SELECT COUNT(*) FROM images WHERE file_path LIKE ?",
                    ("%nested%",),
                ).fetchone()[0]
                self.assertEqual(nested, 0)
