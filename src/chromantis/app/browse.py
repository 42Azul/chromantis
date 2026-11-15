from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace

from chromantis.app.service import ApplicationService, AuthOperationError
from chromantis.search.service import SearchResult


@dataclass(frozen=True)
class BrowseBatch:
    scope: str
    query: str
    count: int
    folder_path: str | None = None
    year: int | None = None
    seen: tuple[str, ...] = ()
    items: tuple[SearchResult, ...] = ()

    @classmethod
    def from_dict(cls, data: dict) -> BrowseBatch:
        return cls(
            scope=data["scope"], query=data["query"], count=data["count"],
            folder_path=data["folder_path"], year=data["year"], seen=tuple(data["seen"]),
            items=tuple(SearchResult(**item) for item in data["items"]),
        )

    @property
    def folders(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.folder_path for item in self.items if item.folder_path))

    @property
    def years(self) -> tuple[int, ...]:
        return tuple(dict.fromkeys(item.year for item in self.items))

    def response(self, can_go_back: bool) -> dict[str, object]:
        return {
            "items": [asdict(item) for item in self.items],
            "scope": self.scope,
            "q": self.query,
            "count": self.count,
            "folders": self.folders,
            "years": self.years,
            "can_go_back": can_go_back,
        }


def browse(
    app: ApplicationService, chat_id: int, action: str, *, q: str = "",
    count: int | None = None, folder_path: str | None = None, year: int | None = None,
) -> dict[str, object]:
    repository = app.repository
    with repository.write_transaction() as connection:
        if app.resolve_principal(chat_id, connection=connection).role == "none":
            raise AuthOperationError("unauthorized", "Chat is not authorized.", 401)
        stored = repository.get_api_browse_session(connection, chat_id)
        history = [BrowseBatch.from_dict(batch) for batch in json.loads(stored)] if stored else []
        current = history[-1] if history else None
        if action == "current":
            if current is None:
                raise AuthOperationError("no_browse_session", "No active browse session.", 404)
            return current.response(len(history) > 1)
        if action == "back":
            if len(history) < 2:
                raise AuthOperationError("no_browse_history", "No previous browse batch.", 409)
            history.pop()
        else:
            batch = _next_scope(current, action, q, count, folder_path, year)
            items = app.images_for_scope(
                batch.scope, batch.query, batch.count, batch.folder_path, batch.year, batch.seen
            )
            if not items and current is not None and action not in {"search", "random", "open_folder", "open_year"}:
                return replace(current, items=()).response(len(history) > 1)
            if action in {"search", "random"} and batch.query.strip():
                kind = "images" if action == "search" else "random"
                repository.record_search(connection, chat_id, kind, batch.query.strip(), batch.count)
            seen = tuple(dict.fromkeys((*batch.seen, *(item.path for item in items))))
            history = [*history[-9:], replace(batch, items=tuple(items), seen=seen)]
        repository.save_api_browse_session(
            connection, chat_id, json.dumps([asdict(batch) for batch in history])
        )
        return history[-1].response(len(history) > 1)


def _next_scope(
    current: BrowseBatch | None,
    action: str,
    q: str,
    count: int | None,
    folder_path: str | None,
    year: int | None,
) -> BrowseBatch:
    if action in {"search", "random"}:
        scope = "search_images" if action == "search" else "random_images"
        default_count = 10 if action == "search" else 1
        return BrowseBatch(scope, q, count or default_count)
    if action == "open_folder" and folder_path:
        return BrowseBatch("same_folder", "", count or 10, folder_path)
    if action == "open_year" and year is not None:
        return BrowseBatch("same_year", "", count or 10, year=year)
    if action not in {"more", "same_folder", "same_year", "related"}:
        raise ValueError("Unknown browse action or missing folder/year.")
    if action == "same_folder" and folder_path and current is None:
        return BrowseBatch("same_folder", "", count or 10, folder_path)
    if action == "same_year" and year is not None and current is None:
        return BrowseBatch("same_year", "", count or 10, year=year)
    if current is None:
        raise AuthOperationError("no_browse_session", "No active browse session.", 404)
    if action == "more":
        return replace(current, count=count or current.count)
    if action == "same_folder":
        folder_path = folder_path or (current.folders[0] if len(current.folders) == 1 else None)
        if not folder_path:
            raise AuthOperationError("no_folder_context", "Choose a folder from the batch.", 409)
        return BrowseBatch("same_folder", "", count or current.count, folder_path, seen=current.seen)
    if action == "same_year":
        year = year if year is not None else (current.years[0] if len(current.years) == 1 else None)
        if year is None:
            raise AuthOperationError("no_year_context", "Choose a year from the batch.", 409)
        return BrowseBatch("same_year", "", count or current.count, year=year, seen=current.seen)
    folder_path = folder_path or (current.folders[0] if len(current.folders) == 1 else None)
    year = year if year is not None else (current.years[0] if len(current.years) == 1 else None)
    if not folder_path or year is None:
        raise AuthOperationError("no_related_context", "Choose a folder and year from the batch.", 409)
    return BrowseBatch("related_images", "", count or current.count, folder_path, year, current.seen)
