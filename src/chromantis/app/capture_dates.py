from __future__ import annotations

import logging
import re
import struct
from dataclasses import dataclass
from datetime import datetime
from ftplib import Error as FtpError
from io import BytesIO

from chromantis.db.repository import Repository
from chromantis.source.adapters import ArchiveSource


logger = logging.getLogger(__name__)
EXIF_PREFIX_BYTES = 512 * 1024
EXIF_TIMESTAMP = re.compile(r"[0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}")


def jpeg_capture_date(prefix: bytes) -> str | None:
    # This optional dependency is only needed by the explicit extraction command.
    from PIL import ExifTags, Image

    try:
        with Image.open(BytesIO(prefix), formats=("JPEG",)) as image:
            exif = image.getexif()
            tag = ExifTags.Base.DateTimeOriginal
            recorded = exif.get_ifd(ExifTags.IFD.Exif).get(tag, exif.get(tag))
        if isinstance(recorded, str) and EXIF_TIMESTAMP.fullmatch(recorded):
            return datetime.strptime(recorded, "%Y:%m:%d %H:%M:%S").date().isoformat()
    except (Image.DecompressionBombError, OSError, ValueError, SyntaxError, struct.error):
        pass
    return None


@dataclass(frozen=True)
class CaptureDateSummary:
    found: int
    missing: int
    retry: int
    stale: int


def index_capture_dates(
    source: ArchiveSource, repository: Repository, limit: int, album: str | None = None,
) -> CaptureDateSummary:
    found = missing = retry = stale = 0
    for image in repository.capture_date_candidates(source.source_root, limit, album):
        try:
            prefix = source.read_prefix(image.path, EXIF_PREFIX_BYTES)
        except (OSError, FtpError, EOFError, ValueError) as error:
            logger.warning("Could not read photo %d (%s)", image.image_id, type(error).__name__)
            repository.save_capture_date(image, None, retry=True)
            retry += 1
            if isinstance(error, (ConnectionError, TimeoutError, EOFError)):
                break
            continue
        date = jpeg_capture_date(prefix)
        if not repository.save_capture_date(image, date):
            stale += 1
        elif date:
            found += 1
        else:
            missing += 1
    return CaptureDateSummary(found, missing, retry, stale)
