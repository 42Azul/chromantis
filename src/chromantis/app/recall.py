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
PEOPLE_SEPARATOR = re.compile(r"\s*,\s*|\s+(?:y|e|and)\s+", re.IGNORECASE)
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
    people = resolve_people(match["name"], aliases())
    year = int(match["year"])
    years = (MIN_YEAR, year - 1) if match["direction"].lower() == "antes" else (year + 1, MAX_YEAR)
    if years[0] > years[1]:
        raise RefinementError("year_conflict", "El año indicado queda fuera del intervalo de búsqueda.")
    return RecallFilters(years=years, people=people).apply(match["topic"])


def resolve_people(value: str, alias_map: dict[str, ResolvedPerson]) -> tuple[int, ...]:
    # An exact saved name or alias takes precedence over list punctuation.
    if person := alias_map.get(normalize_text(value)):
        return (person.id,)
    names = PEOPLE_SEPARATOR.split(value.strip())
    resolved = [alias_map.get(normalize_text(name)) if name.strip() else None for name in names]
    unknown = [name.strip() or "(nombre vacío)" for name, person in zip(names, resolved) if person is None]
    if unknown:
        raise RefinementError("person", "No figuran en Personas: " + ", ".join(unknown) + ". Revisa la lista.")
    return tuple(dict.fromkeys(person.id for person in resolved if person is not None))


def refine(
    base: str, text: str, alias_map: dict[str, ResolvedPerson],
    folders: Callable[[str, int], list[SearchResult]],
    *, allow_empty: bool = False,
) -> Refinement:
    if not base.strip() and not allow_empty:
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
        requested = resolve_people(value, alias_map)
        people = tuple(dict.fromkeys((*filters.people, *requested)))
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
