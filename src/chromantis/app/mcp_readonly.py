from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass

from chromantis.app.service import ApplicationService
from chromantis.parsing.path_parser import normalize_text


class McpAccessError(ValueError):
    """Raised when an album-scoped MCP capability is no longer valid."""


@dataclass(frozen=True)
class AlbumMcpPrincipal:
    """A revocable capability that is restricted to one shared album."""

    secret: str


class ReadOnlyAlbumMcp:
    """Transport-neutral MCP tool core for one revocable album share."""

    TOOL_DEFINITIONS = (
        {
            "name": "chromantis_list_album",
            "description": "List metadata and indexed filenames for the one granted album.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
                    "offset": {"type": "integer", "minimum": 0, "default": 0},
                },
                "additionalProperties": False,
            },
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        },
        {
            "name": "chromantis_search_album",
            "description": "Search metadata and indexed filenames inside the one granted album.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        },
    )

    def __init__(self, app: ApplicationService, principal: AlbumMcpPrincipal):
        self.app = app
        self.principal = principal

    @classmethod
    def list_tools(cls) -> list[dict]:
        return [deepcopy(tool) for tool in cls.TOOL_DEFINITIONS]

    def call_tool(self, name: str, arguments: object = None) -> dict:
        values = {} if arguments is None else arguments
        if not isinstance(values, dict):
            raise ValueError("Tool arguments must be an object.")
        if name == "chromantis_list_album":
            self._only_keys(values, {"limit", "offset"})
            payload = self._list_album(
                self._bounded_int(values.get("limit", 50), "limit", 1, 100),
                self._bounded_int(values.get("offset", 0), "offset", 0, 2**31 - 1),
            )
        elif name == "chromantis_search_album":
            self._only_keys(values, {"query", "limit"})
            query = values.get("query")
            if not isinstance(query, str) or not normalize_text(query):
                raise ValueError("query must contain searchable text.")
            payload = self._search_album(
                query, self._bounded_int(values.get("limit", 50), "limit", 1, 100)
            )
        else:
            raise ValueError("Unknown or unavailable read-only MCP tool.")
        return {
            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
            "structuredContent": payload,
            "isError": False,
        }

    def _list_album(self, limit: int, offset: int) -> dict:
        with self.app.album_share(self.principal.secret) as (store, share):
            if share is None:
                raise McpAccessError("The album grant is invalid, expired, or revoked.")
            photos = store.images(share, limit, offset)
            return self._payload(share, photos, query=None, has_more=len(photos) == limit)

    def _search_album(self, query: str, limit: int) -> dict:
        tokens = tuple(normalize_text(query).split())
        with self.app.album_share(self.principal.secret) as (store, share):
            if share is None:
                raise McpAccessError("The album grant is invalid, expired, or revoked.")
            album_text = normalize_text(" ".join(
                str(share.get(key) or "")
                for key in ("title", "event_date", "year", "place", "note")
            ))
            if all(token in album_text for token in tokens):
                photos = store.images(share, limit, 0)
            else:
                photos = store.search_images(share, tokens, limit)
            return self._payload(share, photos, query=query, has_more=False)

    @staticmethod
    def _payload(share: dict, photos: list[dict], query: str | None, has_more: bool) -> dict:
        return {
            "album": {
                key: share[key]
                for key in ("title", "event_date", "year", "place", "note", "expires_at")
            },
            "photos": [{"filename": photo["filename"]} for photo in photos],
            "query": query,
            "has_more": has_more,
        }

    @staticmethod
    def _bounded_int(value: object, name: str, minimum: int, maximum: int) -> int:
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError(f"{name} must be an integer between {minimum} and {maximum}.")
        return value

    @staticmethod
    def _only_keys(values: dict, allowed: set[str]) -> None:
        if set(values) - allowed:
            raise ValueError("Unexpected tool argument.")
