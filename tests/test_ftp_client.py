from __future__ import annotations

import unittest

from chromantis.ftp.client import StdlibFTPClient


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
        client = StdlibFTPClient(host="example", user="user", password="pass")
        ftp = FakeFTP()

        entries = list(client._walk(ftp, "/CASA/FOTOS", "/CASA/FOTOS", max_depth=2))

        self.assertEqual(
            [entry.path for entry in entries],
            [
                "/CASA/FOTOS/2021",
                "/CASA/FOTOS/2021/20210101 - Reyes",
                "/CASA/FOTOS/2021/20210101 - Reyes/IMG_0001.jpg",
            ],
        )
