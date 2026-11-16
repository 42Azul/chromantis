from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chromantis.config import AppConfig
from chromantis.db.repository import Repository
from chromantis.logging_utils import configure_logging
from chromantis.parsing.path_parser import PathParser
from chromantis.source import MAX_SCAN_DEPTH, ArchiveScanner, build_archive_source
from chromantis.source.scanner import ScanBusy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reindex Chromantis from the configured archive source."
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Update changed and new images using archive size and modification time.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose debug output, including per-file indexing logs.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=100,
        help="Print scan progress every N processed entries. Use 1 for very chatty output.",
    )
    parser.add_argument(
        "--show-skipped",
        action="store_true",
        help="Print skipped invalid paths at the end of the run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = AppConfig.from_env()
    log_level = "DEBUG" if args.verbose else config.log_level
    configure_logging(log_level)
    repository = Repository(config.sqlite_path)
    repository.init_schema()

    source = build_archive_source(config)
    scanner = ArchiveScanner(source=source, repository=repository, parser=PathParser())
    print(f"Reindexing source type: {config.source_type}")
    print(f"Source root: {config.source_root}")
    print(f"SQLite path: {config.sqlite_path}")
    print(f"Log level: {log_level}")
    print(
        "Traversal depth: "
        f"{MAX_SCAN_DEPTH} directories below root "
        "(root/year/folder/image only)"
    )
    try:
        result = scanner.scan(progress_every=args.progress_every, incremental=args.incremental)
    except ScanBusy as exc:
        raise SystemExit(str(exc)) from None
    print(f"Scan status: {result.status}")
    print(result.summary)
    if args.show_skipped and result.skipped_paths:
        print("Skipped paths:")
        for path in result.skipped_paths:
            print(f"- {path}")
    elif result.skipped_paths:
        print(
            f"Skipped invalid paths: {len(result.skipped_paths)} "
            f"(run with --show-skipped to print them)"
        )


if __name__ == "__main__":
    main()
