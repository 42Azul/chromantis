from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "es")
STRINGS_DIR = Path(__file__).with_name("strings")


@lru_cache(maxsize=1)
def _load_catalog() -> dict[str, dict[str, str]]:
    catalog: dict[str, dict[str, str]] = {}
    for language in SUPPORTED_LANGUAGES:
        path = STRINGS_DIR / f"{language}.json"
        with path.open("r", encoding="utf-8") as handle:
            catalog[language] = json.load(handle)
    return catalog


def normalize_language(language: str | None) -> str:
    if language in SUPPORTED_LANGUAGES:
        return str(language)
    return DEFAULT_LANGUAGE


def language_name(target_language: str, language_code: str) -> str:
    return t(target_language, f"language_name_{normalize_language(language_code)}")


def t(language: str | None, key: str, **kwargs: object) -> str:
    normalized = normalize_language(language)
    catalog = _load_catalog().get(normalized, _load_catalog()[DEFAULT_LANGUAGE])
    template = catalog[key]
    if kwargs:
        return template.format(**kwargs)
    return template


def catalog_keys() -> dict[str, set[str]]:
    return {language: set(messages.keys()) for language, messages in _load_catalog().items()}
