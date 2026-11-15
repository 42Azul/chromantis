from __future__ import annotations

import json
from dataclasses import asdict
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from chromantis.app import ApplicationService, AuthOperationError


def handle_api_get(
    path: str,
    app_service: ApplicationService,
    api_token: str | None = None,
    auth_header: str | None = None,
    x_api_token: str | None = None,
) -> tuple[int, dict[str, object]]:
    return _dispatch("GET", path, app_service, api_token, (), auth_header, x_api_token)


def _dispatch(
    method: str,
    url: str,
    app_service: ApplicationService,
    api_token: str | None,
    api_chat_tokens: tuple[tuple[int, str], ...],
    auth_header: str | None,
    x_api_token: str | None,
    body: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    parsed = urlparse(url)
    path = parsed.path
    if method == "GET" and path == "/api/v1/health":
        return 200, {"status": "ok"}
    scheme, _, credential = (auth_header or "").partition(" ")
    supplied = credential if scheme.lower() == "bearer" else None

    def accepts(token: str) -> bool:
        return any(
            compare_digest(candidate.encode(), token.encode())
            for candidate in (supplied, x_api_token)
            if candidate is not None
        )

    chat_id = next((chat_id for chat_id, token in api_chat_tokens if accepts(token)), None)
    if chat_id is not None and not app_service.is_authorized_chat(chat_id):
        return 401, {"error": "Unauthorized"}
    if chat_id is None and (api_token or api_chat_tokens) and not (api_token and accepts(api_token)):
        return 401, {"error": "Unauthorized"}

    try:
        if path == "/api/v1/auth/me" or path.startswith("/api/v1/admin/"):
            if chat_id is None:
                return 401, {"error": "A chat token is required"}
            return _auth_route(method, path, app_service, chat_id, body or {})
        if method == "GET":
            return _query_route(path, parse_qs(parsed.query), app_service)
        return 404, {"error": "Not found"}
    except AuthOperationError as exc:
        return exc.status, {"error": str(exc), "code": exc.code}
    except ValueError as exc:
        return 400, {"error": str(exc)}


def _auth_route(
    method: str,
    path: str,
    app_service: ApplicationService,
    chat_id: int,
    body: dict[str, object],
) -> tuple[int, dict[str, object]]:
    if method == "GET" and path == "/api/v1/auth/me":
        return 200, {"item": asdict(app_service.resolve_principal(chat_id))}
    if method == "GET" and path == "/api/v1/admin/chats":
        app_service.require_admin(chat_id, "authorized_requires_admin")
        return 200, {"items": [asdict(item) for item in app_service.list_effective_authorized_chats()]}
    resource, _, key = path.rpartition("/")
    if method in {"PATCH", "DELETE"} and resource == "/api/v1/admin/chats" and key:
        target = int(key)
        if not -(2**63) <= target < 2**63:
            raise ValueError("Invalid chat ID.")
        if method == "PATCH":
            role = _role(body, {"viewer", "admin", "owner"})
            return 200, {"item": asdict(app_service.set_chat_role(target, role, chat_id))}
        app_service.revoke_chat_access(target, chat_id)
        return 200, {"revoked": True}
    if path == "/api/v1/admin/invites":
        if method == "GET":
            return 200, {"items": [asdict(item) for item in app_service.list_invites(chat_id)]}
        if method == "POST":
            role = _role(body, {"viewer", "admin"}, default="viewer")
            ttl_days = body.get("ttl_days", 7)
            if type(ttl_days) is not int:
                raise ValueError("ttl_days must be an integer.")
            return 201, {"item": asdict(app_service.create_invite(role, chat_id, ttl_days))}
    if method == "DELETE" and resource == "/api/v1/admin/invites" and key:
        code = unquote(key)
        return 200, {"item": asdict(app_service.revoke_invite(code, chat_id))}
    return 404, {"error": "Not found"}


def _role(body: dict[str, object], roles: set[str], default: str | None = None) -> str:
    role = body.get("role", default)
    if not isinstance(role, str) or role not in roles:
        raise ValueError(f"role must be one of {', '.join(sorted(roles))}.")
    return role


def _query_route(
    path: str, params: dict[str, list[str]], app_service: ApplicationService
) -> tuple[int, dict[str, object]]:
    if path == "/api/v1/stats":
        return 200, asdict(app_service.get_index_stats())
    if path == "/api/v1/years":
        year_from = _optional_int(params.get("from", [None])[0])
        year_to = _optional_int(params.get("to", [None])[0])
        return 200, {"items": [asdict(summary) for summary in app_service.list_years(year_from, year_to)]}
    if path == "/api/v1/folders":
        query = params.get("q", [""])[0]
        limit = _bounded_limit(params.get("limit", ["10"])[0], default=10)
        return 200, {"items": [asdict(item) for item in app_service.search_folders(query, limit=limit)]}
    if path == "/api/v1/images":
        query = params.get("q", [""])[0]
        limit = _bounded_limit(params.get("limit", ["10"])[0], default=10)
        return 200, {"items": [asdict(item) for item in app_service.search_images(query, limit=limit)]}
    if path == "/api/v1/random":
        query = params.get("q", [""])[0]
        count = _bounded_limit(params.get("count", ["1"])[0], default=1)
        return 200, {"items": [asdict(item) for item in app_service.random_images(query, count=count)]}
    if path == "/api/v1/people":
        return 200, {"items": [asdict(item) for item in app_service.list_people()]}
    return 404, {"error": "Not found"}


def make_api_handler(
    app_service: ApplicationService,
    api_token: str | None = None,
    api_chat_tokens: tuple[tuple[int, str], ...] = (),
):
    class ChromantisApiHandler(BaseHTTPRequestHandler):
        server_version = "ChromantisAPI/0.1"

        def do_GET(self) -> None:  # noqa: N802
            self._handle()

        def do_POST(self) -> None:  # noqa: N802
            self._handle_with_body()

        def do_PATCH(self) -> None:  # noqa: N802
            self._handle_with_body()

        def do_DELETE(self) -> None:  # noqa: N802
            self._handle()

        def _handle_with_body(self) -> None:
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 <= size <= 16_384:
                    self._write_json(413, {"error": "Request body too large"})
                    return
                body = json.loads(self.rfile.read(size)) if size else {}
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                self._write_json(400, {"error": "Expected a JSON object"})
                return
            self._handle(body)

        def _handle(self, body: dict[str, object] | None = None) -> None:
            status, payload = _dispatch(
                self.command,
                self.path,
                app_service,
                api_token,
                api_chat_tokens,
                self.headers.get("Authorization"),
                self.headers.get("X-API-Token"),
                body,
            )
            self._write_json(status, payload)

        def log_message(self, format: str, *args) -> None:
            return

        def _write_json(self, status_code: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return ChromantisApiHandler


class ApiServer(ThreadingHTTPServer):
    daemon_threads = True


def _optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _bounded_limit(value: str, default: int) -> int:
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(1, min(parsed, 50))
