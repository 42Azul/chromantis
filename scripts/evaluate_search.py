"""Compare the existing search modes on a temporary, synthetic photo archive."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chromantis.app import ApplicationService
from chromantis.app.enrichment import CommandImageEnricher, enrich_images
from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser
from chromantis.search.service import SearchResult
from chromantis.source import ArchiveScanner, LocalArchiveSource


BEACH = "2024/2024-08-04_playa"
OLD_BEACH = "2023/2023-08-10_playa"
WALK = "2024/2024-07-21_paseo"
CARDS = "2024/2024-09-14_cartas"
OFFICE = "2022/2022-09-14_oficina"
STATION = "2024/2024-03-02_anden"
DINNER = "2023/2023-12-27_cena"
HARBOR = "2024/2024-09-20_puerto"
OTHER_SIGN = "2024/2024-04-14_excursion"


@dataclass(frozen=True)
class Query:
    id: str
    category: str
    text: str
    expected: tuple[str, ...]
    folders: bool = False
    place: str = ""
    date_from: str | None = None
    date_to: str | None = None


def photo(folder: str) -> str:
    return f"{folder}/001.png"


QUERIES = (
    Query("album_year", "metadata", "playa 2024", (photo(BEACH),)),
    Query("person_alias", "metadata", "Ani playa", (photo(BEACH),)),
    Query("album_alias", "metadata", "Cena de fin de año", (DINNER,), folders=True),
    Query("place_date", "metadata", "", (BEACH,), folders=True, place="Cabo de Palos",
          date_from="2024-07-01", date_to="2024-08-31"),
    Query("ocr_all", "written_text", "cala azul", (photo(CARDS), photo(OFFICE), photo(OTHER_SIGN))),
    Query("ocr_year", "written_text", "cala azul 2024", (photo(CARDS), photo(OTHER_SIGN))),
    Query("ocr_person_year", "written_text", "Ana cala azul 2024", (photo(CARDS),)),
    Query("ocr_station", "written_text", "estacion norte", (photo(STATION),)),
    Query("visual_bike", "visual", "bicicleta roja junto al mar", (photo(BEACH), photo(OLD_BEACH), photo(WALK))),
    Query("visual_bike_year", "visual", "red bicycle by the sea 2024", (photo(BEACH), photo(WALK))),
    Query("visual_bike_person", "visual", "bicicleta roja Ani 2024", (photo(BEACH),)),
    Query("visual_boat", "visual", "barco azul", (photo(HARBOR),)),
    Query("absent_object", "negative", "cohete plateado", ()),
)
LIMIT = 5


def build_archive(directory: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    scenes = {
        BEACH: "bicycle", OLD_BEACH: "bicycle", WALK: "bicycle",
        HARBOR: "boat", DINNER: "dinner",
        CARDS: "CALA AZUL", OFFICE: "CALA AZUL", OTHER_SIGN: "CALA AZUL",
        STATION: "ESTACION NORTE",
    }
    font = ImageFont.load_default(size=64)
    for folder, scene in scenes.items():
        path = directory / photo(folder)
        path.parent.mkdir(parents=True)
        with Image.new("RGB", (760, 460), "white") as image:
            draw = ImageDraw.Draw(image)
            if scene in {"bicycle", "boat"}:
                draw.rectangle((0, 145, 760, 320), fill="#91c4e3")
                draw.rectangle((0, 320, 760, 460), fill="#e4ceaa")
            if scene == "bicycle":
                for x in (250, 480):
                    draw.ellipse((x - 56, 242, x + 56, 354), outline="#222222", width=8)
                draw.line((250, 298, 350, 298, 438, 216, 315, 216, 350, 298), fill="#bd2020", width=12)
                draw.line((438, 216, 480, 298), fill="#bd2020", width=12)
                draw.line((302, 208, 333, 208), fill="#222222", width=7)
                draw.line((432, 209, 452, 190), fill="#222222", width=7)
            elif scene == "boat":
                draw.polygon([(225, 207), (565, 207), (498, 297), (293, 297)], fill="#254d92")
                draw.polygon([(390, 200), (390, 75), (500, 200)], fill="#eab86e")
            elif scene == "dinner":
                draw.rectangle((115, 100, 645, 360), fill="#7d5338")
                for x in (310, 450):
                    draw.ellipse((x - 54, 165, x + 54, 273), fill="white")
            else:
                draw.text((380, 230), scene, anchor="mm", fill="black", font=font)
            image.save(path)


def seed_curation(repository: Repository) -> None:
    app = ApplicationService(repository, static_owner_chat_ids=(1,))
    person = app.create_person("Ana", actor_chat_id=1)
    app.add_person_alias(person.id, "Ani", actor_chat_id=1)
    for folder in (BEACH, CARDS):
        app.link_person_to_folder(person.id, folder, actor_chat_id=1)
    for folder, changes in {BEACH: {"place": "Cabo de Palos, Murcia"},
                            DINNER: {"aliases": ["Cena de fin de año"]}}.items():
        item = app.get_album_review(1, path=folder)
        app.edit_album_context(1, folder, item["id"], item["context_revision"], changes)


def evaluate(repository: Repository, *, use_ocr: bool, repeat: int) -> dict:
    app = ApplicationService(repository, include_enrichment=use_ocr)
    return evaluate_queries(lambda query: run_query(app, query), repeat)


def run_query(app: ApplicationService, query: Query) -> list[SearchResult]:
    if query.folders:
        return app.search_folders(
            query.text, LIMIT, place=query.place, date_from=query.date_from, date_to=query.date_to,
        )
    return app.search_images(query.text, LIMIT)


def evaluate_queries(
    search: Callable[[Query], list[SearchResult]], repeat: int, queries: tuple[Query, ...] = QUERIES,
) -> dict:
    samples, cases = [], []
    for query in queries:
        for _ in range(repeat):
            started = perf_counter()
            results = search(query)
            samples.append((perf_counter() - started) * 1000)
        actual = {item.path for item in results}
        expected = set(query.expected)
        cases.append({
            "id": query.id, "category": query.category, "query": query.text,
            "expected": sorted(expected),
            "missing": sorted(expected - actual), "unexpected": sorted(actual - expected),
            "matches": [{"path": item.path, "reason": item.reason} for item in results],
        })
    totals = {}
    for case in cases:
        counts = totals.setdefault(case["category"], {"exact": 0, "cases": 0, "relevant": 0, "found": 0})
        counts["cases"] += 1
        counts["exact"] += not (case["missing"] or case["unexpected"])
        counts["relevant"] += len(case["expected"])
        counts["found"] += len(case["expected"]) - len(case["missing"])
    samples.sort()
    return {
        "exact_at_5_by_category": totals,
        "recall_at_5_by_category": {
            category: counts["found"] / counts["relevant"] if counts["relevant"] else None
            for category, counts in totals.items()
        },
        "median_query_ms": round(statistics.median(samples), 3),
        "p95_query_ms": round(samples[math.ceil(0.95 * len(samples)) - 1], 3),
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ocr", action="store_true", help="Also run the installed Tesseract adapter in English.")
    parser.add_argument("--repeat", type=int, default=10, help="Repeats per query for timing (1–100).")
    args = parser.parse_args()
    if not 1 <= args.repeat <= 100:
        parser.error("--repeat must be between 1 and 100.")
    try:
        import PIL.Image
    except ImportError:
        parser.error("Install chromantis[thumbnails] to draw the synthetic fixtures.")
    version = None
    if args.ocr:
        try:
            version = subprocess.check_output(["tesseract", "--version"], text=True, timeout=5).splitlines()[0]
        except (OSError, subprocess.SubprocessError):
            parser.error("The OCR comparison needs a local Tesseract installation with English data.")

    with TemporaryDirectory(prefix="chromantis-search-") as folder:
        root = Path(folder)
        archive = root / "photos"
        build_archive(archive)
        source = LocalArchiveSource(str(archive))
        repository = Repository(str(root / "index.db"))
        repository.init_schema()
        scan = ArchiveScanner(source, repository, PathParser()).scan()
        seed_curation(repository)
        report = {
            "images": scan.summary.images_indexed,
            "lexical": evaluate(repository, use_ocr=False, repeat=args.repeat),
        }
        if args.ocr:
            adapter = CommandImageEnricher("tesseract-eng", version, (
                sys.executable, str(ROOT / "scripts/tesseract_enricher.py"), "--language", "eng",
            ), 15)
            started = perf_counter()
            summary = enrich_images(source, repository, adapter, scan.summary.images_indexed)
            report["ocr"] = {
                "version": version,
                "build_seconds": round(perf_counter() - started, 3),
                "enriched": summary.enriched,
                "failed": summary.failed,
                **evaluate(repository, use_ocr=True, repeat=args.repeat),
            }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(bool(args.ocr and report["ocr"]["failed"]))


if __name__ == "__main__":
    raise SystemExit(main())
