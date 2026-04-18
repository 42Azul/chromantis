from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from chromantis.source.adapters import FtpArchiveSource, LocalArchiveSource


class FakeFTP:
    def __init__(self) -> None:
        self.directories = {
            "/CASA/FOTOS": [("2021", {"type": "dir"}), ("MISC", {"type": "dir"})],
            "/CASA/FOTOS/2021": [("20210101 - Reyes", {"type": "dir"})],
            "/CASA/FOTOS/2021/20210101 - Reyes": [
                ("IMG_0001.jpg", {"type": "file", "size": "123"})
            ],
            "/CASA/FOTOS/MISC": [("IMG_9999.jpg", {"type": "file", "size": "999"})],
        }

    def mlsd(self, path: str):
        yield from self.directories.get(path, [])


class StdlibFTPClientTests(unittest.TestCase):
    def test_walk_descends_into_folder_level_to_reach_images(self) -> None:
        client = FtpArchiveSource(
            host="example",
            user="user",
            password="pass",
            source_root="/CASA/FOTOS",
        )
        ftp = FakeFTP()

        entries = list(client._walk(ftp, "", max_depth=2))

        self.assertEqual(
            [entry.path for entry in entries],
            [
                "2021",
                "2021/20210101 - Reyes",
                "2021/20210101 - Reyes/IMG_0001.jpg",
            ],
        )

    def test_ftp_absolute_path_rejects_parent_traversal(self) -> None:
        client = FtpArchiveSource(
            host="example",
            user="user",
            password="pass",
            source_root="/CASA/FOTOS",
        )

        with self.assertRaises(ValueError):
            client._absolute_path("../secret.txt")

    def test_local_archive_read_rejects_parent_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = LocalArchiveSource(temp_dir)

            with self.assertRaises(ValueError):
                source.read_bytes("../secret.txt")

    def test_local_archive_scan_skips_symlink_outside_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "archive"
            target_dir = Path(temp_dir) / "external"
            year_dir = root / "2024"
            folder_dir = year_dir / "2024-01-01_new_year"
            folder_dir.mkdir(parents=True)
            target_dir.mkdir(parents=True)
            external_file = target_dir / "IMG_0001.jpg"
            external_file.write_bytes(b"external")
            symlink_path = folder_dir / "IMG_9999.jpg"
            symlink_path.symlink_to(external_file)

            source = LocalArchiveSource(str(root))

            entries = list(source.iter_entries())

            self.assertEqual([entry.path for entry in entries], ["2024", "2024/2024-01-01_new_year"])
