from __future__ import annotations

import logging
from dataclasses import dataclass

from chromantis.db.repository import Repository, ScanSummary
from chromantis.parsing.path_parser import PathParseError, PathParser
from chromantis.source.adapters import ArchiveEntry, ArchiveSource

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanResult:
    summary: ScanSummary
    skipped_paths: tuple[str, ...]
    status: str = "succeeded"


class ArchiveScanner:
    def __init__(self, source: ArchiveSource, repository: Repository, parser: PathParser):
        self.source = source
        self.repository = repository
        self.parser = parser

    def scan(self, progress_every: int = 100, *, incremental: bool = False) -> ScanResult:
        scan_id, started_at = self.repository.begin_scan(incremental)
        logger.info("Starting %s scan %d", "incremental" if incremental else "full", scan_id)
        try:
            entries = self._list_images(progress_every)
            result = self._update_index(scan_id, started_at, entries, incremental)
        except (Exception, KeyboardInterrupt) as exc:
            self.repository.finish_scan(scan_id, "failed", error=type(exc).__name__)
            raise
        logger.info("Scan %d %s: %s", scan_id, result.status, result.summary)
        return result

    def _list_images(self, progress_every: int) -> dict[str, ArchiveEntry]:
        images = {}
        for count, entry in enumerate(self.source.iter_entries(), 1):
            if not entry.is_dir and any(entry.path.lower().endswith(ext) for ext in IMAGE_EXTENSIONS):
                images[entry.path] = entry
            if progress_every > 0 and (count == 1 or count % progress_every == 0):
                logger.info("Listed %d archive entries, found %d image paths", count, len(images))
        return images

    def _update_index(
        self, scan_id: int, started_at: str, entries: dict[str, ArchiveEntry], incremental: bool
    ) -> ScanResult:
        skipped: list[str] = []
        unchanged = indexed = 0
        root = self.source.source_root
        with self.repository.write_transaction() as connection:
            if self.repository.scan_is_superseded(connection, scan_id):
                summary = ScanSummary(0, 0, 0, 0, 0)
                self.repository.finish_scan(scan_id, "superseded", summary, connection=connection)
                return ScanResult(summary, (), "superseded")

            previous = self.repository.indexed_image_metadata(connection)
            for path, entry in entries.items():
                if (
                    incremental and entry.size is not None and entry.modified_at is not None
                    and previous.get(path) == (root, entry.size, entry.modified_at)
                ):
                    unchanged += 1
                    continue
                try:
                    record = self.parser.parse_image_path(root, path, entry.size, entry.modified_at)
                except PathParseError:
                    skipped.append(path)
                    continue
                self.repository.upsert_image_record(connection, record, started_at)
                indexed += 1

            missing = (previous.keys() - entries.keys()) | (previous.keys() & set(skipped))
            deleted_folders, deleted_images = self.repository.delete_missing_images(connection, missing)
            summary = ScanSummary(indexed, indexed, len(skipped), deleted_folders, deleted_images, unchanged)
            self.repository.finish_scan(scan_id, "succeeded", summary, connection=connection)
        return ScanResult(summary, tuple(skipped))

    def fetch_image_bytes(self, relative_path: str) -> bytes:
        logger.debug("Fetching image bytes for %s", relative_path)
        return self.source.read_bytes(relative_path)
