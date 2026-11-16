import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chromantis.config import AppConfig
from chromantis.db.backup import create_backup, restore_backup, verify_backup


def _print_summary(action: str, result) -> None:
    print(f"{action}: {result.path}")
    print(f"Bytes: {result.size}")
    print(f"SHA-256: {result.sha256}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create, verify, or restore a Chromantis SQLite backup.")
    parser.add_argument(
        "--database", help="SQLite database path; defaults to SQLITE_PATH from the environment."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create", help="Create a consistent backup without stopping readers.").add_argument(
        "backup"
    )
    commands.add_parser("verify", help="Check backup integrity and print its digest.").add_argument("backup")
    commands.add_parser(
        "restore", help="Restore into a new database path; existing files are never overwritten."
    ).add_argument("backup")
    args = parser.parse_args()

    try:
        if args.command == "create":
            database = args.database or AppConfig.from_env().sqlite_path
            result = create_backup(database, args.backup)
            action = "Backup created"
        elif args.command == "restore":
            database = args.database or AppConfig.from_env().sqlite_path
            result = restore_backup(args.backup, database)
            action = "Database restored"
        else:
            result = verify_backup(args.backup)
            action = "Backup verified"
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as error:
        parser.error(str(error))
    _print_summary(action, result)


if __name__ == "__main__":
    main()
