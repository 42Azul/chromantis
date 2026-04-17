from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chromantis.config import AppConfig
from chromantis.db.repository import Repository
from chromantis.logging_utils import configure_logging


def main() -> None:
    config = AppConfig.from_env()
    configure_logging(config.log_level)
    repository = Repository(config.sqlite_path)
    repository.init_schema()
    print(f"Initialized SQLite schema at {config.sqlite_path}")


if __name__ == "__main__":
    main()
