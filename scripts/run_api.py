from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chromantis.api import ApiServer, make_api_handler
from chromantis.api.thumbnails import build_thumbnail_cache
from chromantis.app import ApplicationService, CommandQueryInterpreter
from chromantis.config import AppConfig
from chromantis.db.repository import Repository
from chromantis.logging_utils import configure_logging
from chromantis.source import build_archive_source


def main() -> None:
    config = AppConfig.from_env()
    configure_logging(config.log_level)
    repository = Repository(config.sqlite_path)
    repository.init_schema()
    interpreter = None
    if config.query_interpreter_command:
        interpreter = CommandQueryInterpreter(
            config.query_interpreter_command, config.query_interpreter_timeout
        )
    app_service = ApplicationService(
        repository,
        static_viewer_chat_ids=config.telegram_chat_allowlist,
        static_owner_chat_ids=config.telegram_admin_chat_allowlist,
        interpreter=interpreter,
        include_enrichment=config.enrichment_search,
        curator_chat_ids=config.api_curator_chat_ids,
    )
    source = build_archive_source(config)
    handler = make_api_handler(
        app_service, api_token=config.api_token, api_chat_tokens=config.api_chat_tokens,
        image_fetcher=source.read_bytes,
        thumbnails=build_thumbnail_cache(config.sqlite_path, config.thumbnail_cache_mib, source),
        deployment_info={
            "source_type": config.source_type,
            "enrichment_search": config.enrichment_search,
            "query_interpreter": "local command" if interpreter else "rules",
        },
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
