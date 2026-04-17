from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from ftplib import FTP, all_errors, error_perm
from pathlib import Path
from typing import BinaryIO, Iterator, Protocol

logger = logging.getLogger(__name__)

MAX_SCAN_DEPTH = 2
YEAR_DIR_RE = re.compile(r"^\d{4}(?:\(\d+\))?$")

@dataclass(frozen=True)
class FTPEntry:
    path: str
    is_dir: bool
    size: int | None = None
    modified_at: str | None = None


class FTPClient(Protocol):
    def iter_entries(self, root: str, max_depth: int = MAX_SCAN_DEPTH) -> Iterator[FTPEntry]:
        ...

    def download_bytes(self, path: str) -> bytes:
        ...

    def download_many_bytes(self, paths: tuple[str, ...]) -> tuple[bytes, ...]:
        ...


class StdlibFTPClient:
    def __init__(self, host: str, user: str, password: str, port: int = 21, timeout: int = 30):
        self.host = host
        self.user = user
        self.password = password
        self.port = port
        self.timeout = timeout

    def iter_entries(self, root: str, max_depth: int = MAX_SCAN_DEPTH) -> Iterator[FTPEntry]:
        ftp = self._connect()
        try:
            self._verify_root(ftp, root)
            yield from self._walk(ftp, root, root, max_depth=max_depth)
        finally:
            logger.debug("Closing FTP connection")
            ftp.quit()

    def download_bytes(self, path: str) -> bytes:
        chunks: list[bytes] = []
        with self._connect() as ftp:
            logger.debug("Downloading FTP file %s", path)
            ftp.retrbinary(f"RETR {path}", chunks.append)
        return b"".join(chunks)

    def download_many_bytes(self, paths: tuple[str, ...]) -> tuple[bytes, ...]:
        if not paths:
            return ()
        ftp = self._connect()
        try:
            logger.info("Downloading %d FTP files in a single session", len(paths))
            payloads: list[bytes] = []
            for path in paths:
                chunks: list[bytes] = []
                logger.debug("Downloading FTP file %s", path)
                ftp.retrbinary(f"RETR {path}", chunks.append)
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

    def _verify_root(self, ftp: FTP, root: str) -> None:
        logger.info("Validating FTP root %s", root)
        ftp.cwd(root)
        logger.info("FTP root is accessible: %s", root)

    def _walk(
        self, ftp: FTP, root: str, current_path: str, max_depth: int
    ) -> Iterator[FTPEntry]:
        relative_depth = self._relative_depth(root, current_path)
        logger.info("Listing FTP directory %s (depth=%d)", current_path, relative_depth)
        for name, facts in self._iter_directory_entries(ftp, current_path):
            if name in {".", ".."}:
                continue
            path = f"{current_path.rstrip('/')}/{name}"
            is_dir = facts.get("type") == "dir"
            modified = facts.get("modify")
            modified_at = None
            if modified:
                modified_at = datetime.strptime(
                    modified, "%Y%m%d%H%M%S"
                ).replace(tzinfo=timezone.utc).isoformat()
            size = int(facts["size"]) if "size" in facts and not is_dir else None
            entry = FTPEntry(path=path, is_dir=is_dir, size=size, modified_at=modified_at)
            logger.debug(
                "Discovered FTP entry path=%s is_dir=%s size=%s depth=%d",
                path,
                is_dir,
                size,
                self._relative_depth(root, path),
            )
            entry_depth = self._relative_depth(root, path)
            if entry_depth == 1 and is_dir and not YEAR_DIR_RE.fullmatch(name):
                logger.info(
                    "Skipping non-year top-level branch %s under root %s",
                    path,
                    root,
                )
                continue
            yield entry
            if is_dir:
                next_depth = entry_depth
                if next_depth <= max_depth:
                    logger.debug("Descending into %s", path)
                    yield from self._walk(ftp, root, path, max_depth=max_depth)
                else:
                    logger.info(
                        "Skipping deeper traversal at %s (depth=%d, max_depth=%d)",
                        path,
                        next_depth,
                        max_depth,
                    )

    def _iter_directory_entries(
        self, ftp: FTP, current_path: str
    ) -> Iterator[tuple[str, dict[str, str]]]:
        try:
            logger.debug("Trying MLSD for %s", current_path)
            yield from ftp.mlsd(current_path)
            return
        except all_errors as exc:
            logger.warning("MLSD failed for %s: %s. Falling back to NLST.", current_path, exc)

        yield from self._iter_directory_entries_nlst(ftp, current_path)

    def _iter_directory_entries_nlst(
        self, ftp: FTP, current_path: str
    ) -> Iterator[tuple[str, dict[str, str]]]:
        previous_dir = ftp.pwd()
        ftp.cwd(current_path)
        try:
            names = ftp.nlst()
        finally:
            ftp.cwd(previous_dir)

        for raw_name in names:
            name = raw_name.strip().rstrip("/")
            if not name or name in {".", ".."}:
                continue
            basename = Path(name).name
            entry_path = f"{current_path.rstrip('/')}/{basename}"
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
    def _relative_depth(root: str, path: str) -> int:
        stripped_root = root.strip("/")
        stripped_path = path.strip("/")
        if stripped_path == stripped_root:
            return 0
        root_parts = [segment for segment in stripped_root.split("/") if segment]
        path_parts = [segment for segment in stripped_path.split("/") if segment]
        return max(0, len(path_parts) - len(root_parts))


class LocalPathFTPClient:
    def iter_entries(self, root: str, max_depth: int = MAX_SCAN_DEPTH) -> Iterator[FTPEntry]:
        root_path = Path(root)
        if not root_path.exists():
            raise FileNotFoundError(root)
        logger.info("Scanning local path fixture root %s", root)
        for path in sorted(root_path.rglob("*")):
            relative_parts = path.relative_to(root_path).parts
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
            yield FTPEntry(
                path=path.as_posix(),
                is_dir=path.is_dir(),
                size=None if path.is_dir() else stat.st_size,
                modified_at=datetime.fromtimestamp(
                    stat.st_mtime, timezone.utc
                ).isoformat(),
            )

    def download_bytes(self, path: str) -> bytes:
        return Path(path).read_bytes()

    def download_many_bytes(self, paths: tuple[str, ...]) -> tuple[bytes, ...]:
        return tuple(self.download_bytes(path) for path in paths)

    def download_to_file(self, path: str, target: BinaryIO) -> None:
        target.write(self.download_bytes(path))
