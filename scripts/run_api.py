from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chromantis.api import ApiServer, make_api_handler
from chromantis.app import ApplicationService
from chromantis.config import AppConfig
from chromantis.db.repository import Repository
from chromantis.logging_utils import configure_logging
from chromantis.source import build_archive_source


def main() -> None:
    config = AppConfig.from_env()
    configure_logging(config.log_level)
    repository = Repository(config.sqlite_path)
    repository.init_schema()
    app_service = ApplicationService(
        repository,
        static_viewer_chat_ids=config.telegram_chat_allowlist,
        static_owner_chat_ids=config.telegram_admin_chat_allowlist,
    )
    handler = make_api_handler(
        app_service, api_token=config.api_token, api_chat_tokens=config.api_chat_tokens,
        image_fetcher=build_archive_source(config).read_bytes,
    )
    server = ApiServer((config.api_bind_host, config.api_port), handler)
    print(f"Starting Chromantis API on http://{config.api_bind_host}:{config.api_port}")
    if config.api_token or config.api_chat_tokens:
        print("API authentication: bearer token required")
    else:
        print("API authentication: disabled (local/trusted use)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
