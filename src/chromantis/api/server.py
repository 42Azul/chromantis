from __future__ import annotations

from dataclasses import asdict
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from chromantis.app import ApplicationService


def handle_api_get(
    path: str,
    app_service: ApplicationService,
    api_token: str | None = None,
    auth_header: str | None = None,
    x_api_token: str | None = None,
) -> tuple[int, dict[str, object]]:
    parsed = urlparse(path)
    if parsed.path == "/api/v1/health":
        return 200, {"status": "ok"}
    if api_token and not _is_authorized(api_token, auth_header=auth_header, x_api_token=x_api_token):
        return 401, {"error": "Unauthorized"}
    params = parse_qs(parsed.query)
    if parsed.path == "/api/v1/stats":
        return 200, asdict(app_service.get_index_stats())
    if parsed.path == "/api/v1/years":
        year_from = _optional_int(params.get("from", [None])[0])
        year_to = _optional_int(params.get("to", [None])[0])
        return 200, {"items": [asdict(summary) for summary in app_service.list_years(year_from, year_to)]}
    if parsed.path == "/api/v1/folders":
        query = params.get("q", [""])[0]
        limit = _bounded_limit(params.get("limit", ["10"])[0], default=10)
        return 200, {"items": [asdict(item) for item in app_service.search_folders(query, limit=limit)]}
    if parsed.path == "/api/v1/images":
        query = params.get("q", [""])[0]
        limit = _bounded_limit(params.get("limit", ["10"])[0], default=10)
        return 200, {"items": [asdict(item) for item in app_service.search_images(query, limit=limit)]}
    if parsed.path == "/api/v1/random":
        query = params.get("q", [""])[0]
        count = _bounded_limit(params.get("count", ["1"])[0], default=1)
        return 200, {"items": [asdict(item) for item in app_service.random_images(query, count=count)]}
    if parsed.path == "/api/v1/people":
        return 200, {"items": [asdict(item) for item in app_service.list_people()]}
    return 404, {"error": "Not found"}


def make_api_handler(app_service: ApplicationService, api_token: str | None = None):
    class ChromantisApiHandler(BaseHTTPRequestHandler):
        server_version = "ChromantisAPI/0.1"

        def do_GET(self) -> None:  # noqa: N802
            status, payload = handle_api_get(
                self.path,
                app_service=app_service,
                api_token=api_token,
                auth_header=self.headers.get("Authorization"),
                x_api_token=self.headers.get("X-API-Token"),
            )
            self._write_json(status, payload)

        def log_message(self, format: str, *args) -> None:
            return

        def _write_json(self, status_code: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
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


def _is_authorized(
    api_token: str,
    auth_header: str | None = None,
    x_api_token: str | None = None,
) -> bool:
    if auth_header == f"Bearer {api_token}":
        return True
    return x_api_token == api_token
