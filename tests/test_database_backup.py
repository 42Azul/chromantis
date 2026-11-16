from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from chromantis.app import ApplicationService
from chromantis.db.backup import create_backup, restore_backup, verify_backup
from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser
from chromantis.source import ArchiveScanner, LocalArchiveSource


ALBUM = "2024/2024-04-21_family_lunch"


class DatabaseBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        archive = self.root / "archive"
        photo = archive / ALBUM / "SYNTHETIC.jpg"
        photo.parent.mkdir(parents=True)
        photo.write_bytes(b"archive must stay unchanged")
        self.original = photo.read_bytes()
        self.database = self.root / "chromantis.db"
        self.repository = Repository(str(self.database))
        self.repository.init_schema()
        ArchiveScanner(LocalArchiveSource(str(archive)), self.repository, PathParser()).scan()
        self.app = ApplicationService(self.repository, static_owner_chat_ids=(10,))
        album = self.app.get_album_review(10, path=ALBUM)
        self.app.edit_album_context(
            10, ALBUM, album["id"], album["context_revision"],
            {"title": "Comida familiar", "aliases": ["Domingo juntos"], "note": "Terraza"},
        )
        with self.app.owner_collections(10, write=True) as collections:
            collection_id = collections.create("Favoritos")
            collections.add(collection_id, "folder", ALBUM)
        self.photo = photo

    def test_backup_restore_preserves_collections_and_corrections(self) -> None:
        backup = self.root / "backups" / "chromantis.sqlite"
        created = create_backup(self.database, backup)
        self.assertEqual(created, verify_backup(backup))
        restored_path = self.root / "fresh" / "chromantis.db"

        restored = restore_backup(backup, restored_path)

        self.assertEqual(restored.path, restored_path)
        restored_repository = Repository(str(restored_path))
        restored_app = ApplicationService(restored_repository, static_owner_chat_ids=(10,))
        album = restored_app.get_album_review(10, path=ALBUM)
        self.assertEqual(album["title"], "Comida familiar")
        self.assertEqual(album["aliases"], ["Domingo juntos"])
        self.assertEqual(album["note"], "Terraza")
        with restored_app.owner_collections(10) as collections:
            collection, = collections.list()
            self.assertEqual(collection["name"], "Favoritos")
            self.assertEqual(collections.get(collection["id"])["entries"][0]["path"], ALBUM)
        self.assertEqual(self.photo.read_bytes(), self.original)

    def test_commands_refuse_overwrite_and_reject_unrelated_sqlite(self) -> None:
        backup = self.root / "backup.sqlite"
        create_backup(self.database, backup)
        with self.assertRaises(FileExistsError):
            create_backup(self.database, backup)
        with self.assertRaises(FileExistsError):
            restore_backup(backup, self.database)
        link = self.root / "broken-link.sqlite"
        link.symlink_to(self.root / "missing.sqlite")
        with self.assertRaises(FileExistsError):
            restore_backup(backup, link)
        unrelated = self.root / "unrelated.sqlite"
        Repository(str(unrelated)).connect().close()
        with self.assertRaisesRegex(ValueError, "Not a compatible Chromantis database"):
            verify_backup(unrelated)


if __name__ == "__main__":
    unittest.main()
