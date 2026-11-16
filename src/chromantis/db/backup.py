from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from chromantis.db.repository import Repository


REQUIRED_TABLES = {"folders", "images", "album_context", "memory_collections"}


@dataclass(frozen=True)
class DatabaseBackup:
    path: Path
    size: int
    sha256: str


def _read_only_connection(path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(str(path.resolve()), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _validate(connection: sqlite3.Connection) -> None:
    result = connection.execute("PRAGMA quick_check").fetchone()[0]
    if result != "ok":
        raise ValueError(f"SQLite integrity check failed: {result}")
    tables = {
        row["name"] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    missing = sorted(REQUIRED_TABLES - tables)
    if missing:
        raise ValueError("Not a compatible Chromantis database; missing: " + ", ".join(missing))
    foreign_key_error = connection.execute("PRAGMA foreign_key_check").fetchone()
    if foreign_key_error is not None:
        raise ValueError("SQLite foreign key check failed.")


def _summary(path: Path) -> DatabaseBackup:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return DatabaseBackup(path=path, size=path.stat().st_size, sha256=digest.hexdigest())


def verify_backup(path: str | Path) -> DatabaseBackup:
    backup = Path(path)
    if not backup.is_file():
        raise FileNotFoundError(f"Database backup not found: {backup}")
    with _read_only_connection(backup) as connection:
        _validate(connection)
    return _summary(backup)


def _copy_database(source: Path, destination: Path, *, migrate: bool) -> DatabaseBackup:
    if not source.is_file():
        raise FileNotFoundError(f"Database not found: {source}")
    if source.resolve() == destination.resolve():
        raise ValueError("Source and destination must be different files.")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Refusing to overwrite existing file: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        with _read_only_connection(source) as source_connection:
            _validate(source_connection)
            with sqlite3.connect(temporary) as target_connection:
                source_connection.backup(target_connection)
        if migrate:
            Repository(str(temporary)).init_schema()
        verify_backup(temporary)
        os.replace(temporary, destination)
        return _summary(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def create_backup(database: str | Path, destination: str | Path) -> DatabaseBackup:
    return _copy_database(Path(database), Path(destination), migrate=False)


def restore_backup(backup: str | Path, database: str | Path) -> DatabaseBackup:
    return _copy_database(Path(backup), Path(database), migrate=True)
