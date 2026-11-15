from pathlib import Path
import argparse
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chromantis.app.enrichment import CommandImageEnricher, enrich_images
from chromantis.config import AppConfig
from chromantis.db.repository import Repository
from chromantis.logging_utils import configure_logging
from chromantis.source import build_archive_source


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich indexed photos with a local adapter command.")
    parser.add_argument("--command", required=True, help="Executable and arguments, with no shell expansion.")
    parser.add_argument("--model", required=True, help="Model or pipeline name to record.")
    parser.add_argument("--version", required=True, help="Model or pipeline version to record.")
    parser.add_argument("--limit", type=int, default=25, help="Maximum photos to process in this run.")
    parser.add_argument("--album", help="Process only this exact indexed album path, relative to the archive.")
    parser.add_argument("--timeout", type=float, default=60, help="Timeout in seconds per photo.")
    args = parser.parse_args()
    command = tuple(shlex.split(args.command))
    if not command or not args.model.strip() or not args.version.strip():
        parser.error("command, model and version are required")
    if args.limit < 1 or not 0 < args.timeout <= 3600:
        parser.error("limit must be positive and timeout must be in (0, 3600] seconds")
    if args.album is not None and not args.album.strip():
        parser.error("--album must be an indexed relative path")
    config = AppConfig.from_env()
    configure_logging(config.log_level)
    repository = Repository(config.sqlite_path)
    repository.init_schema()
    provider = CommandImageEnricher(args.model.strip(), args.version.strip(), command, args.timeout)
    summary = enrich_images(build_archive_source(config), repository, provider, args.limit, album=args.album)
    print(f"Enriched: {summary.enriched} | Failed: {summary.failed} | Changed while processing: {summary.changed}")
    return int(summary.failed > 0)


if __name__ == "__main__":
    raise SystemExit(main())
