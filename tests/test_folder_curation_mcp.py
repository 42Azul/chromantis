from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from chromantis.app import ApplicationService
from chromantis.app.folder_curation import FolderCuration, folder_date
from chromantis.app.mcp_curation import FolderCurationTools, read_proposal, read_scope
from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser
from chromantis.source import ArchiveScanner, LocalArchiveSource


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "folder_curation_mcp.py"
ALBUM = "2021(2)/15.08.2021_Cumple de Anita en Madrid"
SECOND = "2021/2021-07-16_Paseo"
OUTSIDE = "2020/2020-05-12_Private"


class FolderCurationTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        archive = self.root / "archive"
        for album in (ALBUM, SECOND, OUTSIDE):
            folder = archive / album
            folder.mkdir(parents=True)
            (folder / "private-image-name.jpg").touch()
        self.database = self.root / "index.db"
        self.repository = Repository(str(self.database))
        self.repository.init_schema()
        ArchiveScanner(LocalArchiveSource(str(archive)), self.repository, PathParser()).scan()
        archive.rename(self.root / "disconnected")
        self.app = ApplicationService(self.repository, static_owner_chat_ids=(1,))
        self.ana = self.app.create_person("Ana")
        self.app.add_person_alias(self.ana.id, "Anita")
        self.other = self.app.create_person("Not mentioned")
        self.curation = FolderCuration(self.database)
        self.output = self.root / "proposals"
        self.tools = FolderCurationTools(self.curation, [ALBUM, SECOND], self.output)

    def _inspect(self, album: str = "album-1") -> dict:
        return self.tools.call("inspect_curation_album", {"album": album})

    def _queue(self, changes: dict, album: str = "album-1") -> Path:
        result = self.tools.call("propose_curation_album", {
            "album": album, "version": self._inspect(album)["version"], "changes": changes,
        })
        self.assertEqual(result["status"], "pending_operator_review")
        return self.output / result["proposal_file"]

    def _good_changes(self) -> dict:
        return {
            "title": {"value": "Cumpleaños de Ana", "evidence": "Cumple de Anita"},
            "place": {"value": "Madrid", "evidence": "Madrid"},
            "use_folder_date": True,
            "tags": [{"value": "cumpleaños", "evidence": "Cumple"}, {"value": "Madrid", "evidence": "Madrid"}],
            "person_ids": [self.ana.id],
        }

    def test_scoped_metadata_only_and_operator_approved_write(self) -> None:
        self.assertEqual(len(self.tools.call("list_curation_albums", {})["albums"]), 2)
        before = self._inspect()
        self.assertEqual(before["folder_date"], {"value": "2021-08-15", "evidence": "15.08.2021"})
        self.assertEqual(before["people_candidates"], [
            {"id": self.ana.id, "name": "Ana", "evidence": "Anita", "already_linked": False}
        ])
        for private in (OUTSIDE, "private-image-name.jpg", str(self.root), "Not mentioned"):
            self.assertNotIn(private, json.dumps(before))
        with self.assertRaisesRegex(ValueError, "handle"):
            self.tools.call("inspect_curation_album", {"album": OUTSIDE})
        with self.assertRaisesRegex(ValueError, "Unknown tool"):
            self.tools.call("apply_curation_album", {})

        filename = self._queue(self._good_changes())
        self.assertEqual(filename.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self._inspect(), before)
        with self.assertRaisesRegex(ValueError, "already queued"):
            self._queue(self._good_changes())

        record = read_proposal(filename)
        parsed = self.app.get_album_review(1, path=ALBUM)
        self.app.edit_album_context(1, ALBUM, parsed["id"], parsed["context_revision"], {"note": "My note"})
        with self.assertRaisesRegex(ValueError, "changed"):
            self.curation.apply([record])
        self.tools = FolderCurationTools(self.curation, [ALBUM], self.output)
        record = read_proposal(self._queue(self._good_changes()))
        self.curation.apply([record])
        after = self.app.get_album_review(1, path=ALBUM)
        self.assertEqual(after["title"], "Cumpleaños de Ana")
        self.assertEqual(after["event_date"], "2021-08-15")
        self.assertIsNone(after["indexed_date"])
        self.assertEqual(after["place"], "Madrid")
        self.assertEqual(after["note"], "My note")
        self.assertEqual(after["suggestions"]["cumpleanos"]["state"], "accepted")
        self.assertEqual(after["manual_tags"], ["madrid"])
        self.assertEqual(after["person_ids"], [self.ana.id])
        audit = self.repository.list_audit_events(limit=1)[0]
        self.assertEqual(audit.action, "apply_folder_curation")
        self.assertEqual(json.loads(audit.details_json)["context"]["event_date"]["evidence"], "15.08.2021")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.curation.apply([record])

    def test_batch_revalidation_rolls_back_every_album_and_audit(self) -> None:
        first = read_proposal(self._queue(self._good_changes()))
        second = read_proposal(self._queue(
            {"title": {"value": "Paseo de verano", "evidence": "Paseo"}}, "album-2"
        ))
        invalid = copy.deepcopy(second)
        invalid["proposal"]["context"]["title"]["value"] = "Not the validated edit"
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.curation.apply([first, invalid])
        self.assertFalse(self._inspect()["title_is_curated"])
        self.assertNotEqual(self.repository.list_audit_events(limit=1)[0].action, "apply_folder_curation")
        self.curation.apply([first, second])
        self.assertEqual(self._inspect("album-2")["title"], "Paseo de verano")

    def test_guards_evidence_and_preserves_manual_decisions(self) -> None:
        for changes, message in (
            ({"use_folder_date": "yes"}, "boolean"),
            ({"event_date": "2021-08-15"}, "Unsupported"),
            ({"place": {"value": "Barcelona", "evidence": "Madrid"}}, "explicitly"),
            ({"person_ids": [self.other.id]}, "unambiguous"),
            ({"title": {"value": "Cumple familiar", "evidence": "Ana"}}, "quote"),
            ({"title": {"value": "Cumple familiar", "evidence": "Anit"}}, "whole words"),
            ({"tags": [{"value": "cumpleaños", "evidence": "Madrid"}]}, "tag suggestion"),
        ):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, message):
                self._queue(changes)
        item = self.app.get_album_review(1, path=ALBUM)
        self.app.save_album_review(
            1, ALBUM, item["id"], item["revision"], add_people=set(), remove_people=set(), new_person=None,
            decisions={"cumpleanos": None}, manual_add=set(), manual_remove=set(),
        )
        self.app.edit_album_context(1, ALBUM, item["id"], item["context_revision"], {"title": "Nombre familiar"})
        with self.assertRaisesRegex(ValueError, "curated title"):
            self._queue(self._good_changes())
        with self.assertRaisesRegex(ValueError, "reviewed tag"):
            self._queue({"tags": [{"value": "cumpleaños", "evidence": "Cumple"}]})
        self.assertEqual(list(self.output.iterdir()), [])

    def test_name_collisions_and_replaced_album(self) -> None:
        before = self._inspect()
        # The directory permits distinct punctuation, but tokenized evidence is ambiguous.
        self.app.rename_person(self.other.id, "Anita!")
        self.assertEqual(self._inspect()["people_candidates"], [])
        with self.assertRaisesRegex(ValueError, "changed"):
            self.tools.call("propose_curation_album", {
                "album": "album-1", "version": before["version"], "changes": self._good_changes(),
            })
        with self.repository.write_transaction() as connection:
            connection.execute("UPDATE folders SET ftp_root_path = ? WHERE folder_path = ?", ("/new", ALBUM))
        with self.assertRaisesRegex(ValueError, "replaced"):
            self._inspect()

    def test_dates_require_one_valid_unambiguous_date(self) -> None:
        for name in (
            "03.04.2021_Paseo", "2020-08-15_Paseo", "2021-02-29_Paseo",
            "2021-07-15 a 2021-07-18", "Verano 2021", "ID2021-08-15_Paseo",
        ):
            with self.subTest(name=name):
                self.assertIsNone(folder_date(name, 2021))
        self.assertEqual(folder_date("Paseo 2024_02_29", 2024)["value"], "2024-02-29")
        self.assertEqual(folder_date("Paseo 2021-8-5", 2021)["value"], "2021-08-05")

    def test_cli_preview_does_not_apply_and_noninteractive_apply_is_refused(self) -> None:
        filename = self._queue(self._good_changes())
        command = [sys.executable, str(SCRIPT), "--database", str(self.database), "review", str(filename)]
        preview = subprocess.run(command, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(preview.stdout)[0]["context"]["title"]["value"], "Cumpleaños de Ana")
        refused = subprocess.run([*command, "--apply"], input="APPLY\n", capture_output=True, text=True)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("interactive terminal", refused.stderr)
        self.assertFalse(self._inspect()["title_is_curated"])

    def test_operator_finds_albums_missing_a_place_and_mcp_adds_a_searchable_place(self) -> None:
        command = [
            sys.executable, str(SCRIPT), "--database", str(self.database),
            "list-albums", "--year", "2021", "--missing-place",
        ]
        before = subprocess.run(command, capture_output=True, text=True, check=True)
        self.assertEqual({album["path"] for album in json.loads(before.stdout)}, {ALBUM, SECOND})
        self.assertEqual(self.app.search_folders("", place="Madrid"), [])
        proposal = self._queue({"place": {"value": "Madrid", "evidence": "Madrid"}})
        self.curation.apply([read_proposal(proposal)])
        self.assertEqual([album.path for album in self.app.search_folders("", place="Madrid")], [ALBUM])
        current = self._inspect()
        self.assertEqual(current["place"], "Madrid")
        self.assertEqual(current["manual_tags"], [])
        with self.assertRaisesRegex(ValueError, "curated place"):
            self.curation.prepare(ALBUM, current["version"], {"place": {"value": "Anita", "evidence": "Anita"}})
        after = subprocess.run(command, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(after.stdout), [{"path": SECOND, "year": 2021, "place": None}])
        with self.assertRaisesRegex(ValueError, "Unknown tool"):
            self.tools.call("list_albums", {"missing_place": True})

    def test_scope_file_must_be_private_and_contain_only_exact_paths(self) -> None:
        scope = self.root / "scope.json"
        scope.write_text(json.dumps([ALBUM]), encoding="utf-8")
        scope.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "private regular scope file"):
            read_scope(scope)
        scope.chmod(0o600)
        self.assertEqual(read_scope(scope), [ALBUM])
        scope.write_text(json.dumps({"albums": [ALBUM]}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "JSON array"):
            read_scope(scope)

    @unittest.skipUnless(os.name == "posix", "requires a terminal device")
    def test_operator_can_approve_from_a_terminal(self) -> None:
        import pty

        filename = self._queue(self._good_changes())
        master, terminal = pty.openpty()
        try:
            process = subprocess.Popen([
                sys.executable, str(SCRIPT), "--database", str(self.database),
                "review", "--apply", str(filename),
            ], stdin=terminal, stdout=terminal, stderr=terminal)
            try:
                os.write(master, b"APPLY\n")
                self.assertEqual(process.wait(timeout=10), 0)
            finally:
                if process.returncode is None:
                    process.kill()
                    process.wait()
        finally:
            os.close(terminal)
            os.close(master)
        self.assertEqual(self._inspect()["title"], "Cumpleaños de Ana")

    @unittest.skipUnless(importlib.util.find_spec("mcp"), "install optional .[mcp] to test stdio")
    def test_official_mcp_client_negotiates_and_queues_over_stdio(self) -> None:
        from mcp import Client, StdioServerParameters

        scope = self.root / "scope.json"
        scope.write_text(json.dumps([ALBUM]), encoding="utf-8")
        scope.chmod(0o600)

        async def exercise():
            parameters = StdioServerParameters(
                command=sys.executable,
                args=[
                    str(SCRIPT), "--database", str(self.database), "serve",
                    "--scope-file", str(scope), "--proposals", str(self.output),
                ],
            )
            async with Client(parameters, mode="legacy") as client:
                self.assertEqual(
                    [tool.name for tool in (await client.list_tools()).tools],
                    ["list_curation_albums", "inspect_curation_album", "propose_curation_album"],
                )
                scoped = await client.call_tool("list_curation_albums", {})
                self.assertEqual(len(scoped.structured_content["albums"]), 1)
                inspect = await client.call_tool("inspect_curation_album", {"album": "album-1"})
                self.assertEqual(inspect.structured_content["folder_date"]["value"], "2021-08-15")
                outside = await client.call_tool("inspect_curation_album", {"album": "album-2"})
                self.assertTrue(outside.is_error)
                proposal = await client.call_tool("propose_curation_album", {
                    "album": "album-1",
                    "version": inspect.structured_content["version"],
                    "changes": self._good_changes(),
                })
                self.assertFalse(proposal.is_error, proposal.content)
                self.assertEqual(proposal.structured_content["status"], "pending_operator_review")
                self.assertTrue((self.output / proposal.structured_content["proposal_file"]).is_file())
                self.assertFalse(self._inspect()["title_is_curated"])

        asyncio.run(asyncio.wait_for(exercise(), timeout=15))


if __name__ == "__main__":
    unittest.main()
