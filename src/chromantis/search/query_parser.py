from __future__ import annotations

import re
from dataclasses import dataclass

from chromantis.db.repository import ResolvedPerson
from chromantis.parsing.path_parser import normalize_text

YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
YEAR_RANGE_RE = re.compile(r"\b((?:19|20)\d{2})\s*-\s*((?:19|20)\d{2})\b")


class QueryParseError(ValueError):
    """Raised when a search query contains unsupported or invalid syntax."""


@dataclass(frozen=True)
class ParsedQuery:
    raw: str
    year_from: int | None
    year_to: int | None
    people: tuple[ResolvedPerson, ...]
    keywords: tuple[str, ...]

    @property
    def person_ids(self) -> tuple[int, ...]:
        return tuple(person.id for person in self.people)


def parse_query(
    raw: str, alias_map: dict[str, ResolvedPerson] | None = None
) -> ParsedQuery:
    working_text = raw.strip()
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
            person = alias_map[matched_alias]
            if person.id not in seen_person_ids:
                matched_people.append(person)
                seen_person_ids.add(person.id)
            index += len(alias_tokens[matched_alias])
            continue
        keywords.append(tokens[index])
        index += 1
    return tuple(matched_people), tuple(keywords)
