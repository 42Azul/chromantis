from __future__ import annotations

from sqlite3 import Connection

from chromantis.parsing.path_parser import normalize_text


class CollectionStore:
    def __init__(self, connection: Connection, owner_chat_id: int):
        self.connection = connection
        self.owner_chat_id = owner_chat_id

    def list(self) -> list[dict]:
        rows = self.connection.execute(
            """SELECT c.id, c.name, COUNT(e.id) AS count
               FROM memory_collections c LEFT JOIN memory_collection_entries e ON e.collection_id = c.id
               WHERE c.owner_chat_id = ? GROUP BY c.id ORDER BY c.name_key, c.id""",
            (self.owner_chat_id,),
        )
        return [dict(row) for row in rows]

    def get(self, collection_id: int) -> dict:
        collection = self.connection.execute(
            "SELECT id, name FROM memory_collections WHERE id = ? AND owner_chat_id = ?",
            (collection_id, self.owner_chat_id),
        ).fetchone()
        if collection is None:
            raise LookupError("Collection not found.")
        rows = self.connection.execute(
            """
            SELECT e.id, e.kind, e.path,
                   COALESCE(album.title, photo.title || ' / ' || i.filename, e.path) AS title,
                   COALESCE(album.folder_path, photo.folder_path) AS folder_path,
                   (album.id IS NOT NULL OR photo.id IS NOT NULL) AS available
            FROM memory_collection_entries e
            LEFT JOIN album_metadata album
                ON e.kind = 'folder' AND album.folder_path = e.path AND album.ftp_root_path = e.source_root
            LEFT JOIN images i ON e.kind = 'image' AND i.file_path = e.path
            LEFT JOIN album_metadata photo ON photo.id = i.folder_id AND photo.ftp_root_path = e.source_root
            WHERE e.collection_id = ? ORDER BY e.id
            """,
            (collection_id,),
        )
        return {**dict(collection), "entries": [{**dict(row), "available": bool(row["available"])} for row in rows]}

    def create(self, name: str) -> int:
        name = name.strip()
        key = normalize_text(name)
        if not key or len(name) > 80 or not name.isprintable():
            raise ValueError("Enter a collection name of up to 80 characters.")
        count = self.connection.execute(
            "SELECT COUNT(*) FROM memory_collections WHERE owner_chat_id = ?", (self.owner_chat_id,),
        ).fetchone()[0]
        if count >= 100:
            raise ValueError("You can keep up to 100 collections.")
        result = self.connection.execute(
            """INSERT INTO memory_collections (owner_chat_id, name, name_key) VALUES (?, ?, ?)
               ON CONFLICT (owner_chat_id, name_key) DO NOTHING""",
            (self.owner_chat_id, name, key),
        )
        if not result.rowcount:
            raise ValueError("A collection already has that name.")
        return int(result.lastrowid)

    def add(self, collection_id: int, kind: str, path: str) -> dict:
        collection = self.get(collection_id)
        if kind == "folder":
            statement = "SELECT ftp_root_path FROM folders WHERE folder_path = ?"
        elif kind == "image":
            statement = """SELECT f.ftp_root_path FROM images i JOIN folders f ON f.id = i.folder_id
                           WHERE i.file_path = ?"""
        else:
            raise ValueError("kind must be folder or image.")
        index = self.connection.execute(statement, (path,)).fetchone()
        if index is None:
            raise ValueError("Choose a photo or album from the index.")
        root = index["ftp_root_path"]
        existing = self.connection.execute(
            """SELECT 1 FROM memory_collection_entries
               WHERE collection_id = ? AND kind = ? AND path = ? AND source_root = ?""",
            (collection_id, kind, path, root),
        ).fetchone()
        if existing is not None:
            return collection
        if len(collection["entries"]) >= 250:
            raise ValueError("A collection can hold up to 250 entries.")
        self.connection.execute(
            "INSERT INTO memory_collection_entries (collection_id, kind, path, source_root) VALUES (?, ?, ?, ?)",
            (collection_id, kind, path, root),
        )
        return self.get(collection_id)

    def remove(self, collection_id: int, entry_id: int) -> None:
        result = self.connection.execute(
            """DELETE FROM memory_collection_entries WHERE id = ? AND collection_id = ?
               AND collection_id IN (SELECT id FROM memory_collections WHERE owner_chat_id = ?)""",
            (entry_id, collection_id, self.owner_chat_id),
        )
        if not result.rowcount:
            raise LookupError("Collection entry not found.")

    def delete(self, collection_id: int) -> None:
        result = self.connection.execute(
            "DELETE FROM memory_collections WHERE id = ? AND owner_chat_id = ?",
            (collection_id, self.owner_chat_id),
        )
        if not result.rowcount:
            raise LookupError("Collection not found.")
