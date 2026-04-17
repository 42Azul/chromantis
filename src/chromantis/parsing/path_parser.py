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
    ftp_root_path: str
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
    ftp_modified_at: str | None
    folder_tags: tuple[tuple[str, str], ...]
    image_tags: tuple[tuple[str, str], ...]

    @property
    def absolute_file_path(self) -> str:
        return f"{self.ftp_root_path.rstrip('/')}/{self.file_path.lstrip('/')}"


class PathParser:
    def parse_image_path(
        self,
        ftp_root_path: str,
        absolute_path: str,
        file_size: int | None,
        ftp_modified_at: str | None,
    ) -> ParsedImageRecord:
        relative = self._relative_path(ftp_root_path, absolute_path)
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
        event_date = extract_event_date(folder_name_raw)
        folder_tags = build_folder_tags(folder_name_raw, event_date)
        image_tags = build_image_tags(filename)

        return ParsedImageRecord(
            ftp_root_path=ftp_root_path,
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
            ftp_modified_at=ftp_modified_at,
            folder_tags=folder_tags,
            image_tags=image_tags,
        )

    @staticmethod
    def _relative_path(ftp_root_path: str, absolute_path: str) -> str:
        root = ftp_root_path.rstrip("/")
        if not absolute_path.startswith(root + "/"):
            raise PathParseError(f"Path {absolute_path} is outside root {ftp_root_path}")
        return absolute_path[len(root) + 1 :]


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


def extract_event_date(folder_name_raw: str) -> str | None:
    match = re.match(r"^(\d{4}-\d{2}-\d{2})(?:[_-]|$)", folder_name_raw)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1)).isoformat()
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
