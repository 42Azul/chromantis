from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chromantis.app import ApplicationService

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

    def test_full_scan_refreshes_compact_date_and_keeps_manual_correction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "archive"
            album = "2024/20240229 - Reunión"
            photo = archive / album / "IMG_0001.jpg"
            photo.parent.mkdir(parents=True)
            photo.write_bytes(b"synthetic original")
            repository, scanner = self._build_scanner(str(root / "index.db"), archive)
            with patch("chromantis.parsing.path_parser.extract_event_date", return_value=None):
                scanner.scan()
            app = ApplicationService(repository, static_owner_chat_ids=(10,))
            item = app.get_album_review(10)
            self.assertIsNone(item["indexed_date"])
            app.edit_album_context(10, album, item["id"], item["context_revision"], {
                "event_date": "2024-02-28", "title": "Fecha de la reunión",
            })

            scanner.scan()
            updated = app.get_album_review(10)
            self.assertEqual(updated["indexed_date"], "2024-02-29")
            self.assertEqual(updated["event_date"], "2024-02-28")
            self.assertEqual(updated["title"], "Fecha de la reunión")
            self.assertEqual(photo.read_bytes(), b"synthetic original")

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

    def test_incremental_scan_only_updates_changed_images_and_deletes_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "archive"
            folder = root / "2021" / "city"
            folder.mkdir(parents=True)
            unchanged = folder / "keep.jpg"
            changed = folder / "change.jpg"
            missing = folder / "remove.jpg"
            for image in (unchanged, changed, missing):
                image.write_bytes(b"original")
            repository, scanner = self._build_scanner(str(Path(temp_dir) / "index.db"), root)
            with repository.session() as connection:
                connection.execute("DROP TABLE sync_runs")
            repository.init_schema()
            scanner.scan()

            changed.write_bytes(b"new contents")
            missing.unlink()
            (folder / "new.jpg").write_bytes(b"new")
            result = scanner.scan(incremental=True)

            self.assertEqual(result.summary.images_indexed, 2)
            self.assertEqual(result.summary.unchanged_images, 1)
            self.assertEqual(result.summary.deleted_images, 1)
            self.assertEqual(repository.get_index_stats().images, 3)
            self.assertEqual(scanner.scan(incremental=True).summary.images_indexed, 0)
            self.assertEqual(repository.list_sync_runs(1)[0]["status"], "succeeded")

    def test_incomplete_listing_keeps_previous_index_and_records_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository, scanner = self._build_scanner(str(Path(temp_dir) / "index.db"), PHOTOS_ROOT)
            scanner.scan()
            original = scanner.source

            class BrokenSource:
                source_root = original.source_root

                def iter_entries(self):
                    yield next(original.iter_entries())
                    raise OSError("simulated disconnect")

            scanner.source = BrokenSource()
            with self.assertRaises(OSError):
                scanner.scan(incremental=True)
            self.assertEqual(repository.get_index_stats().images, 5)
            latest = repository.list_sync_runs(1)[0]
            self.assertEqual((latest["status"], latest["error"]), ("failed", "OSError"))

    def test_older_scan_cannot_overwrite_newer_successful_scan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository, scanner = self._build_scanner(str(Path(temp_dir) / "index.db"), PHOTOS_ROOT)
            original = scanner.source

            class DelayedSource:
                source_root = original.source_root

                def iter_entries(self):
                    scanner.source = original
                    # Simulate an older process that pre-dates the shared scan lock.
                    scan_id, started_at = repository.begin_scan(incremental=True)
                    scanner._scan(scan_id, started_at, 0, incremental=True)
                    return iter(())

            scanner.source = DelayedSource()
            result = scanner.scan(incremental=True)
            self.assertEqual(result.status, "superseded")
            self.assertEqual(repository.get_index_stats().images, 5)

    def test_next_scan_marks_interrupted_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository, scanner = self._build_scanner(str(Path(temp_dir) / "index.db"), PHOTOS_ROOT)
            repository.begin_scan(incremental=False)
            scanner.scan()
            current, interrupted = repository.list_sync_runs(2)

            self.assertEqual(current["status"], "succeeded")
            self.assertEqual((interrupted["status"], interrupted["error"]), ("failed", "InterruptedScan"))
