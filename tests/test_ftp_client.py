from __future__ import annotations

from contextlib import nullcontext
import tempfile
import unittest
from ftplib import error_perm
from pathlib import Path
from unittest.mock import patch

from chromantis.api.server import handle_api_get
from chromantis.app import ApplicationService
from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser
from chromantis.source import ArchiveScanner
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


class SplitYearFTP:
    def __init__(self, *, mlsd_available: bool) -> None:
        self.mlsd_available = mlsd_available
        self.current = "/"
        self.root = "/synthetic"
        self.directories = {self.root: ["2003(1)", "2003(2)"]}
        for branch, count in (("2003(1)", 30), ("2003(2)", 1)):
            parent = f"{self.root}/{branch}"
            self.directories[parent] = [f"album_{number:02d}" for number in range(count)]
            for album in self.directories[parent]:
                self.directories[f"{parent}/{album}"] = ["photo.jpg"]

    def pwd(self):
        return self.current

    def cwd(self, path):
        if path != "/" and path not in self.directories:
            raise error_perm("550 Not a directory")
        self.current = path

    def mlsd(self, path):
        if not self.mlsd_available:
            raise error_perm("500 MLSD unsupported")
        for name in self.directories[path]:
            is_dir = f"{path}/{name}" in self.directories
            yield name, {"type": "dir"} if is_dir else {"type": "file", "size": "123"}

    def nlst(self):
        return [f"{self.current}/{name}" for name in self.directories[self.current]]

    def size(self, _path):
        return 123

    def sendcmd(self, _command):
        return "213 20240101000000"

    def quit(self):
        pass


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

    def test_split_year_albums_keep_distinct_paths_across_pages(self) -> None:
        for mlsd_available in (True, False):
            with self.subTest(mlsd_available=mlsd_available), tempfile.TemporaryDirectory() as tmp:
                ftp = SplitYearFTP(mlsd_available=mlsd_available)
                source = FtpArchiveSource("example", "fixture", "fixture", ftp.root)
                repo = Repository(str(Path(tmp) / "index.sqlite"))
                repo.init_schema()
                expected_logs = nullcontext() if mlsd_available else self.assertLogs("chromantis.source.adapters", "WARNING")
                with patch.object(source, "_connect", return_value=ftp), expected_logs:
                    ArchiveScanner(source, repo, PathParser()).scan()
                app = ApplicationService(repo)

                status, years = handle_api_get("/api/v1/years", app)
                self.assertEqual(status, 200)
                self.assertEqual(
                    [(item["year"], item["folders"], item["images"]) for item in years["items"]],
                    [(2003, 31, 31)],
                )
                status, first = handle_api_get("/api/v1/folders?q=2003&limit=31", app)
                self.assertEqual(status, 200)
                status, second = handle_api_get("/api/v1/folders?q=2003&limit=31&offset=30", app)
                self.assertEqual(status, 200)
                self.assertEqual(len(first["items"]), 31)
                self.assertEqual(len(second["items"]), 1)
                self.assertEqual(first["items"][0]["title"], second["items"][0]["title"])
                self.assertEqual(first["items"][0]["path"], "2003(1)/album_00")
                self.assertEqual(second["items"][0]["path"], "2003(2)/album_00")

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
