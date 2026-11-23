"""Check an exact archive-relative album path in the existing index and optionally in the source."""

import argparse
from contextlib import closing
from ftplib import all_errors
from pathlib import Path, PurePosixPath
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chromantis.config import AppConfig
from chromantis.parsing.path_parser import PathParseError, PathParser
from chromantis.source import ArchiveSource, build_archive_source
from chromantis.source.scanner import IMAGE_EXTENSIONS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("album", help="Exact archive-relative path, such as 2003(2)/album")
    parser.add_argument("--db", type=Path, help="Override the configured SQLite index path")
    parser.add_argument("--check-source", action="store_true", help="List direct entries in the configured album")
    args = parser.parse_args()
    album = args.album
    path = PurePosixPath(album)
    try:
        if path.is_absolute() or ".." in path.parts or path.as_posix() != album:
            raise PathParseError("Expected an exact archive-relative album path.")
        record = PathParser().parse_image_path("", f"{album}/fixture.jpg", None, None)
    except PathParseError:
        parser.error("Expected an exact archive-relative year/album path.")

    config = AppConfig.from_env() if args.db is None or args.check_source else None
    database = args.db if args.db is not None else Path(config.sqlite_path)
    try:
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
            row = connection.execute(
                """SELECT COUNT(images.id) FROM folders
                   LEFT JOIN images ON images.folder_id = folders.id
                   WHERE folders.folder_path = ?
                   GROUP BY folders.id""",
                (record.folder_path,),
            ).fetchone()
    except sqlite3.Error:
        raise SystemExit("Could not read the existing Chromantis index.") from None

    if row and row[0]:
        print(f"Indexed photos: {row[0]}. Check the year pages or search by album title.")
    elif row:
        print("Album row found with no indexed photos.")
    else:
        print("Album path absent from the index. The index alone cannot explain why.")

    if args.check_source:
        try:
            report_source(build_archive_source(config), record.folder_path)
        except (ValueError,) + all_errors:
            raise SystemExit("Could not list the album in the source. It may be absent or inaccessible.") from None


def report_source(source: ArchiveSource, album_path: str) -> None:
    photos = directories = 0
    for entry in source.iter_album_entries(album_path):
        directories += entry.is_dir
        photos += not entry.is_dir and PurePosixPath(entry.path).suffix.lower() in IMAGE_EXTENSIONS
    print(f"Source: {photos} supported direct photos; {directories} subfolders.")
    if not photos and directories:
        print("Photos inside subfolders are outside the indexed album layout.")


if __name__ == "__main__":
    main()
