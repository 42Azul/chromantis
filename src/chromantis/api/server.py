from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from ftplib import Error as FtpError
from hashlib import sha256
from hmac import compare_digest
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from ipaddress import ip_address
from mimetypes import guess_type
from pathlib import Path
from secrets import token_hex
from shutil import copyfileobj
from ssl import SSLSocket
from tempfile import TemporaryFile
from threading import Lock
from typing import BinaryIO
from urllib.parse import parse_qs, unquote, urlparse
from zipfile import ZipFile

from chromantis.api.thumbnails import SOURCE_BYTES, ThumbnailCache
from chromantis.app import ApplicationService, AuthOperationError
from chromantis.app.album_review import parse_tag
from chromantis.app.browse import browse
from chromantis.app.recall import RefinementError
from chromantis.db.family_access import FamilySession, SESSION_SECONDS
from chromantis.parsing.path_parser import normalize_text
from chromantis.source.adapters import ArchiveReadLimit
from chromantis.source.scanner import ScanBusy

LOOPBACK_HOST = re.compile(r"(?:localhost|127\.0\.0\.1|\[::1\])(?::[0-9]{1,5})?", re.IGNORECASE)

FAMILY_COOKIE = "chromantis_family"
FAMILY_SESSION_PATH = "/api/v1/family/session"
ALBUM_REVIEW_PATH = "/api/v1/album-review"
ALBUM_IMAGES_PATH = "/api/v1/album-images"
CONFIRMED_IMAGES_PATH = "/api/v1/confirmed-images"
PHOTO_TAGS_PATH = "/api/v1/photo-tags"
SYNC_RUNS_PATH = "/api/v1/sync/runs"
ALBUM_SHARES_PATH = "/api/v1/album-shares"
SHARED_ALBUM_PATH = "/api/v1/shared"

PHOTO_EXPORT_PATH = "/api/v1/photo-export"
EXPORT_BYTES = 16 * 1024 * 1024
EXPORT_PHOTOS = 20
LARGE_ALBUM_BYTES = 64 * 1024 * 1024
LARGE_ALBUM_PHOTOS = 100

UI_ROOT = Path(__file__).with_name("ui")
UI_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/ui/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/ui/appearance.js": ("appearance.js", "text/javascript; charset=utf-8"),
    "/ui/style.css": ("style.css", "text/css; charset=utf-8"),
}


@dataclass(frozen=True)
class PhotoPayload:
    content: bytes | BinaryIO
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
    thumbnails: ThumbnailCache | None = None,
    start_index_scan: Callable[[], int] | None = None,
    export_reader: Callable[[str, int], bytes] | None = None,
) -> tuple[int, dict[str, object] | PhotoPayload]:
    try:
        parsed = urlparse(url)
    except ValueError:
        return 400, {"error": "Invalid request URL"}
    path = parsed.path
    if method == "GET" and path == "/api/v1/health":
        return 200, {"status": "ok"}
    if method == "GET" and path.startswith(SHARED_ALBUM_PATH + "/"):
        try:
            return _shared_album_route(path, params=parse_qs(parsed.query), app=app_service,
                                       image_fetcher=image_fetcher, thumbnails=thumbnails)
        except ValueError as error:
            return 400, {"error": str(error)}
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
        params = parse_qs(parsed.query, keep_blank_values=path in {PHOTO_TAGS_PATH, CONFIRMED_IMAGES_PATH})
        session = None
        if family_secret is not None:
            session = app_service.family_access.resolve(family_secret) if api_token or api_chat_tokens else None
            if session is None:
                return 401, {"error": "La sesión familiar ha caducado."}
        if method == "GET":
            if path == "/api/v1/image":
                return _read_image(params.get("path", [""])[0], app_service, image_fetcher)
            if path == "/api/v1/thumbnail":
                return _read_thumbnail(params.get("path", [""])[0], app_service, thumbnails)
            if path == "/api/v1/album-cover":
                return _read_album_cover(params.get("path", [""])[0], app_service, thumbnails)
            if path == "/api/v1/image-dates":
                image_path = _text({"path": params.get("path", [""])[0]}, "path")
                dates = app_service.repository.image_dates(image_path)
                return (200, {"item": dates}) if dates is not None else (404, {"error": "Image not found"})
            if path == "/api/v1/archive-status":
                status = app_service.repository.archive_index_status()
                return 200, {"item": {**status, "thumbnails": thumbnails is not None}}
        if method == "POST" and url.split("?", 1)[0] == PHOTO_EXPORT_PATH:
            if not (api_token or api_chat_tokens):
                return 401, {"error": "Photo export requires authenticated access"}
            return _export_photos(body or {}, app_service, export_reader)
        if path == "/api/v1/refine" and method == "POST":
            data = body or {}
            query = data.get("q", "")
            if not isinstance(query, str):
                raise ValueError("q must be a string.")
            result = app_service.refine_query(query, _text(data, "text"))
            return 200, {"q": result.query, "choices": [asdict(item) for item in result.choices]}
        if path == PHOTO_TAGS_PATH:
            actor = session if session is not None else chat_id
            if actor is None:
                return 401, {"error": "A chat token or family session is required"}
            return _photo_tags_route(method, app_service, actor, body or {}, params)
        if method == "POST" and path == SYNC_RUNS_PATH:
            if chat_id is None or app_service.resolve_principal(chat_id).role != "owner":
                return 403, {"error": "An owner credential is required to start an index scan."}
            if body or parsed.query:
                raise ValueError("This endpoint accepts no scan options.")
            if start_index_scan is None:
                return 503, {"error": "Manual indexing is unavailable."}
            try:
                scan_id = start_index_scan()
            except ScanBusy as exc:
                return 409, {"error": str(exc)}
            except (OSError, RuntimeError, sqlite3.Error):
                return 503, {"error": "Could not start the index scan."}
            return 202, {"item": {"id": scan_id, "status": "running"}}
        if session is not None:
            if path == "/api/v1/auth/me" and method == "GET":
                return 200, {"item": {"first_name": session.label, "role": "viewer", "auth_mode": "family"},
                             "can_curate_albums": True}
            if path == ALBUM_REVIEW_PATH or path.startswith(ALBUM_REVIEW_PATH + "/"):
                return _album_review_route(method, path, app_service, session, body or {}, params)
            if method == "GET" and path in {
                "/api/v1/folders", "/api/v1/years", "/api/v1/album-tags", "/api/v1/photo-tag-catalog", ALBUM_IMAGES_PATH, CONFIRMED_IMAGES_PATH,
            }:
                return _query_route(path, params, app_service)
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
        if path == "/api/v1/collections" or path.startswith("/api/v1/collections/"):
            if chat_id is None:
                return 401, {"error": "A chat token is required"}
            return _collection_route(method, path, app_service, chat_id, body or {})
        if path == ALBUM_SHARES_PATH or path.startswith(ALBUM_SHARES_PATH + "/"):
            if chat_id is None:
                return 401, {"error": "A chat token is required"}
            return _album_share_route(method, path, app_service, chat_id, body or {}, params)
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
        if method == "GET":
            result = _query_route(path, params, app_service)
            if (path == "/api/v1/folders" and chat_id is not None
                    and not {"sort", "place", "date_from", "date_to", "offset"} & params.keys()):
                q = params.get("q", [""])[0]
                limit = _bounded_limit(params.get("limit", ["10"])[0], default=10)
                app_service.remember_search(chat_id, "folders", q, limit)
            return result
        return 404, {"error": "Not found"}
    except AuthOperationError as exc:
        return exc.status, {"error": str(exc), "code": exc.code}
    except RefinementError as exc:
        return 400, {"error": str(exc), "code": exc.code}
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


def _collection_route(
    method: str, path: str, app: ApplicationService, chat_id: int, body: dict[str, object],
) -> tuple[int, dict[str, object]]:
    suffix = path.removeprefix("/api/v1/collections")
    try:
        with app.owner_collections(chat_id, write=method in {"POST", "DELETE"}) as collections:
            if not suffix and method == "GET":
                return 200, {"items": collections.list()}
            if not suffix and method == "POST":
                collection_id = collections.create(_text(body, "name"))
                if "entry" in body:
                    kind, entry_path = _collection_entry(body["entry"])
                    return 201, {"item": collections.add(collection_id, kind, entry_path)}
                return 201, {"item": collections.get(collection_id)}
            parts = suffix.removeprefix("/").split("/")
            collection_id = _positive_id(parts[0])
            if len(parts) == 1 and method == "GET":
                return 200, {"item": collections.get(collection_id)}
            if len(parts) == 1 and method == "DELETE":
                collections.delete(collection_id)
                return 200, {"deleted": True}
            if parts[1:] == ["entries"] and method == "POST":
                kind, entry_path = _collection_entry(body)
                return 200, {"item": collections.add(collection_id, kind, entry_path)}
            if len(parts) == 3 and parts[1] == "entries" and method == "DELETE":
                collections.remove(collection_id, _positive_id(parts[2]))
                return 200, {"deleted": True}
    except LookupError as error:
        return 404, {"error": str(error)}
    return 404, {"error": "Not found"}


def _collection_entry(entry: object) -> tuple[str, str]:
    if not isinstance(entry, dict):
        raise ValueError("entry must describe an indexed photo or album.")
    path = entry.get("path")
    if not isinstance(path, str) or not path.strip() or len(path) > 4096:
        raise ValueError("Choose a photo or album from the index.")
    return _text(entry, "kind"), path


def _album_share_route(
    method: str, path: str, app: ApplicationService, chat_id: int,
    body: dict[str, object], params: dict[str, list[str]],
) -> tuple[int, dict[str, object]]:
    suffix = path.removeprefix(ALBUM_SHARES_PATH)
    try:
        with app.owner_album_shares(chat_id, write=method in {"POST", "DELETE"}) as shares:
            if not suffix and method == "GET":
                album_path = params.get("path", [None])[0]
                return 200, {"items": shares.list(album_path)}
            if not suffix and method == "POST":
                item, secret = shares.create(_text(body, "path"), body.get("ttl_days", 7))
                return 201, {"item": {**item, "url": f"/share/{secret}"}}
            share_id = _positive_id(suffix.removeprefix("/"))
            if method == "DELETE":
                shares.revoke(share_id)
                return 200, {"deleted": True}
    except LookupError as error:
        return 404, {"error": str(error)}
    return 404, {"error": "Not found"}


def _shared_album_route(
    path: str, params: dict[str, list[str]], app: ApplicationService,
    image_fetcher: Callable[[str], bytes] | None, thumbnails: ThumbnailCache | None,
) -> tuple[int, dict[str, object] | PhotoPayload]:
    parts = path.removeprefix(SHARED_ALBUM_PATH + "/").split("/")
    secret = parts[0]
    with app.album_share(secret) as (shares, share):
        if share is None:
            return 404, {"error": "This album link is invalid, expired, or revoked."}
        if len(parts) == 1:
            limit = _bounded_limit(params.get("limit", ["30"])[0], default=30)
            offset = _optional_int(params.get("offset", ["0"])[0]) or 0
            if not 0 <= offset < 2**63:
                raise ValueError("Invalid offset.")
            items = shares.images(share, limit, offset)
            return 200, {
                "item": {
                    key: share[key]
                    for key in ("title", "event_date", "year", "place", "note", "expires_at")
                },
                "items": items,
                "offset": offset,
                "has_more": len(items) == limit,
                "thumbnails": thumbnails is not None,
            }
        image_path = params.get("path", [""])[0]
        if not shares.contains_image(share, image_path):
            return 404, {"error": "Image not found in this shared album."}
        if parts[1:] == ["image"]:
            return _read_image(image_path, app, image_fetcher)
        if parts[1:] == ["thumbnail"]:
            return _read_thumbnail(image_path, app, thumbnails)
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
    if path == f"{base}/batch" and method == "GET":
        limit = _bounded_limit(params.get("limit", ["50"])[0], default=50)
        return 200, {"groups": app.get_album_review_batch(actor, limit)}
    if path == f"{base}/batch" and method == "POST":
        app.save_album_review_batch(actor, _batch_review_entries(body))
        return 200, {"saved": True}
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
    if method == "PATCH" and path == f"{base}/context":
        folder_id, revision = _album_revision(body)
        changes = body.get("changes")
        if not isinstance(changes, dict):
            raise ValueError("Los detalles del álbum no son válidos.")
        item = app.edit_album_context(actor, _text(body, "path"), folder_id, revision, changes)
        return 200, {"item": item}
    if method == "POST" and path == base:
        folder_id, revision = _album_revision(body)
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


def _album_revision(body: dict[str, object]) -> tuple[int, int]:
    folder_id, revision = body.get("id"), body.get("revision")
    if (type(folder_id) is not int or not 1 <= folder_id < 2**63
            or type(revision) is not int or not 0 <= revision < 2**63):
        raise ValueError("Álbum o revisión no válidos.")
    return folder_id, revision


def _photo_tags_route(
    method: str, app: ApplicationService, actor: int | FamilySession,
    body: dict[str, object], params: dict[str, list[str]],
) -> tuple[int, dict[str, object]]:
    if method == "GET":
        paths = params.get("path", [])
        if not 1 <= len(paths) <= 50 or len(set(paths)) != len(paths):
            raise ValueError("Select between 1 and 50 distinct indexed photo paths.")
        return 200, {"items": app.get_photo_tags(actor, [_photo_path(path) for path in paths])}
    if method == "PATCH":
        if body.keys() - {"photos", "add_people", "remove_people", "manual_add", "manual_remove"}:
            raise ValueError("Unexpected photo tag fields.")
        selections = _review_values(body, "photos", limit=50)
        photos = {}
        for selection in selections:
            if not isinstance(selection, dict) or selection.keys() != {"path", "identity"}:
                raise ValueError("Each photo requires a path and identity.")
            path = _photo_path(selection["path"])
            identity = selection["identity"]
            if path in photos or not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{32}", identity):
                raise ValueError("Each photo requires a distinct path and a valid identity.")
            photos[path] = identity
        manual_add = _review_values(body, "manual_add", limit=20)
        manual_remove = _review_values(body, "manual_remove", limit=20)
        if any(not isinstance(tag, str) for tag in manual_add + manual_remove):
            raise ValueError("Manual tags must be strings.")
        items = app.save_photo_tags(
            actor, photos, add_people=_review_people(body, "add_people"),
            remove_people=_review_people(body, "remove_people"),
            manual_add=set(manual_add), manual_remove=set(manual_remove),
        )
        return 200, {"items": items}
    return 404, {"error": "Not found"}


def _photo_path(value: object) -> str:
    if isinstance(value, str) and value.strip() and len(value) <= 4096:
        return value
    raise ValueError("A photo path must be a non-empty indexed path of at most 4096 characters.")


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


def _batch_review_entries(body: dict[str, object]) -> list[dict[str, object]]:
    values = body.get("items")
    if not isinstance(values, list) or not 1 <= len(values) <= 50:
        raise ValueError("El lote debe contener entre 1 y 50 decisiones.")
    entries = []
    for value in values:
        if not isinstance(value, dict):
            raise ValueError("Las decisiones del lote no son válidas.")
        folder_id, revision = _album_revision(value)
        decision = value.get("decision")
        if not isinstance(decision, str) or decision not in {"accepted", "corrected", "rejected"}:
            raise ValueError("Elige aceptar, corregir o rechazar cada sugerencia del lote.")
        entries.append({
            "id": folder_id,
            "path": _text(value, "path"),
            "revision": revision,
            "label": parse_tag(value.get("label")),
            "decision": decision,
            **({"tag": parse_tag(value.get("tag"))} if decision == "corrected" else {}),
        })
    return entries


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


def _export_photos(
    data: dict[str, object], app: ApplicationService, reader: Callable[[str, int], bytes] | None,
) -> tuple[int, dict[str, object] | PhotoPayload]:
    multipart = set(data) == {"paths", "format"} and data["format"] == "multipart"
    large_album = set(data) == {"album", "large"} and data["large"] is True
    if set(data) == {"album"} or large_album:
        max_photos = LARGE_ALBUM_PHOTOS if large_album else EXPORT_PHOTOS
        album = data["album"]
        if not isinstance(album, str) or not album.strip() or len(album) > 4096:
            raise ValueError("album must be a non-empty indexed album path of at most 4096 characters.")
        items = app.images_in_folder(album, limit=max_photos + 1)
        if not items:
            return 404, {"error": "Album has no indexed photos"}
        if len(items) > max_photos:
            return 413, {"error": f"Album exceeds the {max_photos} photo export limit"}
        paths = [item.path for item in items]
    else:
        paths = data.get("paths")
        if ((not multipart and set(data) != {"paths"}) or not isinstance(paths, list) or not 1 <= len(paths) <= EXPORT_PHOTOS
                or any(not isinstance(path, str) or not path for path in paths)):
            return 400, {"error": f"Select between 1 and {EXPORT_PHOTOS} indexed photos"}
        paths = list(dict.fromkeys(paths))
    if reader is None:
        return 503, {"error": "Photo export is unavailable"}
    if any(not app.repository.is_indexed_image(path) for path in paths):
        return 404, {"error": "Image not found"}

    boundary = token_hex(24) if multipart else None

    def originals():
        remaining = LARGE_ALBUM_BYTES if large_album else EXPORT_BYTES
        for path in paths:
            content = reader(path, min(remaining, EXPORT_BYTES))
            remaining -= len(content)
            yield path, content

    try:
        with ExitStack() as staging:
            buffer = staging.enter_context(TemporaryFile() if large_album else BytesIO())
            if boundary:
                for path, content in originals():
                    buffer.write(
                        (f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="photo"\r\n'
                         f"Content-Type: {_image_content_type(path)}\r\n\r\n").encode("ascii")
                    )
                    buffer.write(content)
                    buffer.write(b"\r\n")
                buffer.write(f"--{boundary}--\r\n".encode("ascii"))
            else:
                with ZipFile(buffer, "w") as archive:
                    for number, (path, content) in enumerate(originals(), start=1):
                        name = path.replace("\\", "/").rsplit("/", 1)[-1]
                        archive.writestr(f"{number:02d}-{name}", content)
            content_type = f"multipart/form-data; boundary={boundary}" if boundary else "application/zip"
            if large_album:
                staging.pop_all()  # The response writer owns the completed temporary file.
                return 200, PhotoPayload(buffer, content_type)
            return 200, PhotoPayload(buffer.getvalue(), content_type)
    except ArchiveReadLimit:
        return 413, {"error": ("Album exceeds 64 MiB total or 16 MiB per photo" if large_album
                               else "Selection exceeds the 16 MiB export limit")}
    except (FileNotFoundError, ValueError):
        return 404, {"error": "Image no longer available"}
    except (FtpError, OSError, EOFError):
        return 502, {"error": "Could not read or prepare photo export"}


def _image_content_type(path: str) -> str:
    content_type = guess_type(path)[0] or ""
    return content_type if content_type.startswith("image/") else "application/octet-stream"


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
    except (FtpError, OSError, EOFError):
        return 502, {"error": "Archive unavailable"}
    return 200, PhotoPayload(content, _image_content_type(path))


def _read_thumbnail(
    path: str, app: ApplicationService, thumbnails: ThumbnailCache | None,
) -> tuple[int, dict[str, object] | PhotoPayload]:
    if not path:
        return 400, {"error": "path is required"}
    if thumbnails is None:
        return 404, {"error": "Thumbnails are disabled"}
    fingerprint = app.repository.indexed_image_fingerprint(path)
    if fingerprint is None:
        return 404, {"error": "Image not found"}
    try:
        return 200, PhotoPayload(thumbnails.get(path, fingerprint), "image/jpeg")
    except ValueError:
        return 422, {"error": "Preview unavailable"}
    except FileNotFoundError:
        return 404, {"error": "Image no longer available"}
    except (FtpError, OSError, EOFError):
        return 502, {"error": "Archive unavailable"}


def _read_album_cover(
    path: str, app: ApplicationService, thumbnails: ThumbnailCache | None,
) -> tuple[int, dict[str, object] | PhotoPayload]:
    if not path.strip() or len(path) > 4096:
        return 400, {"error": "path must be a non-empty indexed album path of at most 4096 characters."}
    if thumbnails is None:
        return 404, {"error": "Thumbnails are disabled"}

    candidates = app.repository.cover_candidate_paths(path, max_bytes=SOURCE_BYTES, limit=12)
    # A stable shuffle of a bounded window avoids scanning the whole album per card.
    candidates.sort(key=lambda path: sha256(path.encode()).digest())
    for candidate in candidates[:3]:
        status, payload = _read_thumbnail(candidate, app, thumbnails)
        if status in {200, 502}:
            return status, payload
    return 404, {"error": "No album cover available"}


def _role(body: dict[str, object], roles: set[str], default: str | None = None) -> str:
    role = body.get("role", default)
    if not isinstance(role, str) or role not in roles:
        raise ValueError(f"role must be one of {', '.join(sorted(roles))}.")
    return role


def _query_route(
    path: str, params: dict[str, list[str]], app_service: ApplicationService
) -> tuple[int, dict[str, object]]:
    if path == SYNC_RUNS_PATH:
        limit = _bounded_limit(params.get("limit", ["10"])[0], default=10)
        return 200, {"items": app_service.repository.list_sync_runs(limit)}
    if path == "/api/v1/stats":
        stats = asdict(app_service.get_index_stats())
        return 200, {**stats, "item": stats}
    if path == "/api/v1/years":
        year_from = _optional_int(params.get("from", [None])[0])
        year_to = _optional_int(params.get("to", [None])[0])
        return 200, {"items": [asdict(summary) for summary in app_service.list_years(year_from, year_to)]}
    if path in {"/api/v1/album-tags", "/api/v1/photo-tag-catalog"}:
        limit = _bounded_limit(params.get("limit", ["20"])[0], default=20)
        offset = _optional_int(params.get("offset", [None])[0]) or 0
        if not 0 <= offset < 2**63 - limit - 1:
            raise ValueError("Invalid offset.")
        catalog = app_service.album_tags if path == "/api/v1/album-tags" else app_service.photo_tags
        items = catalog(limit=limit + 1, offset=offset)
        return 200, {"items": items[:limit], "next_offset": offset + limit if len(items) > limit else None}
    if path == "/api/v1/folders":
        query = params.get("q", [""])[0]
        limit = _bounded_limit(params.get("limit", ["10"])[0], default=10)
        order = params.get("sort", ["default"])[0]
        if order not in {"default", "timeline"}:
            raise ValueError("sort must be default or timeline.")
        offset = _optional_int(params.get("offset", [None])[0]) or 0
        if not 0 <= offset < 2**63 - limit:
            raise ValueError("Invalid offset.")
        filters = app_service.album_search_filters(query) if params.get("filters") == ["1"] else None
        raw_tag = params.get("tag", [None])[0]
        if raw_tag is not None and not 1 <= len(raw_tag.strip()) <= 4096:
            raise ValueError("Invalid album tag.")
        tag = None if raw_tag is None else raw_tag if re.fullmatch(r"[0-9]{4}-[0-9]{2}", raw_tag) else normalize_text(raw_tag)
        items = app_service.search_folders(
            filters["q"] if filters else query, limit=limit, offset=offset, chronological=order == "timeline",
            place=params.get("place", [""])[0], date_from=params.get("date_from", [None])[0],
            date_to=params.get("date_to", [None])[0],
            tag=tag,
        )
        payload = {"items": [asdict(item) for item in items]}
        if filters is not None:
            payload["filters"] = filters
        return 200, payload
    if path == "/api/v1/images":
        query = params.get("q", [""])[0]
        limit = _bounded_limit(params.get("limit", ["10"])[0], default=10)
        return 200, {"items": [asdict(item) for item in app_service.search_images(query, limit=limit)]}
    if path == CONFIRMED_IMAGES_PATH:
        tags = params.get("tag", [])
        identifiers = params.get("person", []) + params.get("person_id", [])
        if len(tags) > 1 or len(identifiers) > 1 or not (identifiers or tags):
            raise ValueError("Provide one person name, alias or person_id, and/or one manual tag.")
        if identifiers and not 1 <= len(identifiers[0].strip()) <= 100:
            raise ValueError("Provide a non-empty person name or alias of at most 100 characters.")
        limit = _bounded_limit(params.get("limit", ["30"])[0], default=30)
        offset = _optional_int(params.get("offset", [None])[0]) or 0
        if not 0 <= offset < 2**63 - limit:
            raise ValueError("Invalid offset.")
        if tags and not identifiers:
            items = app_service.search_manually_tagged_images(tags[0], limit=limit + 1, offset=offset)
        else:
            person = _positive_id(identifiers[0]) if "person_id" in params else identifiers[0]
            items = app_service.search_confirmed_images(
                person, limit=limit + 1, offset=offset, tag=tags[0] if tags else None,
            )
        return 200, {
            "items": [asdict(item) for item in items[:limit]],
            "next_offset": offset + limit if len(items) > limit else None,
        }
    if path == ALBUM_IMAGES_PATH:
        album_path = params.get("path", [""])[0]
        if not album_path.strip() or len(album_path) > 4096:
            raise ValueError("path must be a non-empty indexed album path of at most 4096 characters.")
        limit = _bounded_limit(params.get("limit", ["30"])[0], default=30)
        offset = _optional_int(params.get("offset", [None])[0]) or 0
        if not 0 <= offset < 2**63 - limit:
            raise ValueError("Invalid offset.")
        items = app_service.images_in_folder(album_path, limit=limit + 1, offset=offset)
        return 200, {
            "items": [asdict(item) for item in items[:limit]],
            "next_offset": offset + limit if len(items) > limit else None,
        }
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
    thumbnails: ThumbnailCache | None = None,
    start_index_scan: Callable[[], int] | None = None,
    *,
    trust_local_proxy: bool = False,
    export_reader: Callable[[str, int], bytes] | None = None,
):
    export_lock = Lock()

    class ChromantisApiHandler(BaseHTTPRequestHandler):
        server_version = "ChromantisAPI/0.1"

        def parse_request(self) -> bool:
            if not super().parse_request():
                return False
            hosts = self.headers.get_all("Host", [])
            loopback_peer = ip_address(self.client_address[0]).is_loopback
            forwarded = self.headers.get_all("X-Forwarded-Proto")
            secure = isinstance(self.connection, SSLSocket) or (
                trust_local_proxy and loopback_peer and forwarded == ["https"]
            )
            protected_https = secure and bool(api_token or api_chat_tokens)
            local_http = (
                not secure and forwarded is None and loopback_peer
                and len(hosts) == 1 and LOOPBACK_HOST.fullmatch(hosts[0]) is not None
            )
            if len(hosts) != 1 or not (protected_https or local_http):
                self.close_connection = True
                self._write_json(403, {
                    "error": "Usa HTTPS con autenticación de API o un túnel SSH a localhost.",
                    "code": "private_transport_required",
                })
                return False
            self.external_scheme = "https" if secure else "http"
            return True

        def do_GET(self) -> None:  # noqa: N802
            request_path = self.path.partition("?")[0]
            asset = UI_FILES.get(request_path)
            if asset is None and request_path.startswith("/share/"):
                asset = UI_FILES["/"]
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
            if self.command == "POST" and self.path.split("?", 1)[0] == PHOTO_EXPORT_PATH:
                if not export_lock.acquire(blocking=False):
                    self._write_json(503, {"error": "A photo export is already running"})
                    return
                try:
                    self._dispatch_response(body, family_secret)
                finally:
                    export_lock.release()
                return
            self._dispatch_response(body, family_secret)

        def _dispatch_response(self, body: dict[str, object] | None, family_secret: str | None) -> None:
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
                thumbnails,
                start_index_scan,
                export_reader,
            )
            if isinstance(payload, PhotoPayload):
                if isinstance(payload.content, bytes):
                    self._write(status, payload.content, payload.content_type)
                else:
                    with payload.content as file:
                        self._write(status, file, payload.content_type)
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
            return bool(host) and self.headers.get_all("Origin") == [f"{self.external_scheme}://{host}"] and (
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
            if self.external_scheme == "https":
                cookie[FAMILY_COOKIE]["secure"] = True
            self._write_json(200, {"ok": True}, cookie[FAMILY_COOKIE].OutputString())

        def log_message(self, format: str, *args) -> None:
            return

        def _write_json(
            self, status_code: int, payload: dict[str, object], cookie: str | None = None
        ) -> None:
            body = json.dumps(payload, sort_keys=True).encode("utf-8")
            self._write(status_code, body, "application/json; charset=utf-8", cookie)

        def _write(
            self, status_code: int, body: bytes | BinaryIO, content_type: str, cookie: str | None = None,
        ) -> None:
            if isinstance(body, bytes):
                length = len(body)
            else:
                length = body.tell()
                body.seek(0)
            self.send_response(status_code)
            self.send_header("Content-Type", content_type)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob:; "
                "connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
            )
            if content_type == "application/zip":
                self.send_header("Content-Disposition", 'attachment; filename="chromantis-photos.zip"')
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            if cookie is not None:
                self.send_header("Set-Cookie", cookie)
            try:
                self.end_headers()
                if isinstance(body, bytes):
                    self.wfile.write(body)
                else:
                    copyfileobj(body, self.wfile)
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True

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
