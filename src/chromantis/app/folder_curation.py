"""Evidence and atomic, operator-approved edits for folder metadata."""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import closing, contextmanager
from datetime import date
from pathlib import Path
from sqlite3 import Connection, Row, connect

from chromantis.app.album_review import (
    apply_tag_decisions,
    parse_tag,
    review_folder,
    review_item,
    save_context,
    save_review_progress,
)
from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import normalize_text


WORDS = re.compile(r"[^\W_]+", re.UNICODE)
NAME_DATES = re.compile(r"(?<![^\W_])(\d{4}|\d{1,2})([-_. ])(\d{1,2})\2(\d{4}|\d{1,2})(?![^\W_])")


def folder_date(name: str, indexed_year: int) -> dict[str, str] | None:
    """Accept only one unambiguous full date that agrees with the year branch."""
    matches = list(NAME_DATES.finditer(name))
    if len(matches) != 1:
        return None
    match = matches[0]
    first, _, middle, last = match.groups()
    if len(first) == 4 and len(last) <= 2:
        year, month, day = int(first), int(middle), int(last)
    elif len(first) == 2 and len(last) == 4 and int(first) > 12:
        year, month, day = int(last), int(middle), int(first)
    else:
        return None
    if year != indexed_year:
        return None
    try:
        return {"value": date(year, month, day).isoformat(), "evidence": match[0]}
    except ValueError:
        return None


def person_candidates(connection: Connection, name: str) -> dict[int, dict]:
    raw_words = list(WORDS.finditer(name))
    words = [normalize_text(word[0]) for word in raw_words]
    matches: dict[tuple[int, int], dict[int, str]] = {}
    for row in connection.execute(
        """SELECT id, display_name, display_name AS term FROM people
           UNION ALL SELECT p.id, p.display_name, a.alias FROM person_aliases a
                     JOIN people p ON p.id = a.person_id
           ORDER BY id, term"""
    ):
        term = WORDS.findall(normalize_text(row["term"]))
        if not term or not any(ch.isalpha() for ch in "".join(term)):
            continue
        for start in range(len(words) - len(term) + 1):
            end = start + len(term)
            if words[start:end] == term:
                matches.setdefault((start, end), {})[row["id"]] = row["display_name"]

    candidates = {}
    for (start, end), people in matches.items():
        # Suppress a short match inside a longer one, or both sides of a partial overlap.
        if len(people) != 1 or any(
            other_start < end and start < other_end and not (start <= other_start and other_end <= end)
            for other_start, other_end in matches
        ):
            continue
        person_id, display_name = next(iter(people.items()))
        evidence = name[raw_words[start].start():raw_words[end - 1].end()]
        candidates.setdefault(person_id, {"id": person_id, "name": display_name, "evidence": evidence})
    return candidates


def _evidenced(value: object, limit: int, name: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"value", "evidence"}:
        raise ValueError("Each proposed title, place or tag needs a value and a folder-name quote.")
    text, evidence = value["value"], value["evidence"]
    if (not isinstance(text, str) or not 1 <= len(text.strip()) <= limit or not text.isprintable()
            or not any(ch.isalnum() for ch in text)
            or not isinstance(evidence, str) or not 1 <= len(evidence) <= 255
            or evidence not in name or not evidence.isprintable()
            or not any(ch.isalpha() for ch in evidence)):
        raise ValueError("Use a single-line value and quote exact words from the folder name.")
    # A quote must not cut a word in half (e.g. 'Ana' inside 'Anabel').
    if not re.search(r"(?<![^\W_])" + re.escape(evidence) + r"(?![^\W_])", name):
        raise ValueError("Evidence must quote whole words from the folder name.")
    return {"value": text.strip(), "evidence": evidence}


class FolderCuration:
    """Read and curate index metadata without opening the photo archive."""

    def __init__(self, database: str | Path):
        self.database = Path(database).resolve(strict=True)
        if not self.database.is_file():
            raise ValueError("Choose an existing Chromantis SQLite file.")

    @contextmanager
    def read(self):
        with closing(connect(self.database.as_uri() + "?mode=ro", uri=True)) as connection:
            connection.row_factory = Row
            connection.execute("BEGIN")
            yield connection

    def album_identity(self, path: str) -> tuple[int, str, int]:
        with self.read() as connection:
            return self._identity(connection, path)

    def list_albums(
        self, *, year: int | None, missing_place: bool, limit: int, offset: int,
    ) -> list[dict]:
        """Operator-only index lookup; not exposed as an MCP tool."""
        with self.read() as connection:
            return [dict(row) for row in connection.execute(
                """SELECT f.folder_path AS path, f.indexed_year AS year, f.place
                   FROM album_metadata f
                   WHERE (? IS NULL OR f.indexed_year = ?) AND (? = 0 OR f.place IS NULL)
                   ORDER BY f.indexed_year DESC, f.folder_path
                   LIMIT ? OFFSET ?""",
                (year, year, missing_place, limit, offset),
            )]

    def library_page(
        self, *, after: int, year: int | None, missing_place: bool, limit: int,
    ) -> list[dict]:
        with self.read() as connection:
            return [dict(row) for row in connection.execute(
                """SELECT id, indexed_year, place IS NOT NULL AS has_place
                   FROM album_metadata
                   WHERE id > ? AND (? IS NULL OR indexed_year = ?) AND (? = 0 OR place IS NULL)
                   ORDER BY id LIMIT ?""",
                (after, year, year, missing_place, limit),
            )]

    def album_reference(self, album_id: int) -> tuple[str, tuple[int, str, int]]:
        with self.read() as connection:
            row = connection.execute(
                "SELECT folder_path, ftp_root_path, year FROM folders WHERE id = ?", (album_id,)
            ).fetchone()
        if row is None:
            raise ValueError("The selected album is not indexed anymore.")
        return row["folder_path"], (album_id, row["ftp_root_path"], row["year"])

    @staticmethod
    def _identity(connection: Connection, path: str) -> tuple[int, str, int]:
        row = connection.execute(
            "SELECT id, ftp_root_path, year FROM folders WHERE folder_path = ?", (path,)
        ).fetchone()
        if row is None:
            raise ValueError("The selected album is not indexed anymore.")
        return row["id"], row["ftp_root_path"], row["year"]

    def inspect(self, path: str, *, identity: tuple[int, str, int] | None = None) -> dict:
        with self.read() as connection:
            _, _, snapshot = self._snapshot(connection, path, identity)
            return snapshot

    def _snapshot(
        self, connection: Connection, path: str, identity: tuple[int, str, int] | None = None,
    ) -> tuple[Row, dict, dict]:
        current_identity = self._identity(connection, path)
        if identity is not None and identity != current_identity:
            raise ValueError("This album was replaced. Reopen the server with an explicit scope.")
        folder = review_folder(connection, path=path)
        assert folder is not None
        item = review_item(connection, folder)
        name = folder["folder_name_raw"]
        people = person_candidates(connection, name)
        linked_people = [dict(row) for row in connection.execute(
            """SELECT p.id, p.display_name AS name FROM folder_people fp
               JOIN people p ON p.id = fp.person_id WHERE fp.folder_id = ? ORDER BY p.id""",
            (folder["id"],),
        )]
        revision = hashlib.sha256(json.dumps(
            [str(self.database), current_identity, item, people, linked_people], sort_keys=True, ensure_ascii=True
        ).encode()).hexdigest()
        return folder, item, {
            "version": revision,
            "folder_name": name,
            "indexed_year": folder["indexed_year"],
            "title": folder["title"],
            "title_is_curated": folder["title_override"] is not None,
            "date": folder["event_date"],
            "date_is_curated": folder["date_override"] is not None,
            "folder_date": folder_date(name, folder["indexed_year"]),
            "place": folder["place"],
            "manual_tags": item["manual_tags"],
            "tag_suggestions": item["suggestions"],
            "linked_people": linked_people,
            "people_candidates": [
                candidate | {"already_linked": person_id in item["person_ids"]}
                for person_id, candidate in sorted(people.items())
            ],
        }

    def prepare(
        self, path: str, version: str, changes: dict, *, identity: tuple[int, str, int] | None = None,
    ) -> dict:
        with self.read() as connection:
            _, _, snapshot = self._snapshot(connection, path, identity)
            self._check_version(snapshot, version)
            return self._proposal(snapshot, changes)

    @staticmethod
    def _check_version(snapshot: dict, version: str) -> None:
        if snapshot["version"] != version:
            raise ValueError("The album or its evidence changed. Inspect it and prepare a new proposal.")

    @staticmethod
    def _proposal(snapshot: dict, changes: dict) -> dict:
        if not isinstance(changes, dict) or changes.keys() - {
            "title", "place", "use_folder_date", "tags", "person_ids",
        }:
            raise ValueError("Unsupported folder edit.")
        name = snapshot["folder_name"]
        context = {}
        for field, limit in (("title", 160), ("place", 120)):
            if field not in changes:
                continue
            proposed = _evidenced(changes[field], limit, name)
            if proposed["value"] == snapshot[field]:
                continue
            if snapshot.get(f"{field}_is_curated") or (field == "place" and snapshot[field]):
                raise ValueError(f"An existing curated {field} is not overwritten.")
            if field == "place" and (
                WORDS.findall(normalize_text(proposed["value"]))
                != WORDS.findall(normalize_text(proposed["evidence"]))
            ):
                raise ValueError("A place must be named explicitly in the folder.")
            context[field] = proposed | {"before": snapshot[field]}
        take_date = changes.get("use_folder_date", False)
        if type(take_date) is not bool:
            raise ValueError("use_folder_date must be a boolean.")
        if take_date:
            from_name = snapshot["folder_date"]
            if not from_name:
                raise ValueError("There is no unambiguous full folder date consistent with the indexed year.")
            if from_name["value"] != snapshot["date"]:
                if snapshot["date_is_curated"]:
                    raise ValueError("An existing curated date is not overwritten.")
                context["event_date"] = from_name | {"before": snapshot["date"]}

        tags = changes.get("tags", [])
        if not isinstance(tags, list) or len(tags) > 8:
            raise ValueError("Propose at most eight album tags.")
        manual, decisions, tag_changes = set(snapshot["manual_tags"]), {}, {}
        for value in tags:
            proposed = _evidenced(value, 40, name)
            tag = parse_tag(proposed["value"])
            suggestion = snapshot["tag_suggestions"].get(tag)
            if suggestion and suggestion["state"] in {"rejected", "corrected"}:
                raise ValueError("A reviewed tag decision cannot be overridden.")
            if tag in manual or (suggestion and suggestion["state"] == "accepted"):
                continue
            if suggestion:
                if suggestion["evidence"] not in WORDS.findall(normalize_text(proposed["evidence"])):
                    raise ValueError("Use the folder-name evidence attached to the tag suggestion.")
                decisions[tag] = tag
            tag_changes[tag] = proposed | {
                "value": tag, "action": "accept_suggestion" if suggestion else "add_manual_tag",
            }
        if len(manual | (set(tag_changes) - decisions.keys())) > 20:
            raise ValueError("The album would exceed twenty manual tags.")

        ids = changes.get("person_ids", [])
        if not isinstance(ids, list) or len(ids) > 8 or any(type(person_id) is not int for person_id in ids):
            raise ValueError("Choose at most eight existing people by candidate ID.")
        candidates = {person["id"]: person for person in snapshot["people_candidates"]}
        if not set(ids) <= candidates.keys():
            raise ValueError("Select only people with an unambiguous name or alias in the folder name.")
        people = [candidates[pid] for pid in sorted(set(ids)) if not candidates[pid]["already_linked"]]
        if not (context or tag_changes or people):
            raise ValueError("No new changes to propose.")
        return {"context": context, "tags": list(tag_changes.values()), "people": people}

    def apply(self, records: list[dict], *, via_mcp: bool = False) -> None:
        """Validate the supplied batch again in the transaction that saves it."""
        repository = Repository(str(self.database))
        with repository.write_transaction() as connection:
            for record in records:
                folder, item, snapshot = self._snapshot(connection, record["path"])
                self._check_version(snapshot, record["version"])
                proposal = self._proposal(snapshot, record["changes"])
                if proposal != record["proposal"]:
                    raise ValueError("The displayed proposal does not match the validated edits.")
                self._save(connection, folder, item, proposal)
                repository.record_audit_event(
                    "apply_folder_curation", "folder", record["path"],
                    {"origin": "mcp_folder_review",
                     "write_channel": "mcp_client" if via_mcp else "operator_terminal",
                     **proposal}, connection=connection,
                )

    @staticmethod
    def _save(connection: Connection, folder: Row, item: dict, proposal: dict) -> None:
        context = {key: edit["value"] for key, edit in proposal["context"].items()}
        if context:
            save_context(connection, folder, context)
        decisions = {
            tag["value"]: tag["value"] for tag in proposal["tags"] if tag["action"] == "accept_suggestion"
        }
        manual_add = {tag["value"] for tag in proposal["tags"] if tag["action"] == "add_manual_tag"}
        if decisions or manual_add or proposal["people"]:
            folder_id = folder["id"]
            reviewed = apply_tag_decisions(connection, folder_id, item, decisions, manual_add, set())
            connection.executemany(
                "INSERT INTO folder_people (folder_id, person_id) VALUES (?, ?)",
                ((folder_id, person["id"]) for person in proposal["people"]),
            )
            save_review_progress(connection, folder, reviewed)
