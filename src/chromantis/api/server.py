from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from ftplib import Error as FtpError
from hmac import compare_digest
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from mimetypes import guess_type
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from chromantis.app import ApplicationService, AuthOperationError
from chromantis.app.album_review import parse_tag
from chromantis.app.browse import browse
from chromantis.db.family_access import FamilySession, SESSION_SECONDS

FAMILY_COOKIE = "chromantis_family"
FAMILY_SESSION_PATH = "/api/v1/family/session"
ALBUM_REVIEW_PATH = "/api/v1/album-review"

UI_ROOT = Path(__file__).with_name("ui")
UI_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/ui/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/ui/style.css": ("style.css", "text/css; charset=utf-8"),
}


@dataclass(frozen=True)
class PhotoPayload:
    content: bytes
    content_type: str


def handle_api_get(
    path: str,
    app_service: ApplicationService,
    api_token: str | None = None,
    auth_header: str | None = None,
    x_api_token: str | None = None,
) -> tuple[int, dict[str, object]]:
    status, payload = _dispatch("GET", path, app_service, api_token, (), auth_header, x_api_token)
    assert isinstance(payload, dict)
    return status, payload


def _dispatch(
    method: str,
    url: str,
    app_service: ApplicationService,
    api_token: str | None,
    api_chat_tokens: tuple[tuple[int, str], ...],
    auth_header: str | None,
    x_api_token: str | None,
    body: dict[str, object] | None = None,
    image_fetcher: Callable[[str], bytes] | None = None,
    deployment_info: dict[str, object] | None = None,
    family_secret: str | None = None,
) -> tuple[int, dict[str, object] | PhotoPayload]:
    try:
        parsed = urlparse(url)
    except ValueError:
        return 400, {"error": "Invalid request URL"}
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
    if auth_header or x_api_token:
        family_secret = None
    if chat_id is not None and not app_service.is_authorized_chat(chat_id):
        return 401, {"error": "Unauthorized"}
    if (family_secret is None and chat_id is None and (api_token or api_chat_tokens)
            and not (api_token and accepts(api_token))):
        return 401, {"error": "Unauthorized"}

    try:
        params = parse_qs(parsed.query)
        if family_secret is not None:
            session = app_service.family_access.resolve(family_secret) if api_token or api_chat_tokens else None
            if session is None:
                return 401, {"error": "La sesión familiar ha caducado."}
            if path == "/api/v1/auth/me" and method == "GET":
                return 200, {"item": {"first_name": session.label, "role": "viewer", "auth_mode": "family"},
                             "can_curate_albums": True}
            if path == ALBUM_REVIEW_PATH or path.startswith(ALBUM_REVIEW_PATH + "/"):
                return _album_review_route(method, path, app_service, session, body or {}, params)
            if path == "/api/v1/folders" and method == "GET":
                return _query_route(path, params, app_service)
            if path == "/api/v1/image" and method == "GET":
                return _read_image(params.get("path", [""])[0], app_service, image_fetcher)
            return 403, {"error": "El acceso familiar solo permite consultar y etiquetar álbumes."}
        if path.startswith(("/api/v1/auth/", "/api/v1/admin/")):
            if chat_id is None:
                return 401, {"error": "A chat token is required"}
            return _auth_route(
                method, path, app_service, chat_id, body or {}, params, deployment_info or {}
            )
        if path == ALBUM_REVIEW_PATH or path.startswith(ALBUM_REVIEW_PATH + "/"):
            if chat_id is None:
                return 401, {"error": "A chat token is required"}
            return _album_review_route(method, path, app_service, chat_id, body or {}, params)
        if path == "/api/v1/browse" and method in {"GET", "POST"}:
            if chat_id is None:
                return 401, {"error": "A chat token is required"}
            if method == "GET":
                return 200, browse(app_service, chat_id, "current")
            return 200, _browse_request(app_service, chat_id, body or {})
        if path == "/api/v1/searches" and method == "GET":
            if chat_id is None:
                return 401, {"error": "A chat token is required"}
            pinned = params.get("pinned", ["false"])[0]
            if pinned not in {"true", "false"}:
                raise ValueError("pinned must be true or false.")
            limit = _bounded_limit(params.get("limit", ["20"])[0], default=20)
            offset = _optional_int(params.get("offset", [None])[0]) or 0
            if not 0 <= offset < 2**63:
                raise ValueError("Invalid offset.")
            searches = app_service.repository.list_saved_searches(chat_id, pinned == "true", limit, offset)
            return 200, {"items": [asdict(search) for search in searches]}
        if method == "PATCH" and path.rpartition("/")[0] == "/api/v1/searches":
            if chat_id is None:
                return 401, {"error": "A chat token is required"}
            search_id = _positive_id(path.rpartition("/")[2])
            pinned = (body or {}).get("pinned")
            if not isinstance(pinned, bool):
                raise ValueError("pinned must be true or false.")
            search = app_service.set_search_pinned(chat_id, search_id, pinned)
            if search is None:
                return 404, {"error": "Search not found"}
            return 200, {"item": asdict(search)}
        if path == "/api/v1/interpret" and method == "POST":
            text = _text(body or {}, "text")
            return 200, {"item": asdict(app_service.interpret_text(text))}
        if path == "/api/v1/image" and method == "GET":
            return _read_image(params.get("path", [""])[0], app_service, image_fetcher)
        if method == "GET":
            result = _query_route(path, params, app_service)
            if path == "/api/v1/folders" and chat_id is not None:
                q = params.get("q", [""])[0]
                limit = _bounded_limit(params.get("limit", ["10"])[0], default=10)
                app_service.remember_search(chat_id, "folders", q, limit)
            return result
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
    params: dict[str, list[str]],
    deployment_info: dict[str, object],
) -> tuple[int, dict[str, object]]:
    if method == "GET" and path == "/api/v1/auth/me":
        principal = app_service.resolve_principal(chat_id)
        return 200, {"item": asdict(principal), "can_curate_albums": app_service.can_curate_albums(principal)}
    if path == "/api/v1/auth/preferences":
        if method == "GET":
            return 200, {"item": {"language": app_service.get_chat_language(chat_id)}}
        if method == "PATCH":
            language = _text(body, "language")
            preference = app_service.set_chat_language(chat_id, language, actor_chat_id=chat_id)
            return 200, {"item": {"language": preference.language}}
    if method == "GET" and path == "/api/v1/admin/config":
        app_service.require_admin(chat_id, "configuration_requires_admin")
        return 200, {"item": deployment_info}
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
    if path.startswith("/api/v1/admin/people"):
        return _people_admin_route(method, path, app_service, chat_id, body, params)
    return 404, {"error": "Not found"}


def _album_review_route(
    method: str,
    path: str,
    app: ApplicationService,
    actor: int | FamilySession,
    body: dict[str, object],
    params: dict[str, list[str]],
) -> tuple[int, dict[str, object]]:
    base = ALBUM_REVIEW_PATH
    app.require_album_curator(actor)
    album_path = params.get("path", [None])[0]
    if method == "GET" and path == base:
        after = _optional_int(params.get("after", [None])[0]) or 0
        if not 0 <= after < 2**63:
            raise ValueError("Álbum anterior no válido.")
        item = app.get_album_review(
            actor, after=after, reviewed=params.get("reviewed") == ["true"], path=album_path
        )
        if album_path is not None and item is None:
            return 404, {"error": "No se encuentra el álbum."}
        return 200, {"item": item}
    if method == "GET" and path == f"{base}/people":
        return 200, {"items": app.album_people_directory(actor)}
    if method == "GET" and path == f"{base}/photos" and album_path is not None:
        return 200, {"items": [asdict(item) for item in app.images_in_folder(album_path, limit=3)]}
    if method == "POST" and path == base:
        folder_id, revision = body.get("id"), body.get("revision")
        if (type(folder_id) is not int or not 1 <= folder_id < 2**63
                or type(revision) is not int or not 0 <= revision < 2**63):
            raise ValueError("Álbum o revisión no válidos.")
        decisions = body.get("decisions", {})
        if not isinstance(decisions, dict) or len(decisions) > 20:
            raise ValueError("Las decisiones de etiquetado no son válidas.")
        new_person = body.get("new_person")
        if new_person is not None and (not isinstance(new_person, str) or not 1 <= len(new_person.strip()) <= 100):
            raise ValueError("Escribe un nombre de hasta 100 caracteres.")
        app.save_album_review(
            actor, _text(body, "path"), folder_id, revision,
            add_people=_review_people(body, "add_people"), remove_people=_review_people(body, "remove_people"),
            new_person=new_person,
            decisions={key: parse_tag(value) if value is not None else None for key, value in decisions.items()},
            manual_add={parse_tag(value) for value in _review_values(body, "manual_add", limit=20)},
            manual_remove={parse_tag(value) for value in _review_values(body, "manual_remove", limit=20)},
        )
        return 200, {"saved": True}
    return 404, {"error": "Not found"}


def _review_values(body: dict[str, object], key: str, limit: int) -> list:
    values = body.get(key, [])
    if not isinstance(values, list) or len(values) > limit:
        raise ValueError("La selección es demasiado larga o no es válida.")
    return values


def _review_people(body: dict[str, object], key: str) -> set[int]:
    values = _review_values(body, key, limit=100)
    if any(type(value) is not int or not 1 <= value < 2**63 for value in values):
        raise ValueError("La selección de personas no es válida.")
    return set(values)


def _people_admin_route(
    method: str,
    path: str,
    app: ApplicationService,
    chat_id: int,
    body: dict[str, object],
    params: dict[str, list[str]],
) -> tuple[int, dict[str, object]]:
    app.require_admin(chat_id, "people_write_requires_admin")
    prefix = "/api/v1/admin/people"
    if method == "POST" and path == prefix:
        detail = app.create_person(_text(body, "display_name"), actor_chat_id=chat_id)
        return 201, {"item": asdict(detail)}
    if not path.startswith(prefix + "/"):
        return 404, {"error": "Not found"}
    identifier, _, action = path.removeprefix(prefix + "/").partition("/")
    person_id = _positive_id(identifier)
    if app.get_person_detail(person_id) is None:
        return 404, {"error": "Person not found"}
    if method == "PATCH" and not action:
        detail = app.rename_person(person_id, _text(body, "display_name"), actor_chat_id=chat_id)
    elif method == "POST" and action == "aliases":
        detail = app.add_person_alias(person_id, _text(body, "alias"), actor_chat_id=chat_id)
    elif method == "POST" and action == "folders":
        detail = app.link_person_to_folder(person_id, _text(body, "path"), actor_chat_id=chat_id)
    elif method == "DELETE" and action == "folders":
        folder = _text({"path": params.get("path", [""])[0]}, "path")
        detail = app.unlink_person_from_folder(person_id, folder, actor_chat_id=chat_id)
    else:
        return 404, {"error": "Not found"}
    return 200, {"item": asdict(detail)}


def _positive_id(identifier: str) -> int:
    value = int(identifier)
    if not 1 <= value < 2**63:
        raise ValueError("Invalid ID.")
    return value


def _text(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string.")
    return value.strip()


def _browse_request(
    app: ApplicationService, chat_id: int, body: dict[str, object]
) -> dict[str, object]:
    action = _text(body, "action")
    q, count, folder, year = (body.get(key) for key in ("q", "count", "folder", "year"))
    if q is not None and not isinstance(q, str):
        raise ValueError("q must be a string.")
    if count is not None and (type(count) is not int or not 1 <= count <= 50):
        raise ValueError("count must be an integer between 1 and 50.")
    if folder is not None and (not isinstance(folder, str) or not folder.strip()):
        raise ValueError("folder must be a non-empty string.")
    if year is not None and (type(year) is not int or not 1000 <= year <= 9999):
        raise ValueError("year must be a four-digit integer.")
    return browse(app, chat_id, action, q=q or "", count=count, folder_path=folder, year=year)


def _read_image(
    path: str, app: ApplicationService, image_fetcher: Callable[[str], bytes] | None
) -> tuple[int, dict[str, object] | PhotoPayload]:
    if not path:
        return 400, {"error": "path is required"}
    if image_fetcher is None or not app.repository.is_indexed_image(path):
        return 404, {"error": "Image not found"}
    try:
        content = image_fetcher(path)
    except (FileNotFoundError, ValueError):
        return 404, {"error": "Image no longer available"}
    except (FtpError, OSError):
        return 502, {"error": "Archive unavailable"}
    content_type = guess_type(path)[0] or "application/octet-stream"
    if not content_type.startswith("image/"):
        content_type = "application/octet-stream"
    return 200, PhotoPayload(content, content_type)


def _role(body: dict[str, object], roles: set[str], default: str | None = None) -> str:
    role = body.get("role", default)
    if not isinstance(role, str) or role not in roles:
        raise ValueError(f"role must be one of {', '.join(sorted(roles))}.")
    return role


def _query_route(
    path: str, params: dict[str, list[str]], app_service: ApplicationService
) -> tuple[int, dict[str, object]]:
    if path == "/api/v1/sync/runs":
        limit = _bounded_limit(params.get("limit", ["10"])[0], default=10)
        return 200, {"items": app_service.repository.list_sync_runs(limit)}
    if path == "/api/v1/stats":
        stats = asdict(app_service.get_index_stats())
        return 200, {**stats, "item": stats}
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
    if path.startswith("/api/v1/people/"):
        identifier = unquote(path.removeprefix("/api/v1/people/"))
        detail = app_service.get_person_detail(_positive_id(identifier))
        if detail is None:
            return 404, {"error": "Person not found"}
        return 200, {"item": asdict(detail)}
    return 404, {"error": "Not found"}


def make_api_handler(
    app_service: ApplicationService,
    api_token: str | None = None,
    api_chat_tokens: tuple[tuple[int, str], ...] = (),
    image_fetcher: Callable[[str], bytes] | None = None,
    deployment_info: dict[str, object] | None = None,
):
    class ChromantisApiHandler(BaseHTTPRequestHandler):
        server_version = "ChromantisAPI/0.1"

        def do_GET(self) -> None:  # noqa: N802
            asset = UI_FILES.get(self.path.partition("?")[0])
            if asset:
                filename, media_type = asset
                self._write(200, (UI_ROOT / filename).read_bytes(), media_type)
                return
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
            family_secret = self._family_secret()
            if self.path == FAMILY_SESSION_PATH and self.command in {"POST", "DELETE"}:
                self._handle_family_session(body or {}, family_secret)
                return
            if (family_secret is not None and self.command != "GET"
                    and not (self.headers.get("Authorization") or self.headers.get("X-API-Token"))
                    and not self._same_origin_family_request()):
                self._write_json(403, {"error": "La petición debe proceder de la web de Chromantis."})
                return
            status, payload = _dispatch(
                self.command,
                self.path,
                app_service,
                api_token,
                api_chat_tokens,
                self.headers.get("Authorization"),
                self.headers.get("X-API-Token"),
                body,
                image_fetcher,
                deployment_info,
                family_secret,
            )
            if isinstance(payload, PhotoPayload):
                self._write(status, payload.content, payload.content_type)
            else:
                self._write_json(status, payload)

        def _family_secret(self) -> str | None:
            cookies = SimpleCookie()
            try:
                cookies.load(self.headers.get("Cookie", ""))
            except CookieError:
                return None
            cookie = cookies.get(FAMILY_COOKIE)
            return cookie.value if cookie is not None else None

        def _same_origin_family_request(self) -> bool:
            host = self.headers.get("Host")
            origin = self.headers.get("Origin")
            return bool(host) and origin in {f"http://{host}", f"https://{host}"} and (
                self.command == "DELETE" or self.headers.get_content_type() == "application/json"
            )

        def _handle_family_session(self, body: dict[str, object], family_secret: str | None) -> None:
            if not self._same_origin_family_request():
                self._write_json(403, {"error": "La petición debe proceder de la web de Chromantis."})
                return
            cookie = SimpleCookie()
            if self.command == "POST":
                if not (api_token or api_chat_tokens):
                    self._write_json(403, {"error": "El acceso familiar requiere proteger primero el archivo."})
                    return
                if family_secret and app_service.family_access.resolve(family_secret):
                    self._write_json(409, {"error": "Cierra la sesión familiar actual para usar otro código."})
                    return
                secret = app_service.family_access.redeem(body.get("code"))
                if secret is None:
                    self._write_json(401, {"error": "El código es incorrecto, ya se usó o ha caducado."})
                    return
                cookie[FAMILY_COOKIE] = secret
                cookie[FAMILY_COOKIE]["max-age"] = SESSION_SECONDS
            else:
                if family_secret:
                    app_service.family_access.sign_out(family_secret)
                cookie[FAMILY_COOKIE] = ""
                cookie[FAMILY_COOKIE]["max-age"] = 0
            cookie[FAMILY_COOKIE]["path"] = "/api/v1"
            cookie[FAMILY_COOKIE]["httponly"] = True
            cookie[FAMILY_COOKIE]["samesite"] = "Strict"
            if self.headers["Origin"].startswith("https://"):
                cookie[FAMILY_COOKIE]["secure"] = True
            self._write_json(200, {"ok": True}, cookie[FAMILY_COOKIE].OutputString())

        def log_message(self, format: str, *args) -> None:
            return

        def _write_json(
            self, status_code: int, payload: dict[str, object], cookie: str | None = None
        ) -> None:
            body = json.dumps(payload, sort_keys=True).encode("utf-8")
            self._write(status_code, body, "application/json; charset=utf-8", cookie)

        def _write(self, status_code: int, body: bytes, content_type: str, cookie: str | None = None) -> None:
            self.send_response(status_code)
            self.send_header("Content-Type", content_type)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob:; "
                "connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
            )
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if cookie is not None:
                self.send_header("Set-Cookie", cookie)
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
