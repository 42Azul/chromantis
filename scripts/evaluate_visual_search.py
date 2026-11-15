"""Test image tags and image/text similarity locally on the synthetic search archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_search import (
    BEACH, LIMIT, OLD_BEACH, QUERIES, WALK, Query, build_archive, evaluate_queries, photo, run_query, seed_curation,
)

from chromantis.app import ApplicationService
from chromantis.app.enrichment import ImageEnrichment, enrich_images
from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser
from chromantis.search.query_parser import ParsedQuery, parse_query
from chromantis.search.service import SearchResult
from chromantis.source import ArchiveScanner, LocalArchiveSource


MODEL = "Xenova/clip-vit-base-patch32"
VERSION = "6ef1ebc8b0766a7a8d11b146462c99cdf74dd22d"
ASSETS = {
    "text_model_quantized.onnx": "73baab855d406190da9faa498cfedf65f15cf309f4cc7385b7b032e6d08e5c3a",
    "vision_model_quantized.onnx": "583fd1110a514667812fee7d684952aaf82a99b959760c8d7dca7e0ab9839299",
    "tokenizer.json": "f7f3b7af117d467b58374797691a6438d3e6b9e9cef800dfd5dced7f697a90cd",
}
VOCABULARY = {
    "a red bicycle by the sea": ("red bicycle by the sea", "bicicleta roja junto al mar"),
    "a blue boat": ("blue boat", "barco azul"),
    "a sign with text": (),
    "a table set for dinner": (),
}
TRIAL_QUERIES = QUERIES + (
    Query("english_person_year", "filters", "red bicycle by the sea Ani 2024", (photo(BEACH),)),
    Query("paraphrased_coast", "paraphrase", "bicycle on the beach", (photo(BEACH), photo(OLD_BEACH), photo(WALK))),
    Query("wrong_bike_colour", "contrast", "blue bicycle", ()),
    Query("wrong_bike_place", "contrast", "bicycle in a garage", ()),
)


def verify_assets(directory: Path) -> int:
    size = 0
    for name, expected in ASSETS.items():
        path = directory / name
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise ValueError(f"Unexpected checksum for {name}. Use files from {MODEL} at {VERSION}.")
        size += path.stat().st_size
    return size


class ClipEncoder:
    def __init__(self, directory: Path):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.np = np
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=77)
        self.mean = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
        self.std = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self.vision = ort.InferenceSession(
            str(directory / "vision_model_quantized.onnx"), options, providers=["CPUExecutionProvider"],
        )
        self.text = ort.InferenceSession(
            str(directory / "text_model_quantized.onnx"), options, providers=["CPUExecutionProvider"],
        )

    def image_vector(self, content: bytes):
        from PIL import Image

        with Image.open(BytesIO(content)) as source:
            image = source.convert("RGB")
        width, height = image.size
        scale = 224 / min(width, height)
        image = image.resize((int(width * scale), int(height * scale)), Image.Resampling.BICUBIC)
        left, top = (image.width - 224) // 2, (image.height - 224) // 2
        cropped = image.crop((left, top, left + 224, top + 224))
        pixels = (self.np.asarray(cropped, dtype=self.np.float32) / 255 - self.mean) / self.std
        vector = self.vision.run(["image_embeds"], {"pixel_values": pixels.transpose(2, 0, 1)[None]})[0][0]
        return vector / self.np.linalg.norm(vector)

    def text_vector(self, phrase: str):
        ids = self.np.array([self.tokenizer.encode(phrase).ids], dtype=self.np.int64)
        vector = self.text.run(["text_embeds"], {"input_ids": ids})[0][0]
        return vector / self.np.linalg.norm(vector)


class VocabularyTagger:
    model = MODEL
    version = VERSION + "-trial-vocabulary-1"

    def __init__(self, encoder: ClipEncoder, threshold: float):
        self.encoder = encoder
        self.threshold = threshold
        self.prompts = [encoder.text_vector(prompt) for prompt in VOCABULARY]

    def enrich(self, image: bytes) -> ImageEnrichment:
        vector = self.encoder.image_vector(image)
        scores = [float(vector @ prompt) for prompt in self.prompts]
        best = max(range(len(scores)), key=scores.__getitem__)
        terms = tuple(VOCABULARY.values())[best] if scores[best] >= self.threshold else ()
        return ImageEnrichment("", "", terms)


def eligible(item: SearchResult, query: ParsedQuery, person_folders: dict[int, set[str]]) -> bool:
    if query.year_from is not None and item.year < query.year_from:
        return False
    if query.year_to is not None and item.year > query.year_to:
        return False
    return all(item.folder_path in person_folders.get(person.id, ()) for person in query.people)


def embedding_search(
    app: ApplicationService, encoder: ClipEncoder, images: list[SearchResult], vectors: dict,
    threshold: float, alias_map: dict, person_folders: dict[int, set[str]], query: Query,
) -> list[SearchResult]:
    lexical = run_query(app, query)
    if lexical or query.folders:
        return lexical
    parsed = parse_query(query.text, alias_map)
    if not parsed.keywords:
        return []
    text_vector = encoder.text_vector(" ".join(parsed.keywords))
    ranked = []
    for image in images:
        if eligible(image, parsed, person_folders):
            score = float(vectors[image.path] @ text_vector)
            if score >= threshold:
                ranked.append((score, image))
    ranked.sort(key=lambda pair: (-pair[0], pair[1].path))
    return [replace(image, reason=f"visual_similarity={score:.3f} ({MODEL})") for score, image in ranked[:LIMIT]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assets", type=Path, help="Local directory containing the pinned ONNX files and tokenizer.")
    parser.add_argument("--threshold", type=float, default=0.28, help="Minimum cosine similarity (default: 0.28).")
    parser.add_argument("--repeat", type=int, default=5, help="Repeat each query for timing (1–20).")
    args = parser.parse_args()
    if not 0 < args.threshold < 1 or not 1 <= args.repeat <= 20:
        parser.error("Use a threshold between 0 and 1 and 1–20 repetitions.")
    try:
        model_bytes = verify_assets(args.assets)
        started = perf_counter()
        encoder = ClipEncoder(args.assets)
        load_seconds = perf_counter() - started
    except (OSError, ValueError, ImportError) as exc:
        parser.error(str(exc))

    with TemporaryDirectory(prefix="chromantis-visual-") as directory:
        root = Path(directory)
        archive = root / "photos"
        database = root / "index.db"
        build_archive(archive)
        source = LocalArchiveSource(str(archive))
        repository = Repository(str(database))
        repository.init_schema()
        scan = ArchiveScanner(source, repository, PathParser()).scan()
        seed_curation(repository)
        baseline = ApplicationService(repository)
        images = baseline.search_images("", scan.summary.images_indexed)
        alias_map = repository.list_alias_map()
        person_folders = {
            person.id: set(repository.get_person_detail(person.id).folder_paths) for person in baseline.list_people()
        }
        report = {
            "model": MODEL, "revision": VERSION, "asset_bytes": model_bytes,
            "load_seconds": round(load_seconds, 3), "threshold": args.threshold,
            "lexical": evaluate_queries(lambda query: run_query(baseline, query), args.repeat, TRIAL_QUERIES),
        }

        started = perf_counter()
        vectors = {image.path: encoder.image_vector(source.read_bytes(image.path)) for image in images}
        vector_seconds = perf_counter() - started
        report["embeddings"] = {
            "build_seconds": round(vector_seconds, 3),
            "vector_payload_bytes": sum(vector.nbytes for vector in vectors.values()),
            **evaluate_queries(lambda query: embedding_search(
                baseline, encoder, images, vectors, args.threshold, alias_map, person_folders, query,
            ), args.repeat, TRIAL_QUERIES),
        }

        original_size = database.stat().st_size
        started = perf_counter()
        tagger = VocabularyTagger(encoder, args.threshold)
        summary = enrich_images(source, repository, tagger, len(images))
        tag_seconds = perf_counter() - started
        with repository.session() as connection:
            tag_bytes = connection.execute(
                "SELECT COALESCE(SUM(length(CAST(object_tags_json AS BLOB))), 0) FROM image_enrichment"
            ).fetchone()[0]
        tagged = ApplicationService(repository, include_enrichment=True)
        report["tags"] = {
            "build_seconds": round(tag_seconds, 3), "sqlite_growth_bytes": database.stat().st_size - original_size,
            "tag_payload_bytes": tag_bytes,
            "enriched": summary.enriched, "failed": summary.failed,
            **evaluate_queries(lambda query: run_query(tagged, query), args.repeat, TRIAL_QUERIES),
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(summary.failed > 0)


if __name__ == "__main__":
    raise SystemExit(main())
