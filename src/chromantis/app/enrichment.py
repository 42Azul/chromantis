from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from ftplib import Error as FtpError
from typing import Protocol

from chromantis.db.repository import Repository
from chromantis.source.adapters import ArchiveSource

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImageEnrichment:
    caption: str
    ocr_text: str
    object_tags: tuple[str, ...]


class ImageEnricher(Protocol):
    model: str
    version: str

    def enrich(self, image: bytes) -> ImageEnrichment:
        ...


@dataclass(frozen=True)
class CommandImageEnricher:
    model: str
    version: str
    command: tuple[str, ...]
    timeout: float

    def enrich(self, image: bytes) -> ImageEnrichment:
        result = subprocess.run(
            self.command, input=image, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=self.timeout, check=True,
        )
        data = json.loads(result.stdout.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Expected an enrichment JSON object.")
        caption, ocr_text, tags = data.get("caption"), data.get("ocr_text"), data.get("object_tags")
        if not isinstance(caption, str) or len(caption) > 4000:
            raise ValueError("Invalid caption.")
        if not isinstance(ocr_text, str) or len(ocr_text) > 40_000:
            raise ValueError("Invalid OCR text.")
        if not isinstance(tags, list) or len(tags) > 100 or any(
            not isinstance(tag, str) or not tag.strip() or len(tag) > 100 for tag in tags
        ):
            raise ValueError("Invalid object tags.")
        return ImageEnrichment(caption.strip(), ocr_text.strip(), tuple(dict.fromkeys(tag.strip() for tag in tags)))


@dataclass(frozen=True)
class EnrichmentSummary:
    enriched: int
    failed: int
    changed: int


def enrich_images(
    source: ArchiveSource, repository: Repository, provider: ImageEnricher, limit: int
) -> EnrichmentSummary:
    enriched = failed = changed = 0
    candidates = repository.list_enrichment_candidates(source.source_root, provider.model, provider.version, limit)
    for candidate in candidates:
        try:
            result = provider.enrich(source.read_bytes(candidate.path))
        except (FtpError, OSError, subprocess.SubprocessError, ValueError) as exc:
            logger.warning("Enrichment failed for image %d (%s)", candidate.image_id, type(exc).__name__)
            repository.save_image_enrichment(
                candidate, provider.model, provider.version, "", "", (), error=type(exc).__name__
            )
            failed += 1
            continue
        saved = repository.save_image_enrichment(
            candidate, provider.model, provider.version, result.caption, result.ocr_text, result.object_tags
        )
        if saved:
            enriched += 1
        else:
            changed += 1
    return EnrichmentSummary(enriched, failed, changed)
