"""Check an exact archive-relative album path in the existing index."""

import argparse
from contextlib import closing
from pathlib import Path, PurePosixPath
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chromantis.config import AppConfig
from chromantis.parsing.path_parser import PathParseError, PathParser


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("album", help="Exact archive-relative path, such as 2003(2)/album")
    parser.add_argument("--db", type=Path, help="Override the configured SQLite index path")
    args = parser.parse_args()
    album = args.album
    path = PurePosixPath(album)
    try:
        if path.is_absolute() or ".." in path.parts or path.as_posix() != album:
            raise PathParseError("Expected an exact archive-relative album path.")
        record = PathParser().parse_image_path("", f"{album}/fixture.jpg", None, None)
    except PathParseError:
        parser.error("Expected an exact archive-relative year/album path.")

    database = args.db or Path(AppConfig.from_env().sqlite_path)
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


if __name__ == "__main__":
    main()
