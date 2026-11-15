"""Configure a NAS deployment and enroll the Telegram owner."""

from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import sys
from tempfile import NamedTemporaryFile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

TOKEN_RE = re.compile(r"[0-9]+:[A-Za-z0-9_-]+")
YEAR_RE = re.compile(r"[0-9]{4}(?:\([0-9]+\))?")


class SetupError(Exception):
    pass


def read_env(path: Path) -> dict[str, str]:
    settings = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.lstrip().startswith("#"):
                settings.setdefault(key.strip(), value.strip().strip("'").strip('"'))
    return settings


def update_env(path: Path, settings: dict[str, str]) -> None:
    path = path.resolve()
    old_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    lines = []
    for line in old_lines:
        key = line.partition("=")[0].strip()
        if key not in settings:
            lines.append(line)
    lines.extend(f"{key}={value}" for key, value in settings.items())
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        try:
            tmp.write("\n".join(lines) + "\n")
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path.replace(path)
        finally:
            tmp_path.unlink(missing_ok=True)


def telegram_request(token: str, method: str, **parameters):
    data = urlencode(parameters).encode()
    try:
        with urlopen(f"https://api.telegram.org/bot{token}/{method}", data=data, timeout=12) as response:
            payload = json.load(response)
    except HTTPError as exc:
        hints = {
            401: "Telegram rechazó el token. Revisa el token nuevo en BotFather.",
            409: "Telegram ya tiene otra sesión de recepción. Detén la otra instancia o introduce el ID del chat.",
        }
        raise SetupError(hints.get(exc.code, f"Telegram devolvió HTTP {exc.code}.")) from None
    except (URLError, TimeoutError, ValueError):
        raise SetupError("No se pudo verificar el bot con Telegram desde este NAS.") from None
    if not payload.get("ok"):
        raise SetupError("Telegram no aceptó la petición.")
    return payload["result"]


def find_owner(updates: list[dict], challenge: str) -> int | None:
    for update in updates:
        message = update.get("message", {})
        chat = message.get("chat", {})
        if chat.get("type") == "private" and message.get("text") == f"/start {challenge}":
            return chat["id"]
    return None


def enroll_owner(token: str, username: str) -> int:
    challenge = secrets.token_urlsafe(16)
    print(f"Abre https://t.me/{username}?start={challenge} y pulsa Iniciar.")
    print(f"También puedes enviar /start {challenge} al bot por privado.")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        updates = telegram_request(token, "getUpdates")
        owner = find_owner(updates, challenge)
        if owner is not None:
            return owner
        time.sleep(2)
    raise SetupError("No llegó la confirmación. Reintenta o indica CHROMANTIS_OWNER_CHAT_ID al lanzar el script.")


def has_year_folders(root: Path) -> bool:
    return root.is_dir() and any(
        entry.is_dir() and YEAR_RE.fullmatch(entry.name) for entry in root.iterdir()
    )


def local_archive() -> str:
    value = os.environ.get("CHROMANTIS_PHOTOS", "").strip()
    if not value:
        value = input("Ruta de las fotos en el NAS (la que contiene las carpetas por año): ").strip()
    if not value:
        raise SetupError("Indica la ruta al archivo de fotos.")
    root = Path(value).expanduser().resolve()
    if not has_year_folders(root):
        raise SetupError("La ruta debe contener carpetas por año, por ejemplo 2021 o 2024.")
    return str(root)


def main(rotate_token: bool = False, path: Path = Path(".env")) -> None:
    existing = read_env(path)
    changed = {}
    source_type = existing.get("SOURCE_TYPE", "ftp")
    source_root = existing.get("SOURCE_ROOT") or existing.get("FTP_PHOTOS_ROOT")
    if not source_root or (source_type == "ftp" and existing.get("FTP_HOST") == "ftp.example.com"):
        changed.update(SOURCE_TYPE="local", SOURCE_ROOT=local_archive())
    elif source_type == "local":
        root = Path(source_root)
        if not has_year_folders(root):
            raise SetupError("La ruta local de .env debe estar montada y contener carpetas por año.")

    previous_token = existing.get("TELEGRAM_TOKEN", "")
    token = previous_token
    owners = existing.get("TELEGRAM_ADMIN_CHAT_ALLOWLIST", "").strip(", ")
    manual_owner = os.environ.get("CHROMANTIS_OWNER_CHAT_ID", "").strip()
    owner = None
    if manual_owner or owners:
        owner = int(manual_owner or owners.split(",")[0])
    if rotate_token or not token:
        if not sys.stdin.isatty():
            raise SetupError("Ejecuta la configuración en un terminal interactivo para pegar el token.")
        token = getpass.getpass("Token de Telegram: ").strip()
    if not TOKEN_RE.fullmatch(token):
        raise SetupError("Introduce un token válido con bash scripts/setup_nas.sh --rotate-token.")
    if token != previous_token or owner is None:
        bot = telegram_request(token, "getMe")
        print(f"Telegram ha verificado @{bot['username']}.")
        if owner is None:
            owner = enroll_owner(token, bot["username"])
    if token != previous_token:
        changed["TELEGRAM_TOKEN"] = token

    if not 1 <= owner < 2**63:
        raise SetupError("Indica el ID numérico de tu chat privado con el bot.")
    all_owners = dict.fromkeys([*(int(chat) for chat in owners.split(",") if chat.strip()), owner])
    changed["TELEGRAM_ADMIN_CHAT_ALLOWLIST"] = ",".join(map(str, all_owners))
    tokens = json.loads(existing.get("API_CHAT_TOKENS") or "{}")
    if not isinstance(tokens, dict):
        raise SetupError("API_CHAT_TOKENS debe ser un objeto JSON.")
    tokens.setdefault(str(owner), secrets.token_urlsafe(32))
    changed["API_CHAT_TOKENS"] = json.dumps(tokens, separators=(",", ":"))
    for key, value in {"SQLITE_PATH": "./data/chromantis.db", "API_BIND_HOST": "127.0.0.1", "API_PORT": "8787"}.items():
        if not existing.get(key):
            changed[key] = value
    if any(existing.get(key) != value for key, value in changed.items()):
        update_env(path, changed)
    else:
        path.chmod(0o600)
    print(f"Configurado el chat propietario {owner}. El token web está en API_CHAT_TOKENS dentro de .env.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rotate-token", action="store_true")
    args = parser.parse_args()
    try:
        main(rotate_token=args.rotate_token)
    except SetupError as error:
        raise SystemExit(str(error)) from None
    except (OSError, ValueError, EOFError):
        raise SystemExit("La configuración no es válida. Revisa la ruta, el ID de chat y los valores de .env.") from None
