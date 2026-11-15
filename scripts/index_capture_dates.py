import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chromantis.app.capture_dates import index_capture_dates
from chromantis.config import AppConfig
from chromantis.db.repository import Repository
from chromantis.logging_utils import configure_logging
from chromantis.source import build_archive_source


def main() -> int:
    parser = argparse.ArgumentParser(description="Extrae fechas EXIF de un lote pequeño de JPEG indexados.")
    parser.add_argument("--limit", type=int, default=25, help="Máximo de fotos por pasada (1–100).")
    parser.add_argument("--album", help="Limita la pasada a la ruta relativa exacta de un álbum.")
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error("--limit debe estar entre 1 y 100")
    try:
        import PIL.Image
    except ImportError:
        parser.error("Instala el extra chromantis[thumbnails] para leer EXIF.")
    config = AppConfig.from_env()
    configure_logging(config.log_level)
    repository = Repository(config.sqlite_path)
    repository.init_schema()
    summary = index_capture_dates(build_archive_source(config), repository, args.limit, args.album)
    print(f"Con fecha: {summary.found} | Sin fecha: {summary.missing} | "
          f"Pendientes de reintento: {summary.retry} | Cambiaron durante la lectura: {summary.stale}")
    return int(summary.retry > 0)


if __name__ == "__main__":
    raise SystemExit(main())
