from __future__ import annotations

import os
import logging
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
    log_level: str

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
            log_level=log_level,
        )
