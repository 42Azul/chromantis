from __future__ import annotations

import json
import os
import logging
import shlex
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        logger.debug("No .env file found at %s", path)
        return
    logger.debug("Loading environment variables from %s", path)
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def normalize_ftp_root(value: str) -> str:
    root = value.strip()
    if not root:
        raise ValueError("FTP_PHOTOS_ROOT must not be empty")
    if not root.startswith("/"):
        raise ValueError("FTP_PHOTOS_ROOT must be an absolute FTP path")
    normalized = "/" + "/".join(segment for segment in root.split("/") if segment)
    return normalized or "/"


def normalize_source_type(value: str | None) -> str:
    source_type = (value or "ftp").strip().lower()
    if source_type not in {"ftp", "local"}:
        raise ValueError("SOURCE_TYPE must be either 'ftp' or 'local'")
    return source_type


def normalize_local_root(value: str, base_dir: Path = REPO_ROOT) -> str:
    root = value.strip()
    if not root:
        raise ValueError("SOURCE_ROOT must not be empty")
    path = Path(root)
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return str(path)


def _parse_chat_allowlist(value: str | None) -> tuple[int, ...]:
    if not value:
        return ()
    chat_ids = []
    for item in value.split(","):
        stripped = item.strip()
        if not stripped:
            continue
        chat_ids.append(int(stripped))
    return tuple(chat_ids)


@dataclass(frozen=True)
class AppConfig:
    source_type: str
    source_root: str
    ftp_host: str
    ftp_port: int
    ftp_user: str
    ftp_password: str
    sqlite_path: str
    telegram_token: str | None
    telegram_chat_allowlist: tuple[int, ...]
    telegram_admin_chat_allowlist: tuple[int, ...]
    telegram_access_code: str | None
    api_bind_host: str
    api_port: int
    api_token: str | None
    log_level: str
    api_chat_tokens: tuple[tuple[int, str], ...] = ()
    api_curator_chat_ids: tuple[int, ...] = ()
    query_interpreter_command: tuple[str, ...] = ()
    query_interpreter_timeout: float = 10.0
    enrichment_search: bool = False
    thumbnail_cache_mib: int = 0

    @classmethod
    def from_env(cls, dotenv_path: str | None = None) -> "AppConfig":
        env_path = Path(dotenv_path) if dotenv_path else Path(".env")
        _load_dotenv(env_path)

        source_type = normalize_source_type(os.getenv("SOURCE_TYPE"))
        if source_type == "ftp":
            source_root = normalize_ftp_root(
                os.getenv("SOURCE_ROOT") or os.getenv("FTP_PHOTOS_ROOT", "")
            )
        else:
            source_root = normalize_local_root(
                os.getenv("SOURCE_ROOT", ""),
                base_dir=REPO_ROOT,
            )
        sqlite_path = os.getenv("SQLITE_PATH", "chromantis.db")
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()

        logger.debug(
            "Loaded config for source_type=%s host=%s root=%s sqlite_path=%s log_level=%s",
            source_type,
            os.getenv("FTP_HOST", ""),
            source_root,
            sqlite_path,
            log_level,
        )

        api_token = os.getenv("API_TOKEN") or None
        api_chat_tokens = _parse_api_chat_tokens(os.getenv("API_CHAT_TOKENS"), api_token)

        query_interpreter_command = tuple(shlex.split(os.getenv("QUERY_INTERPRETER_COMMAND", "")))
        query_interpreter_timeout = float(os.getenv("QUERY_INTERPRETER_TIMEOUT", "10"))
        if not 0 < query_interpreter_timeout <= 300:
            raise ValueError("QUERY_INTERPRETER_TIMEOUT must be in (0, 300] seconds.")

        thumbnail_cache_mib = int(os.getenv("THUMBNAIL_CACHE_MIB", "0"))
        if not 0 <= thumbnail_cache_mib <= 512:
            raise ValueError("THUMBNAIL_CACHE_MIB must be between 0 and 512.")

        return cls(
            source_type=source_type,
            source_root=source_root,
            ftp_host=os.getenv("FTP_HOST", ""),
            ftp_port=int(os.getenv("FTP_PORT", "21")),
            ftp_user=os.getenv("FTP_USER", ""),
            ftp_password=os.getenv("FTP_PASSWORD", ""),
            sqlite_path=sqlite_path,
            telegram_token=os.getenv("TELEGRAM_TOKEN") or None,
            telegram_chat_allowlist=_parse_chat_allowlist(
                os.getenv("TELEGRAM_CHAT_ALLOWLIST")
            ),
            telegram_admin_chat_allowlist=_parse_chat_allowlist(
                os.getenv("TELEGRAM_ADMIN_CHAT_ALLOWLIST")
            ),
            telegram_access_code=os.getenv("TELEGRAM_ACCESS_CODE") or None,
            api_bind_host=os.getenv("API_BIND_HOST", "127.0.0.1"),
            api_port=int(os.getenv("API_PORT", "8787")),
            api_token=api_token,
            api_chat_tokens=api_chat_tokens,
            api_curator_chat_ids=_parse_chat_allowlist(os.getenv("API_CURATOR_CHAT_IDS")),
            query_interpreter_command=query_interpreter_command,
            query_interpreter_timeout=query_interpreter_timeout,
            enrichment_search=os.getenv("ENRICHMENT_SEARCH", "false").strip().lower() == "true",
            thumbnail_cache_mib=thumbnail_cache_mib,
            log_level=log_level,
        )


def _parse_api_chat_tokens(
    value: str | None, read_token: str | None
) -> tuple[tuple[int, str], ...]:
    if not value:
        return ()
    try:
        pairs = json.loads(value)
        if not isinstance(pairs, dict):
            raise ValueError
        tokens = {}
        for key, token in pairs.items():
            chat_id = int(key)
            if not -(2**63) <= chat_id < 2**63 or chat_id == 0 or chat_id in tokens:
                raise ValueError
            if not isinstance(token, str) or not token or any(
                not 33 <= ord(char) <= 126 for char in token
            ):
                raise ValueError
            tokens[chat_id] = token
        if len(set(tokens.values())) != len(tokens) or read_token in tokens.values():
            raise ValueError
        return tuple(tokens.items())
    except (TypeError, ValueError):
        raise ValueError(
            "API_CHAT_TOKENS must be a JSON object mapping chat IDs to unique printable tokens."
        ) from None
