from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from chromantis.app import ApplicationService
from chromantis.app.mcp_readonly import AlbumMcpPrincipal, McpAccessError, ReadOnlyAlbumMcp
from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser
from chromantis.source import ArchiveScanner, LocalArchiveSource


FIXTURE = Path(__file__).parent / "fixtures" / "ftp_tree" / "server_root" / "photos" / "archive"


class ReadOnlyAlbumMcpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.archive = root / "archive"
        shutil.copytree(FIXTURE, self.archive)
        self.repository = Repository(str(root / "chromantis.db"))
        self.repository.init_schema()
        ArchiveScanner(LocalArchiveSource(str(self.archive)), self.repository, PathParser()).scan()
        self.app = ApplicationService(self.repository, static_owner_chat_ids=(1,))
        with self.app.owner_album_shares(1, write=True) as shares:
            self.share, secret = shares.create("2021/2021-08-15_city_trip", 7)
        self.tools = ReadOnlyAlbumMcp(self.app, AlbumMcpPrincipal(secret))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_tools_are_read_only_album_scoped_and_work_offline(self) -> None:
        offline = self.archive.with_name("archive-offline")
        self.archive.rename(offline)
        definitions = self.tools.list_tools()
        self.assertEqual(
            [tool["name"] for tool in definitions],
            ["chromantis_list_album", "chromantis_search_album"],
        )
        self.assertTrue(all(tool["annotations"]["readOnlyHint"] for tool in definitions))
        self.assertTrue(all(not tool["annotations"]["destructiveHint"] for tool in definitions))

        listed = self.tools.call_tool("chromantis_list_album", {"limit": 10})["structuredContent"]
        self.assertEqual(listed["album"]["title"], "2021 08 15 city trip")
        self.assertEqual(
            [photo["filename"] for photo in listed["photos"]], ["IMG_001.jpg", "IMG_002.jpg"]
        )
        self.assertNotIn("path", listed["album"])
        self.assertNotIn("path", listed["photos"][0])

        matched = self.tools.call_tool(
            "chromantis_search_album", {"query": "IMG 001", "limit": 10}
        )["structuredContent"]
        self.assertEqual(matched["photos"], [{"filename": "IMG_001.jpg"}])
        outside = self.tools.call_tool(
            "chromantis_search_album", {"query": "beach", "limit": 10}
        )["structuredContent"]
        self.assertEqual(outside["photos"], [])
        wildcard = self.tools.call_tool(
            "chromantis_search_album", {"query": "%", "limit": 10}
        )["structuredContent"]
        self.assertEqual(wildcard["photos"], [])

        with self.assertRaisesRegex(ValueError, "Unknown or unavailable"):
            self.tools.call_tool("chromantis_edit_album", {"title": "Changed"})

    def test_revocation_is_checked_on_every_tool_call(self) -> None:
        self.assertTrue(self.tools.call_tool("chromantis_list_album")["structuredContent"]["photos"])
        with self.app.owner_album_shares(1, write=True) as shares:
            shares.revoke(self.share["id"])
        with self.assertRaisesRegex(McpAccessError, "revoked"):
            self.tools.call_tool("chromantis_list_album")

    def test_arguments_are_bounded_and_cannot_select_another_album(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            self.tools.call_tool("chromantis_list_album", {"path": "2019/2019-07-10_beach_day"})
        for value in (True, 0, 101):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "limit"):
                self.tools.call_tool("chromantis_list_album", {"limit": value})


if __name__ == "__main__":
    unittest.main()
