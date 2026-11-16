from __future__ import annotations

from sqlite3 import Connection, Row


def find_photos(connection: Connection, paths: list[str]) -> dict[str, Row]:
    placeholders = ", ".join("?" for _ in paths)
    rows = connection.execute(
        f"SELECT id, file_path, photo_identity FROM images WHERE file_path IN ({placeholders})",
        paths,
    )
    return {row["file_path"]: row for row in rows}


def photo_annotations(connection: Connection, photo: Row) -> dict:
    people = connection.execute(
        "SELECT person_id, origin FROM photo_people WHERE image_id = ? ORDER BY person_id",
        (photo["id"],),
    )
    tags = connection.execute(
        "SELECT tag, origin FROM photo_manual_tags WHERE image_id = ? ORDER BY tag",
        (photo["id"],),
    )
    return {
        "path": photo["file_path"],
        "identity": photo["photo_identity"],
        "people": [dict(row) for row in people],
        "manual_tags": [dict(row) for row in tags],
    }


def update_photo_annotations(
    connection: Connection, image_id: int, *,
    add_people: set[int], remove_people: set[int], manual_add: set[str], manual_remove: set[str],
) -> None:
    connection.executemany(
        "DELETE FROM photo_people WHERE image_id = ? AND person_id = ?",
        ((image_id, person_id) for person_id in remove_people),
    )
    connection.executemany(
        "INSERT INTO photo_people (image_id, person_id, origin) VALUES (?, ?, 'manual')",
        ((image_id, person_id) for person_id in add_people),
    )
    connection.executemany(
        "DELETE FROM photo_manual_tags WHERE image_id = ? AND tag = ?",
        ((image_id, tag) for tag in manual_remove),
    )
    connection.executemany(
        "INSERT INTO photo_manual_tags (image_id, tag, origin) VALUES (?, ?, 'manual')",
        ((image_id, tag) for tag in manual_add),
    )
