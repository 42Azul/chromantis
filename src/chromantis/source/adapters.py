from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from ftplib import FTP, all_errors, error_perm
from pathlib import Path, PurePosixPath
from typing import Iterator, Protocol

logger = logging.getLogger(__name__)

MAX_SCAN_DEPTH = 2
YEAR_DIR_RE = re.compile(r"^\d{4}(?:\(\d+\))?$")


@dataclass(frozen=True)
class ArchiveEntry:
    path: str
    is_dir: bool
    size: int | None = None
    modified_at: str | None = None


class ArchiveSource(Protocol):
    source_root: str

    def iter_entries(self, max_depth: int = MAX_SCAN_DEPTH) -> Iterator[ArchiveEntry]:
        ...

    def read_bytes(self, relative_path: str) -> bytes:
        ...

    def read_many_bytes(self, relative_paths: tuple[str, ...]) -> tuple[bytes, ...]:
        ...


class FtpArchiveSource:
    def __init__(self, host: str, user: str, password: str, source_root: str, port: int = 21, timeout: int = 30):
        self.host = host
        self.user = user
        self.password = password
        self.source_root = source_root
        self.port = port
        self.timeout = timeout

    def iter_entries(self, max_depth: int = MAX_SCAN_DEPTH) -> Iterator[ArchiveEntry]:
        ftp = self._connect()
        try:
            self._verify_root(ftp)
            yield from self._walk(ftp, "", max_depth=max_depth)
        finally:
            logger.debug("Closing FTP connection")
            ftp.quit()

    def read_bytes(self, relative_path: str) -> bytes:
        chunks: list[bytes] = []
        with self._connect() as ftp:
            absolute_path = self._absolute_path(relative_path)
            logger.debug("Downloading FTP file %s", absolute_path)
            ftp.retrbinary(f"RETR {absolute_path}", chunks.append)
        return b"".join(chunks)

    def read_many_bytes(self, relative_paths: tuple[str, ...]) -> tuple[bytes, ...]:
        if not relative_paths:
            return ()
        ftp = self._connect()
        try:
            logger.info("Downloading %d FTP files in a single session", len(relative_paths))
            payloads: list[bytes] = []
            for relative_path in relative_paths:
                absolute_path = self._absolute_path(relative_path)
                chunks: list[bytes] = []
                logger.debug("Downloading FTP file %s", absolute_path)
                ftp.retrbinary(f"RETR {absolute_path}", chunks.append)
                payloads.append(b"".join(chunks))
            return tuple(payloads)
        finally:
            logger.debug("Closing FTP connection")
            ftp.quit()

    def _connect(self) -> FTP:
        logger.info("Connecting to FTP %s:%s", self.host, self.port)
        ftp = FTP()
        ftp.connect(self.host, self.port, timeout=self.timeout)
        logger.info("Connected to FTP host %s:%s", self.host, self.port)
        ftp.login(self.user, self.password)
        logger.info("Authenticated to FTP as %s", self.user)
        return ftp

    def _verify_root(self, ftp: FTP) -> None:
        logger.info("Validating FTP root %s", self.source_root)
        ftp.cwd(self.source_root)
        logger.info("FTP root is accessible: %s", self.source_root)

    def _walk(
        self, ftp: FTP, current_relative_path: str, max_depth: int
    ) -> Iterator[ArchiveEntry]:
        logger.info(
            "Listing archive directory %s (depth=%d)",
            current_relative_path or ".",
            self._relative_depth(current_relative_path),
        )
        for name, facts in self._iter_directory_entries(
            ftp,
            self._absolute_path(current_relative_path),
        ):
            if name in {".", ".."}:
                continue
            relative_path = f"{current_relative_path.rstrip('/')}/{name}".strip("/")
            is_dir = facts.get("type") == "dir"
            modified = facts.get("modify")
            modified_at = None
            if modified:
                modified_at = datetime.strptime(
                    modified, "%Y%m%d%H%M%S"
                ).replace(tzinfo=timezone.utc).isoformat()
            size = int(facts["size"]) if "size" in facts and not is_dir else None
            entry = ArchiveEntry(
                path=relative_path,
                is_dir=is_dir,
                size=size,
                modified_at=modified_at,
            )
            entry_depth = self._relative_depth(relative_path)
            logger.debug(
                "Discovered archive entry path=%s is_dir=%s size=%s depth=%d",
                relative_path,
                is_dir,
                size,
                entry_depth,
            )
            if entry_depth == 1 and is_dir and not YEAR_DIR_RE.fullmatch(name):
                logger.info(
                    "Skipping non-year top-level branch %s under root %s",
                    relative_path,
                    self.source_root,
                )
                continue
            yield entry
            if is_dir:
                if entry_depth <= max_depth:
                    logger.debug("Descending into %s", relative_path)
                    yield from self._walk(ftp, relative_path, max_depth=max_depth)
                else:
                    logger.info(
                        "Skipping deeper traversal at %s (depth=%d, max_depth=%d)",
                        relative_path,
                        entry_depth,
                        max_depth,
                    )

    def _iter_directory_entries(
        self, ftp: FTP, current_absolute_path: str
    ) -> Iterator[tuple[str, dict[str, str]]]:
        try:
            logger.debug("Trying MLSD for %s", current_absolute_path)
            yield from ftp.mlsd(current_absolute_path)
            return
        except all_errors as exc:
            logger.warning("MLSD failed for %s: %s. Falling back to NLST.", current_absolute_path, exc)
        yield from self._iter_directory_entries_nlst(ftp, current_absolute_path)

    def _iter_directory_entries_nlst(
        self, ftp: FTP, current_absolute_path: str
    ) -> Iterator[tuple[str, dict[str, str]]]:
        previous_dir = ftp.pwd()
        ftp.cwd(current_absolute_path)
        try:
            names = ftp.nlst()
        finally:
            ftp.cwd(previous_dir)
        for raw_name in names:
            name = raw_name.strip().rstrip("/")
            if not name or name in {".", ".."}:
                continue
            basename = Path(name).name
            entry_path = f"{current_absolute_path.rstrip('/')}/{basename}"
            facts = self._facts_from_path_fallback(ftp, entry_path)
            logger.debug(
                "NLST fallback discovered entry path=%s type=%s size=%s",
                entry_path,
                facts.get("type"),
                facts.get("size"),
            )
            yield basename, facts

    def _facts_from_path_fallback(self, ftp: FTP, entry_path: str) -> dict[str, str]:
        facts: dict[str, str] = {}
        if self._can_cwd(ftp, entry_path):
            facts["type"] = "dir"
            return facts
        facts["type"] = "file"
        try:
            size = ftp.size(entry_path)
        except all_errors:
            size = None
        if size is not None:
            facts["size"] = str(size)
        try:
            modified = ftp.sendcmd(f"MDTM {entry_path}")
        except all_errors:
            modified = None
        if modified and modified.startswith("213 "):
            facts["modify"] = modified[4:].strip()
        return facts

    @staticmethod
    def _can_cwd(ftp: FTP, path: str) -> bool:
        previous_dir = ftp.pwd()
        try:
            ftp.cwd(path)
            return True
        except error_perm:
            return False
        finally:
            try:
                ftp.cwd(previous_dir)
            except all_errors:
                pass

    @staticmethod
    def _relative_depth(relative_path: str) -> int:
        if not relative_path:
            return 0
        return len([segment for segment in relative_path.split("/") if segment])

    def _absolute_path(self, relative_path: str) -> str:
        if not relative_path:
            return self.source_root
        normalized_relative_path = _normalize_relative_archive_path(relative_path)
        return f"{self.source_root.rstrip('/')}/{normalized_relative_path}"


class LocalArchiveSource:
    def __init__(self, source_root: str):
        self.root_path = Path(source_root).resolve()
        self.source_root = str(self.root_path)

    def iter_entries(self, max_depth: int = MAX_SCAN_DEPTH) -> Iterator[ArchiveEntry]:
        if not self.root_path.exists():
            raise FileNotFoundError(self.source_root)
        logger.info("Scanning local archive root %s", self.source_root)
        for path in sorted(self.root_path.rglob("*")):
            if path.is_symlink():
                logger.warning("Skipping symlinked local archive entry %s", path)
                continue
            resolved_path = path.resolve()
            if not resolved_path.is_relative_to(self.root_path):
                logger.warning(
                    "Skipping local archive entry outside configured root %s", path
                )
                continue
            relative_parts = path.relative_to(self.root_path).parts
            relative_depth = len(relative_parts)
            if relative_parts and not YEAR_DIR_RE.fullmatch(relative_parts[0]):
                logger.debug("Skipping local path outside year layout %s", path)
                continue
            if relative_depth == 1 and path.is_dir() and not YEAR_DIR_RE.fullmatch(path.name):
                logger.debug("Skipping non-year top-level local branch %s", path)
                continue
            if path.is_dir() and relative_depth > max_depth:
                logger.debug(
                    "Skipping local directory %s beyond max_depth=%d", path, max_depth
                )
                continue
            if not path.is_dir() and relative_depth > max_depth + 1:
                logger.debug(
                    "Skipping local file %s beyond max_depth=%d", path, max_depth
                )
                continue
            stat = path.stat()
            yield ArchiveEntry(
                path=path.relative_to(self.root_path).as_posix(),
                is_dir=path.is_dir(),
                size=None if path.is_dir() else stat.st_size,
                modified_at=datetime.fromtimestamp(
                    stat.st_mtime, timezone.utc
                ).isoformat(),
            )

    def read_bytes(self, relative_path: str) -> bytes:
        return self._absolute_path(relative_path).read_bytes()

    def read_many_bytes(self, relative_paths: tuple[str, ...]) -> tuple[bytes, ...]:
        return tuple(self.read_bytes(relative_path) for relative_path in relative_paths)

    def _absolute_path(self, relative_path: str) -> Path:
        normalized_relative_path = _normalize_relative_archive_path(relative_path)
        candidate = (self.root_path / normalized_relative_path).resolve()
        if not candidate.is_relative_to(self.root_path):
            raise ValueError(
                f"Archive path {relative_path!r} escapes configured root {self.source_root!r}"
            )
        return candidate


def _normalize_relative_archive_path(relative_path: str) -> str:
    raw_path = relative_path.strip().replace("\\", "/")
    if not raw_path:
        raise ValueError("Archive path must not be empty")
    pure_path = PurePosixPath(raw_path)
    if pure_path.is_absolute():
        raise ValueError("Archive path must be relative to the configured source root")
    normalized_parts = []
    for part in pure_path.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            raise ValueError("Archive path must not escape the configured source root")
        normalized_parts.append(part)
    if not normalized_parts:
        raise ValueError("Archive path must not be empty")
    return "/".join(normalized_parts)
