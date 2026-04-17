from __future__ import annotations

import re
from dataclasses import dataclass

from chromantis.parsing.path_parser import normalize_text


@dataclass(frozen=True)
class ParsedQuery:
    raw: str
    year: int | None
    keywords: tuple[str, ...]


def parse_query(raw: str) -> ParsedQuery:
    match = re.search(r"\b(19|20)\d{2}\b", raw)
    year = int(match.group(0)) if match else None
    normalized = normalize_text(raw)
    keywords = tuple(
        token
        for token in normalized.split(" ")
        if token and not re.fullmatch(r"(19|20)\d{2}", token)
    )
    return ParsedQuery(raw=raw, year=year, keywords=keywords)
