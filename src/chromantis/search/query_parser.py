from __future__ import annotations

import json
import re
from dataclasses import dataclass

from chromantis.db.repository import ResolvedPerson
from chromantis.parsing.path_parser import normalize_text

YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
YEAR_RANGE_RE = re.compile(r"\b((?:19|20)\d{2})\s*-\s*((?:19|20)\d{2})\b")
RECALL_FILTER_RE = re.compile(
    r'(?<!\S)(?:years:(?P<years>[1-9]\d{3}-[1-9]\d{3})|person:(?P<person>[1-9]\d{0,18})'
    r'|album:(?P<album>"(?:[^"\\]|\\.)*"))(?=\s|$)'
)


class QueryParseError(ValueError):
    """Raised when a search query contains unsupported or invalid syntax."""


@dataclass(frozen=True)
class RecallFilters:
    years: tuple[int, int] | None = None
    people: tuple[int, ...] = ()
    album: str | None = None

    def apply(self, text: str) -> str:
        parts = [text]
        if self.years:
            parts.append(f"years:{self.years[0]}-{self.years[1]}")
        parts.extend(f"person:{person_id}" for person_id in self.people)
        if self.album:
            parts.append("album:" + json.dumps(self.album, ensure_ascii=False))
        return " ".join(part for part in parts if part)


def split_recall(raw: str) -> tuple[str, RecallFilters]:
    years, album = None, None
    people = []
    for match in RECALL_FILTER_RE.finditer(raw):
        if value := match["years"]:
            first, last = map(int, value.split("-"))
            if first > last:
                raise QueryParseError("The refinement starts after it ends.")
            years = (first, last)
        elif value := match["person"]:
            people.append(int(value))
        else:
            try:
                album = json.loads(match["album"])
            except ValueError as exc:
                raise QueryParseError("Invalid album filter.") from exc
    text = RECALL_FILTER_RE.sub(" ", raw).strip()
    return text, RecallFilters(years, tuple(dict.fromkeys(people)), album)


@dataclass(frozen=True)
class ParsedQuery:
    raw: str
    year_from: int | None
    year_to: int | None
    people: tuple[ResolvedPerson, ...]
    keywords: tuple[str, ...]
    phrase: str = ""
    literal_phrase: str = ""
    recall: RecallFilters = RecallFilters()

    @property
    def person_ids(self) -> tuple[int, ...]:
        return tuple(person.id for person in self.people)


def parse_query(
    raw: str, alias_map: dict[str, ResolvedPerson] | None = None
) -> ParsedQuery:
    base, recall = split_recall(raw)
    working_text = base
    year_from: int | None = None
    year_to: int | None = None

    range_match = YEAR_RANGE_RE.search(working_text)
    if range_match:
        year_from = int(range_match.group(1))
        year_to = int(range_match.group(2))
        if year_from > year_to:
            raise QueryParseError("Year ranges must be increasing, for example 2018-2021.")
        working_text = (
            working_text[: range_match.start()] + " " + working_text[range_match.end() :]
        )
    else:
        standalone_years = [int(match.group(1)) for match in YEAR_RE.finditer(working_text)]
        if len(standalone_years) == 1:
            year_from = standalone_years[0]
            year_to = standalone_years[0]
            working_text = YEAR_RE.sub(" ", working_text, count=1)

    normalized_tokens = [token for token in normalize_text(working_text).split(" ") if token]
    people, keywords = _extract_people_and_keywords(normalized_tokens, alias_map or {})
    return ParsedQuery(
        raw=raw,
        year_from=year_from,
        year_to=year_to,
        people=people,
        keywords=keywords,
        phrase=" ".join(normalized_tokens),
        literal_phrase=normalize_text(base),
        recall=recall,
    )


def _extract_people_and_keywords(
    tokens: list[str], alias_map: dict[str, ResolvedPerson]
) -> tuple[tuple[ResolvedPerson, ...], tuple[str, ...]]:
    if not tokens:
        return (), ()
    alias_tokens = {
        alias: tuple(alias.split(" "))
        for alias in alias_map
        if alias and all(part for part in alias.split(" "))
    }
    phrase_lengths = sorted(
        {len(parts) for parts in alias_tokens.values()},
        reverse=True,
    )
    matched_people: list[ResolvedPerson] = []
    seen_person_ids: set[int] = set()
    keywords: list[str] = []
    index = 0
    while index < len(tokens):
        matched_alias: str | None = None
        for length in phrase_lengths:
            if index + length > len(tokens):
                continue
            candidate = " ".join(tokens[index : index + length])
            if candidate in alias_tokens:
                matched_alias = candidate
                break
        if matched_alias is not None:
            if index and keywords and tokens[index - 1] in {"with", "con"} and keywords[-1] == tokens[index - 1]:
                keywords.pop()
            person = alias_map[matched_alias]
            if person.id not in seen_person_ids:
                matched_people.append(person)
                seen_person_ids.add(person.id)
            index += len(alias_tokens[matched_alias])
            continue
        keywords.append(tokens[index])
        index += 1
    return tuple(matched_people), tuple(keywords)
