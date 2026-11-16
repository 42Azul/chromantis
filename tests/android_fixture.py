"""Serve a temporary synthetic archive over HTTPS for Android smoke testing."""

from __future__ import annotations

import argparse
import ssl
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw

from chromantis.api.server import ApiServer, make_api_handler
from chromantis.api.thumbnails import build_thumbnail_cache
from chromantis.app import ApplicationService
from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser
from chromantis.source import ArchiveScanner, LocalArchiveSource


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cert", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--index-only", action="store_true", help="Disconnect the synthetic archive after indexing.")
    args = parser.parse_args()

    with TemporaryDirectory(prefix="chromantis-android-") as directory:
        root = Path(directory)
        archive = root / "archive"
        for folder, count in (("2024/2024-07-01_playa", 33), ("2023/2023-10-05_excursion", 2)):
            album = archive / folder
            album.mkdir(parents=True)
            for number in range(1, count + 1):
                with Image.new("RGB", (640, 480), (number * 23 % 256, 112, 160)) as image:
                    ImageDraw.Draw(image).text((35, 35), f"Synthetic photo {number}", fill="white")
                    image.save(album / f"Photo_{number:02d}.jpg")

        db = str(root / "index.db")
        repository = Repository(db)
        repository.init_schema()
        ana = repository.create_person("Ana")
        repository.add_person_alias(ana.id, "Anita")
        source = LocalArchiveSource(str(archive))
        ArchiveScanner(source, repository, PathParser()).scan()
        if args.index_only:
            archive.rename(root / "disconnected")
        app = ApplicationService(repository)
        _, invite = app.family_access.invite("Android fixture")
        handler = make_api_handler(
            app,
            api_token="synthetic-fixture-only",
            image_fetcher=source.read_bytes,
            thumbnails=build_thumbnail_cache(db, 8, source),
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(args.cert, args.key)
        with ApiServer((args.bind, args.port), handler) as server:
            server.socket = context.wrap_socket(server.socket, server_side=True)
            print(f"Fixture: https://{args.bind}:{server.server_port}", flush=True)
            print(f"SQLite: {db}", flush=True)
            print(f"Family code: {invite}", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()

