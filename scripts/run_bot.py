from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chromantis.bot.telegram_bot import TelegramBotApp, TelegramBotService
from chromantis.config import AppConfig
from chromantis.db.repository import Repository
from chromantis.ftp.client import StdlibFTPClient
from chromantis.logging_utils import configure_logging
from chromantis.search.service import SearchService


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

    ftp_client = StdlibFTPClient(
        host=config.ftp_host,
        port=config.ftp_port,
        user=config.ftp_user,
        password=config.ftp_password,
    )

    service = TelegramBotService(
        SearchService(repository),
        chat_allowlist=config.telegram_chat_allowlist,
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
        image_fetcher=ftp_client.download_bytes,
        image_batch_fetcher=ftp_client.download_many_bytes,
    ).build()

    print("Starting Chromantis Telegram bot")
    print(f"SQLite path: {config.sqlite_path}")
    print(f"FTP photo root: {config.ftp_photos_root}")
    print(
        f"Current index: folders={stats.folders} images={stats.images} tags={stats.tags}"
    )
    if config.telegram_chat_allowlist:
        print(f"Allowed chats: {', '.join(str(chat_id) for chat_id in config.telegram_chat_allowlist)}")
    else:
        print("Allowed chats: dynamic auth via /login")
    print(f"Stored authorized chats: {len(authorized_chats)}")
    if config.telegram_access_code:
        print(f"Access code: {access_code} (from TELEGRAM_ACCESS_CODE)")
    else:
        print(f"Access code: {access_code} (generated for this bot session)")
        print("Use /login <access-code> from Telegram to authorize a new chat.")
    if stats.images == 0:
        print(
            "Warning: index is empty. Run "
            "'python scripts/reindex_ftp.py --verbose --progress-every 1 --show-skipped' first."
        )
    app.run_polling()


if __name__ == "__main__":
    main()
