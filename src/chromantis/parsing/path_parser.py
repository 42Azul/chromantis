from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import PurePosixPath

STOPWORDS = {
    "a",
    "an",
    "and",
    "con",
    "de",
    "del",
    "el",
    "en",
    "la",
    "las",
    "los",
    "the",
    "to",
    "trip",
    "viaje",
}

YEAR_SEGMENT_RE = re.compile(r"^(\d{4})(?:\(\d+\))?$")

SEASONS = {
    12: "winter",
    1: "winter",
    2: "winter",
    3: "spring",
    4: "spring",
    5: "spring",
    6: "summer",
    7: "summer",
    8: "summer",
    9: "autumn",
    10: "autumn",
    11: "autumn",
}


class PathParseError(ValueError):
    """Raised when a path does not match the expected subtree layout."""


@dataclass(frozen=True)
class ParsedImageRecord:
    source_root: str
    folder_path: str
    file_path: str
    year: int
    folder_name_raw: str
    folder_slug: str
    title: str
    event_date: str | None
    filename: str
    extension: str
    file_size: int | None
    source_modified_at: str | None
    folder_tags: tuple[tuple[str, str], ...]
    image_tags: tuple[tuple[str, str], ...]


class PathParser:
    def parse_image_path(
        self,
        source_root: str,
        relative_path: str,
        file_size: int | None,
        modified_at: str | None,
    ) -> ParsedImageRecord:
        relative = relative_path.strip("/")
        parts = PurePosixPath(relative).parts
        if len(parts) != 3:
            raise PathParseError(f"Expected /year/folder/file path, got {relative}")

        year_segment, folder_name_raw, filename = parts
        year_match = YEAR_SEGMENT_RE.fullmatch(year_segment)
        if not year_match:
            raise PathParseError(f"Invalid year segment: {year_segment}")

        extension = PurePosixPath(filename).suffix.lower()
        folder_slug = slugify(folder_name_raw)
        title = humanize(folder_name_raw)
        event_date = extract_event_date(folder_name_raw, year=int(year_match.group(1)))
        folder_tags = build_folder_tags(folder_name_raw, event_date)
        image_tags = build_image_tags(filename)

        return ParsedImageRecord(
            source_root=source_root,
            folder_path=f"{year_segment}/{folder_name_raw}",
            file_path=relative,
            year=int(year_match.group(1)),
            folder_name_raw=folder_name_raw,
            folder_slug=folder_slug,
            title=title,
            event_date=event_date,
            filename=filename,
            extension=extension,
            file_size=file_size,
            source_modified_at=modified_at,
            folder_tags=folder_tags,
            image_tags=image_tags,
        )


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = stripped.lower()
    normalized = re.sub(r"[_\-]+", " ", lowered)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def slugify(value: str) -> str:
    return normalize_text(value)


def humanize(value: str) -> str:
    text = normalize_text(value)
    return re.sub(r"\s+", " ", text).strip()


def extract_event_date(folder_name_raw: str, *, year: int | None = None) -> str | None:
    match = re.match(r"^(\d{4}-\d{2}-\d{2})(?:[_-]|$)", folder_name_raw)
    if match:
        candidate = match.group(1)
    else:
        compact = re.match(r"^([0-9]{4})([0-9]{2})([0-9]{2})(?: - |$)", folder_name_raw)
        if not compact or year != int(compact.group(1)):
            return None
        candidate = "-".join(compact.groups())
    try:
        return date.fromisoformat(candidate).isoformat()
    except ValueError:
        return None


def tokenize_folder(folder_name_raw: str) -> list[str]:
    normalized = normalize_text(folder_name_raw)
    normalized = re.sub(r"^\d{4}\s\d{2}\s\d{2}\s*", "", normalized)
    tokens = re.split(r"\s+", normalized)
    return [token for token in tokens if token and token not in STOPWORDS and not token.isdigit()]


def build_folder_tags(folder_name_raw: str, event_date: str | None) -> tuple[tuple[str, str], ...]:
    tags: list[tuple[str, str]] = []
    for token in tokenize_folder(folder_name_raw):
        tags.append((token, "path"))
    if event_date:
        month = int(event_date[5:7])
        tags.append((SEASONS[month], "rule"))
        tags.append((event_date[:7], "rule"))
    return tuple(dict.fromkeys(tags))


def build_image_tags(filename: str) -> tuple[tuple[str, str], ...]:
    normalized_stem = normalize_text(PurePosixPath(filename).stem)
    if not normalized_stem or normalized_stem.startswith("img ") or normalized_stem.startswith("dsc "):
        return ()
    tokens = [token for token in normalized_stem.split(" ") if token and token not in STOPWORDS]
    return tuple((token, "path") for token in dict.fromkeys(tokens))
