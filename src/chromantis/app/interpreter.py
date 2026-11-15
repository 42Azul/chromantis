from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from typing import Protocol

from chromantis.parsing.path_parser import normalize_text
from chromantis.search.query_parser import YEAR_RANGE_RE, YEAR_RE

logger = logging.getLogger(__name__)

FILLER_WORDS = {
    "a",
    "all",
    "album",
    "albums",
    "folder",
    "folders",
    "carpeta",
    "carpetas",
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
    "ano",
    "anos",
    "busca",
    "buscar",
    "buscame",
    "de",
    "del",
    "el",
    "en",
    "ensename",
    "fotos",
    "foto",
    "imagen",
    "imagenes",
    "la",
    "las",
    "los",
    "muestrame",
    "por",
    "quiero",
    "recuerdo",
    "recuerdos",
    "un",
    "una",
}


@dataclass(frozen=True)
class InterpretedRequest:
    action: str
    query: str
    count: int
    needs_clarification: bool = False
    clarification: str | None = None
    confidence: float = 1.0


class QueryInterpreter(Protocol):
    def interpret(self, text: str) -> InterpretedRequest:
        ...


class RuleQueryInterpreter:
    YEARS_HINT_RE = re.compile(r"\b(years?|what years?|ano|anos|año|años)\b", re.IGNORECASE)
    RANDOM_HINT_RE = re.compile(
        r"\b(random|surprise|memory|aleatorio|azar|recuerdo|recuerdos)\b",
        re.IGNORECASE,
    )
    FOLDERS_HINT_RE = re.compile(
        r"\b(folder|folders|album|albums|trip|event|carpeta|carpetas|evento|eventos)\b",
        re.IGNORECASE,
    )
    COUNT_RE = re.compile(r"\b(\d{1,2})\b")

    def interpret(self, text: str) -> InterpretedRequest:
        raw = text.strip().replace("–", "-")
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
        clarification = None
        years = YEAR_RE.findall(YEAR_RANGE_RE.sub("", raw))
        if len(set(years)) > 1:
            clarification = "several_years"
        elif not query:
            clarification = "folders" if action == "folders" else "query"
        return InterpretedRequest(
            action=action,
            query=query,
            count=count,
            needs_clarification=clarification is not None,
            clarification=clarification,
            confidence=0.0 if clarification else 1.0,
        )

    def _normalize_query(self, text: str) -> str:
        ranges = [
            (match.group(1), match.group(2)) for match in YEAR_RANGE_RE.finditer(text)
        ]
        cleaned = normalize_text(text.strip())
        for start, end in ranges:
            cleaned = re.sub(rf"\b{start} {end}\b", f"{start}-{end}", cleaned, count=1)
        cleaned = re.sub(r"[?!.:,]+", " ", cleaned)
        tokens = []
        for token in cleaned.split():
            if token.isdigit() and 1 <= int(token) <= 10:
                continue
            if token in FILLER_WORDS:
                continue
            tokens.append(token)
        return " ".join(tokens).strip()


class CommandQueryInterpreter:
    """Run a configured local model adapter and fall back to rules if it fails."""

    def __init__(self, command: tuple[str, ...], timeout: float):
        self.command = command
        self.timeout = timeout
        self.rules = RuleQueryInterpreter()

    def interpret(self, text: str) -> InterpretedRequest:
        try:
            result = subprocess.run(
                self.command,
                input=json.dumps({"text": text}, ensure_ascii=False),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                encoding="utf-8",
                timeout=self.timeout,
                check=True,
            )
            return _model_response(json.loads(result.stdout))
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            logger.warning("Query interpreter unavailable (%s); using rules", type(exc).__name__)
            return self.rules.interpret(text)


def _model_response(data: object) -> InterpretedRequest:
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object from the interpreter.")

    confidence = data.get("confidence")
    if type(confidence) not in {float, int} or not 0 <= confidence <= 1:
        raise ValueError("Invalid interpreter confidence.")
    if confidence < 0.65:
        return InterpretedRequest("images", "", 3, True, "model_uncertain", float(confidence))

    action, query, count = (data.get(key) for key in ("action", "query", "count"))
    if not isinstance(action, str) or action not in {"images", "folders", "random", "years"}:
        raise ValueError("Unsupported interpreter action.")
    if not isinstance(query, str) or len(query) > 2000 or any(char in query for char in "\r\n\x00"):
        raise ValueError("Invalid interpreter query.")
    if type(count) is not int or not 1 <= count <= 10:
        raise ValueError("Invalid interpreter result count.")
    query = query.strip()
    if not query and action in {"images", "folders"}:
        return InterpretedRequest(action, "", count, True, "model_uncertain", float(confidence))
    return InterpretedRequest(action, query, count, confidence=float(confidence))
