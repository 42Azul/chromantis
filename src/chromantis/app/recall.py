from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace

from chromantis.db.repository import ResolvedPerson
from chromantis.parsing.path_parser import normalize_text
from chromantis.search.query_parser import RecallFilters, parse_query, split_recall
from chromantis.search.service import SearchResult


INTENT = re.compile(
    r"^(?P<prefix>antes de|después de|despues de|solo|sólo|en el álbum|en el album|"
    r"álbum|album|con|before|after|only|in album|with)\s+(?P<value>.+)$",
    re.IGNORECASE,
)
YEAR = re.compile(r"[1-9][0-9]{3}")
ALBUM_REQUEST = re.compile(
    r"^(?:fotos|[aá]lbumes)\s+(?:de(?:\s+(?:el|la|los|las))?|del)\s+"
    r"(?P<topic>.+?)\s+con\s+(?P<name>.+?)\s+"
    r"(?P<direction>antes|despu[eé]s)\s+de\s+(?P<year>[1-9][0-9]{3})[?.!]?$",
    re.IGNORECASE,
)
MIN_YEAR, MAX_YEAR = 1000, 9999


@dataclass(frozen=True)
class Refinement:
    query: str | None = None
    choices: tuple[SearchResult, ...] = ()


class RefinementError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def is_refinement(text: str) -> bool:
    return INTENT.fullmatch(text.strip()) is not None


def normalize_album_request(
    text: str, aliases: Callable[[], dict[str, ResolvedPerson]],
) -> str:
    match = ALBUM_REQUEST.fullmatch(text.strip())
    if match is None:
        return text
    person = aliases().get(normalize_text(match["name"]))
    if person is None:
        raise RefinementError("person", "Ese nombre o alias no figura en Personas.")
    year = int(match["year"])
    years = (MIN_YEAR, year - 1) if match["direction"].lower() == "antes" else (year + 1, MAX_YEAR)
    if years[0] > years[1]:
        raise RefinementError("year_conflict", "El año indicado queda fuera del intervalo de búsqueda.")
    return RecallFilters(years=years, people=(person.id,)).apply(match["topic"])


def refine(
    base: str, text: str, alias_map: dict[str, ResolvedPerson],
    folders: Callable[[str, int], list[SearchResult]],
) -> Refinement:
    if not base.strip():
        raise RefinementError("no_query", "Start a search before refining it.")
    match = INTENT.fullmatch(text.strip())
    if not match:
        raise RefinementError("usage", "Try “before 2020”, “with Ana” or “album Beach trip”.")
    prefix = normalize_text(match["prefix"])
    value = match["value"].strip()
    previous, filters = split_recall(base)
    if prefix in {"antes de", "before", "despues de", "after", "solo", "only"}:
        if YEAR.fullmatch(value) is None:
            raise RefinementError("year", "Enter a four-digit year.")
        year = int(value)
        first, last = filters.years or (MIN_YEAR, MAX_YEAR)
        parsed = parse_query(previous)
        first, last = max(first, parsed.year_from or MIN_YEAR), min(last, parsed.year_to or MAX_YEAR)
        if prefix in {"antes de", "before"}:
            last = min(last, year - 1)
        elif prefix in {"despues de", "after"}:
            first = max(first, year + 1)
        else:
            first, last = max(first, year), min(last, year)
        if first > last:
            raise RefinementError("year_conflict", "That year does not overlap the current search.")
        return Refinement(replace(filters, years=(first, last)).apply(previous))
    if prefix in {"con", "with"}:
        person = alias_map.get(normalize_text(value))
        if person is None:
            raise RefinementError("person", "That name or alias is not in People.")
        people = tuple(dict.fromkeys((*filters.people, person.id)))
        return Refinement(replace(filters, people=people).apply(previous))

    exact = folders(replace(filters, album=value).apply(""), 1)
    choices = exact or folders(filters.apply(value), 6)
    if filters.album:
        choices = [item for item in choices if item.path == filters.album]
    if not choices:
        raise RefinementError("album", "No album matches that name or path in the current filter.")
    if len(choices) > 1:
        return Refinement(choices=tuple(choices))
    return Refinement(replace(filters, album=choices[0].path).apply(previous))
