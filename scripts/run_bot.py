from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chromantis.bot.telegram_bot import TelegramBotApp, TelegramBotService
from chromantis.app import ApplicationService
from chromantis.config import AppConfig
from chromantis.db.repository import Repository
from chromantis.logging_utils import configure_logging
from chromantis.source import build_archive_source


def main() -> None:
    config = AppConfig.from_env()
    configure_logging(config.log_level)

    if not config.telegram_token:
        raise SystemExit("Missing TELEGRAM_TOKEN in .env")

    repository = Repository(config.sqlite_path)
    repository.init_schema()
    stats = repository.get_index_stats()
    authorized_chats = repository.list_authorized_chats()
    access_code = config.telegram_access_code or f"{secrets.randbelow(1_000_000):06d}"

    source = build_archive_source(config)
    app_service = ApplicationService(
        repository,
        access_code=access_code,
        static_viewer_chat_ids=config.telegram_chat_allowlist,
        static_owner_chat_ids=config.telegram_admin_chat_allowlist,
    )

    service = TelegramBotService(
        app_service,
        chat_allowlist=config.telegram_chat_allowlist,
        admin_chat_allowlist=config.telegram_admin_chat_allowlist,
        stats_provider=repository.get_index_stats,
        access_code=access_code,
        auth_checker=repository.is_chat_authorized,
        auth_granter=repository.authorize_chat,
        auth_revoker=repository.revoke_chat,
        session_loader=repository.get_chat_session,
        session_saver=repository.save_chat_session,
        session_clearer=repository.clear_chat_session,
    )
    app = TelegramBotApp(
        token=config.telegram_token,
        service=service,
        image_fetcher=source.read_bytes,
        image_batch_fetcher=source.read_many_bytes,
    ).build()

    print("Starting Chromantis Telegram bot")
    print(f"SQLite path: {config.sqlite_path}")
    print(f"Source type: {config.source_type}")
    print(f"Source root: {config.source_root}")
    print(
        f"Current index: folders={stats.folders} images={stats.images} tags={stats.tags}"
    )
    if config.telegram_chat_allowlist:
        print(f"Static viewer chats: {', '.join(str(chat_id) for chat_id in config.telegram_chat_allowlist)}")
    else:
        print("Static viewer chats: none")
    if config.telegram_admin_chat_allowlist:
        print(
            f"Static owner chats: {', '.join(str(chat_id) for chat_id in config.telegram_admin_chat_allowlist)}"
        )
    else:
        print("Static owner chats: none")
    print(f"Stored authorized chats: {len(authorized_chats)}")
    if config.telegram_access_code:
        print(f"Access code: {access_code} (from TELEGRAM_ACCESS_CODE, grants viewer access)")
    else:
        print(f"Access code: {access_code} (generated for this bot session, grants viewer access)")
        print("Use /login <access-code> from Telegram to authorize a new chat.")
    if stats.images == 0:
        print(
            "Warning: index is empty. Run "
            "'python scripts/reindex_source.py --verbose --progress-every 1 --show-skipped' first."
        )
    app.run_polling()


if __name__ == "__main__":
    main()
