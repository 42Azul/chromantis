from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable
from contextlib import suppress
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock

from chromantis.source.adapters import ArchiveSource, LocalArchiveSource


logger = logging.getLogger(__name__)
SOURCE_BYTES = 32 * 1024 * 1024
MAX_PIXELS = 30_000_000
THUMBNAIL_EDGE = 480
CACHE_NAME = re.compile(r"[0-9a-f]{64}\.jpg")
MAX_ENTRIES = 2048


class PreviewUnavailable(ValueError):
    pass


class ThumbnailCache:
    def __init__(
        self, directory: Path, budget: int, source: ArchiveSource, render: Callable[[bytes], bytes]
    ):
        self.directory = directory
        self.budget = budget
        self.source = source
        self.render = render
        self._disk = Lock()
        self._rendering = Lock()
        self._prepared = False

    def get(self, path: str, fingerprint: tuple[str, int | None, str | None]) -> bytes:
        root, size, _ = fingerprint
        if root != self.source.source_root:
            raise PreviewUnavailable("Reindex the configured archive to preview this image.")
        if size is not None and size > SOURCE_BYTES:
            raise PreviewUnavailable("Image is too large for a thumbnail.")
        file = self._cache_path(path, fingerprint)
        if file is not None and (hit := self._cached(file)) is not None:
            return hit
        with self._rendering:
            if file is not None and (hit := self._cached(file)) is not None:
                return hit
            content = self.source.read_bytes(path, max_bytes=SOURCE_BYTES)
            thumbnail = self.render(content)
            if file is not None and len(content) == size and len(thumbnail) <= self.budget:
                self._store(file, thumbnail)
            return thumbnail

    def peek(self, path: str, fingerprint: tuple[str, int | None, str | None]) -> bytes | None:
        file = self._cache_path(path, fingerprint)
        return self._cached(file) if file is not None else None

    def _cache_path(self, path: str, fingerprint: tuple[str, int | None, str | None]) -> Path | None:
        root, size, modified_at = fingerprint
        # An incomplete fingerprint cannot safely identify a cached revision.
        if root != self.source.source_root or size is None or size > SOURCE_BYTES or modified_at is None:
            return None
        key = sha256(json.dumps([1, path, root, size, modified_at]).encode()).hexdigest()
        return self.directory / f"{key}.jpg"

    def _cached(self, file: Path) -> bytes | None:
        with self._disk:
            try:
                if not self._prepared:
                    self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
                    for partial in self.directory.glob(".preview-*"):
                        partial.unlink()
                    self._make_room(0)
                    self._prepared = True
                if not file.is_symlink():
                    return file.read_bytes()
            except FileNotFoundError:
                pass
            except OSError:
                logger.warning("Could not read the thumbnail cache.", exc_info=True)
        return None

    def _store(self, file: Path, thumbnail: bytes) -> None:
        with self._disk:
            temporary = None
            try:
                if not self._prepared:
                    return
                self._make_room(len(thumbnail))
                with NamedTemporaryFile(dir=self.directory, prefix=".preview-", delete=False) as handle:
                    temporary = Path(handle.name)
                    handle.write(thumbnail)
                temporary.replace(file)
            except OSError:
                logger.warning("Could not save a thumbnail in the cache.", exc_info=True)
            finally:
                if temporary is not None:
                    with suppress(OSError):
                        temporary.unlink(missing_ok=True)

    def _make_room(self, incoming: int) -> None:
        entries = []
        total = 0
        with os.scandir(self.directory) as files:
            for entry in files:
                if CACHE_NAME.fullmatch(entry.name) and entry.is_file(follow_symlinks=False):
                    info = entry.stat(follow_symlinks=False)
                    entries.append((info.st_mtime_ns, Path(entry.path), info.st_size))
                    total += info.st_size
        count = len(entries) + bool(incoming)
        if total + incoming <= self.budget and count <= MAX_ENTRIES:
            return
        for _, path, size in sorted(entries):
            path.unlink()
            total -= size
            count -= 1
            if total + incoming <= self.budget and count <= MAX_ENTRIES:
                break


def build_thumbnail_cache(
    sqlite_path: str, budget_mib: int, source: ArchiveSource,
) -> ThumbnailCache | None:
    if not budget_mib:
        return None
    database = Path(sqlite_path).resolve()
    directory = database.with_name(f"{database.name}.thumbnails").resolve()
    if isinstance(source, LocalArchiveSource) and directory.is_relative_to(source.root_path):
        logger.warning("The thumbnail cache must be outside the read-only photo archive.")
        return None
    try:
        from PIL import Image, ImageOps
    except ImportError:
        logger.warning("Install chromantis[thumbnails] to enable thumbnail generation.")
        return None

    def render(content: bytes) -> bytes:
        try:
            with Image.open(BytesIO(content), formats=("JPEG", "PNG", "GIF", "WEBP")) as image:
                if image.width * image.height > MAX_PIXELS:
                    raise PreviewUnavailable("Image resolution exceeds the thumbnail limit.")
                image.thumbnail((THUMBNAIL_EDGE, THUMBNAIL_EDGE))
                upright = ImageOps.exif_transpose(image).convert("RGB")
                upright.info.clear()
                out = BytesIO()
                upright.save(out, "JPEG", quality=75)
                return out.getvalue()
        except (Image.DecompressionBombError, OSError, SyntaxError) as exc:
            raise PreviewUnavailable("No thumbnail is available for this image.") from exc

    return ThumbnailCache(directory, budget_mib * 1024 * 1024, source, render)
