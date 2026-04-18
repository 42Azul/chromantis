from __future__ import annotations

import logging
from dataclasses import dataclass

from chromantis.db.repository import Repository, ScanSummary
from chromantis.parsing.path_parser import PathParseError, PathParser
from chromantis.source.adapters import ArchiveSource

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanResult:
    summary: ScanSummary
    skipped_paths: tuple[str, ...]


class ArchiveScanner:
    def __init__(self, source: ArchiveSource, repository: Repository, parser: PathParser):
        self.source = source
        self.repository = repository
        self.parser = parser

    def scan(self, progress_every: int = 100) -> ScanResult:
        logger.info("Starting archive scan under root %s", self.source.source_root)
        entries = self.source.iter_entries()
        scan_seen_at = self.repository.begin_scan()
        skipped_paths: list[str] = []
        folders_indexed = 0
        images_indexed = 0
        processed_entries = 0
        yielded_entries = 0
        listed_directories = 0

        with self.repository.session() as connection:
            for entry in entries:
                yielded_entries += 1
                processed_entries += 1
                if entry.is_dir:
                    listed_directories += 1
                    logger.debug("Skipping directory entry %s", entry.path)
                    self._log_progress(
                        processed_entries,
                        images_indexed,
                        listed_directories,
                        skipped_paths,
                        progress_every,
                    )
                    continue
                if not self._is_supported_image(entry.path):
                    logger.debug("Skipping non-image file %s", entry.path)
                    self._log_progress(
                        processed_entries,
                        images_indexed,
                        listed_directories,
                        skipped_paths,
                        progress_every,
                    )
                    continue
                try:
                    record = self.parser.parse_image_path(
                        source_root=self.source.source_root,
                        relative_path=entry.path,
                        file_size=entry.size,
                        modified_at=entry.modified_at,
                    )
                except PathParseError as exc:
                    logger.debug("Skipping invalid image path %s: %s", entry.path, exc)
                    skipped_paths.append(entry.path)
                    self._log_progress(
                        processed_entries,
                        images_indexed,
                        listed_directories,
                        skipped_paths,
                        progress_every,
                    )
                    continue

                self.repository.upsert_image_record(connection, record, scan_seen_at)
                logger.debug(
                    "Indexed image %s in folder %s with tags=%s",
                    record.file_path,
                    record.folder_path,
                    [tag for tag, _source in record.folder_tags],
                )
                folders_indexed += 1
                images_indexed += 1
                self._log_progress(
                    processed_entries,
                    images_indexed,
                    listed_directories,
                    skipped_paths,
                    progress_every,
                )

            deleted_folders, deleted_images = self.repository.prune_stale(
                connection, scan_seen_at
            )

        logger.info(
            "Finished archive scan root=%s entries_seen=%d directories=%d images_indexed=%d skipped=%d deleted_images=%d deleted_folders=%d",
            self.source.source_root,
            yielded_entries,
            listed_directories,
            images_indexed,
            len(skipped_paths),
            deleted_images,
            deleted_folders,
        )

        return ScanResult(
            summary=ScanSummary(
                folders_indexed=folders_indexed,
                images_indexed=images_indexed,
                skipped_paths=len(skipped_paths),
                deleted_folders=deleted_folders,
                deleted_images=deleted_images,
            ),
            skipped_paths=tuple(skipped_paths),
        )

    def fetch_image_bytes(self, relative_path: str) -> bytes:
        logger.debug("Fetching image bytes for %s", relative_path)
        return self.source.read_bytes(relative_path)

    @staticmethod
    def _log_progress(
        processed_entries: int,
        images_indexed: int,
        listed_directories: int,
        skipped_paths: list[str],
        progress_every: int,
    ) -> None:
        if progress_every <= 0:
            return
        if processed_entries == 1 or processed_entries % progress_every == 0:
            logger.info(
                "Scan progress: entries_seen=%d directories=%d indexed_images=%d skipped=%d",
                processed_entries,
                listed_directories,
                images_indexed,
                len(skipped_paths),
            )

    @staticmethod
    def _is_supported_image(path: str) -> bool:
        lower_path = path.lower()
        return any(lower_path.endswith(extension) for extension in IMAGE_EXTENSIONS)
