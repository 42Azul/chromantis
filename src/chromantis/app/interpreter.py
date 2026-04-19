from __future__ import annotations

import re
from dataclasses import dataclass

FILLER_WORDS = {
    "a",
    "all",
    "an",
    "do",
    "find",
    "for",
    "from",
    "have",
    "i",
    "image",
    "images",
    "me",
    "memory",
    "memories",
    "of",
    "photo",
    "photos",
    "picture",
    "pictures",
    "please",
    "search",
    "show",
    "some",
    "the",
    "with",
}


@dataclass(frozen=True)
class InterpretedRequest:
    action: str
    query: str
    count: int


class RuleQueryInterpreter:
    YEARS_HINT_RE = re.compile(r"\b(years?|what years?)\b", re.IGNORECASE)
    RANDOM_HINT_RE = re.compile(r"\b(random|surprise|memory)\b", re.IGNORECASE)
    FOLDERS_HINT_RE = re.compile(r"\b(folder|folders|album|albums|trip|event)\b", re.IGNORECASE)
    COUNT_RE = re.compile(r"\b(\d{1,2})\b")

    def interpret(self, text: str) -> InterpretedRequest:
        raw = text.strip()
        lowered = raw.lower()
        if self.YEARS_HINT_RE.search(lowered) and not re.search(r"\b(19|20)\d{2}\b", lowered):
            return InterpretedRequest(action="years", query="", count=1)

        action = "images"
        if self.RANDOM_HINT_RE.search(lowered):
            action = "random"
        elif self.FOLDERS_HINT_RE.search(lowered):
            action = "folders"

        count = 3 if action == "images" else 1
        count_match = self.COUNT_RE.search(lowered)
        if count_match:
            count = max(1, min(int(count_match.group(1)), 10))

        query = self._normalize_query(raw)
        return InterpretedRequest(action=action, query=query, count=count)

    def _normalize_query(self, text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r"[?!.:,]+", " ", cleaned)
        tokens = []
        for token in cleaned.split():
            lowered = token.lower()
            if lowered.isdigit() and 1 <= int(lowered) <= 10:
                continue
            if lowered in FILLER_WORDS:
                continue
            tokens.append(token)
        return " ".join(tokens).strip()
