from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from chromantis.api.server import handle_api_get
from chromantis.app import ApplicationService
from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser
from chromantis.source import ArchiveScanner, LocalArchiveSource


PHOTOS_ROOT = Path(__file__).parent / "fixtures" / "ftp_tree" / "server_root" / "photos" / "archive"


class ApiServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = str(Path(self.temp_dir.name) / "chromantis.db")
        repository = Repository(db_path)
        repository.init_schema()
        scanner = ArchiveScanner(LocalArchiveSource(str(PHOTOS_ROOT)), repository, PathParser())
        scanner.scan()
        self.app_service = ApplicationService(repository)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_health_endpoint_is_public(self) -> None:
        status, payload = handle_api_get("/api/v1/health", app_service=self.app_service, api_token="secret-token")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"status": "ok"})

    def test_images_endpoint_requires_token(self) -> None:
        status, payload = handle_api_get("/api/v1/images?q=city", app_service=self.app_service, api_token="secret-token")
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "Unauthorized")

    def test_images_endpoint_returns_results_with_token(self) -> None:
        status, payload = handle_api_get(
            "/api/v1/images?q=city&limit=2",
            app_service=self.app_service,
            api_token="secret-token",
            auth_header="Bearer secret-token",
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["items"]), 2)
        self.assertIn("path", payload["items"][0])
        self.assertIn("reason", payload["items"][0])

    def test_years_endpoint_returns_summaries(self) -> None:
        status, payload = handle_api_get(
            "/api/v1/years?from=2019&to=2021",
            app_service=self.app_service,
            api_token="secret-token",
            x_api_token="secret-token",
        )
        self.assertEqual(status, 200)
        years = [item["year"] for item in payload["items"]]
        self.assertEqual(years, [2019, 2021])
