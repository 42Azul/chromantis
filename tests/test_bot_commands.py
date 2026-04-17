from __future__ import annotations

import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from chromantis.bot.telegram_bot import ChatSession, TelegramBotApp, TelegramBotService
from chromantis.db.repository import Repository
from chromantis.ftp.client import LocalPathFTPClient
from chromantis.ftp.scanner import FTPScanner
from chromantis.parsing.path_parser import PathParser
from chromantis.search.service import SearchService


PHOTOS_ROOT = (
    Path(__file__).parent / "fixtures" / "ftp_tree" / "server_root" / "photos" / "archive"
)


class TelegramBotServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = str(Path(self.temp_dir.name) / "chromantis.db")
        repository = Repository(db_path)
        repository.init_schema()
        scanner = FTPScanner(LocalPathFTPClient(), repository, PathParser())
        scanner.scan(str(PHOTOS_ROOT))
        self.service = TelegramBotService(
            SearchService(repository),
            chat_allowlist=(1234,),
            stats_provider=repository.get_index_stats,
            access_code="246810",
            auth_checker=repository.is_chat_authorized,
            auth_granter=repository.authorize_chat,
            auth_revoker=repository.revoke_chat,
            session_loader=repository.get_chat_session,
            session_saver=repository.save_chat_session,
            session_clearer=repository.clear_chat_session,
        )
        self.repository = repository

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_years_command(self) -> None:
        reply = self.service.handle_command("/years", chat_id=1234)
        self.assertIn("2019", reply.text)
        self.assertIn("2021", reply.text)
        self.assertIn("folder(s)", reply.text)

    def test_whoami_command(self) -> None:
        reply = self.service.handle_command(
            "/whoami",
            chat_id=1234,
            username="tester",
            first_name="Test",
        )
        self.assertIn("Chat ID: 1234", reply.text)
        self.assertIn("Auth mode: allowlist", reply.text)
        self.assertIn("Admin: yes", reply.text)

    def test_random_command_returns_image_path(self) -> None:
        reply = self.service.handle_command("/random city", chat_id=1234)
        self.assertEqual(len(reply.image_paths), 1)
        self.assertTrue(reply.buttons)

    def test_unauthorized_chat_is_rejected(self) -> None:
        reply = self.service.handle_command("/years", chat_id=999)
        self.assertEqual(reply.text, "Unauthorized chat. Use /login <access-code>.")

    def test_stats_command(self) -> None:
        reply = self.service.handle_command("/stats", chat_id=1234)
        self.assertIn("Indexed folders:", reply.text)
        self.assertIn("Indexed images:", reply.text)

    def test_years_accepts_range(self) -> None:
        reply = self.service.handle_command("/years 2019-2021", chat_id=1234)
        self.assertIn("2019", reply.text)
        self.assertIn("2021", reply.text)

    def test_years_rejects_non_year_arguments(self) -> None:
        reply = self.service.handle_command("/years city", chat_id=1234)
        self.assertEqual(reply.text, "Usage: /years or /years 2018-2021")

    def test_start_for_unauthorized_chat_shows_login_message(self) -> None:
        reply = self.service.handle_command("/start", chat_id=999)
        self.assertIn("/login <access-code>", reply.text)

    def test_login_requires_valid_code(self) -> None:
        reply = self.service.handle_command("/login 000000", chat_id=999)
        self.assertEqual(reply.text, "Invalid access code.")
        self.assertFalse(self.repository.is_chat_authorized(999))

    def test_login_persists_chat_authorization(self) -> None:
        reply = self.service.handle_command(
            "/login 246810",
            chat_id=999,
            username="tester",
            first_name="Test",
        )
        self.assertEqual(reply.text, "Chat authorized. Use /help to see available commands.")
        self.assertTrue(self.repository.is_chat_authorized(999))

        help_reply = self.service.handle_command("/help", chat_id=999)
        self.assertIn("/logout", help_reply.text)

    def test_logout_revokes_dynamic_authorization(self) -> None:
        self.repository.authorize_chat(999, username="tester", first_name="Test")

        reply = self.service.handle_command("/logout", chat_id=999)

        self.assertEqual(reply.text, "Chat authorization removed.")
        self.assertFalse(self.repository.is_chat_authorized(999))
        self.assertIsNone(self.repository.get_chat_session(999))

    def test_logout_does_not_revoke_static_allowlist(self) -> None:
        reply = self.service.handle_command("/logout", chat_id=1234)
        self.assertIn("static allowlist", reply.text)

    def test_images_command_accepts_count_and_returns_multiple_images(self) -> None:
        reply = self.service.handle_command("/images 2 city", chat_id=1234)

        self.assertEqual(len(reply.image_paths), 2)
        self.assertIn("Showing images: 2 image(s)", reply.text)
        labels = {button.label for row in reply.buttons for button in row}
        self.assertIn("More", labels)
        self.assertIn("Same Folder", labels)

    def test_people_add_and_show_commands(self) -> None:
        create_reply = self.service.handle_command("/people add Pablo", chat_id=1234)
        self.assertIn("Person created: Pablo", create_reply.text)

        alias_reply = self.service.handle_command(
            "/people alias Pablo | Pablito",
            chat_id=1234,
        )
        self.assertIn("Alias added: Pablo", alias_reply.text)

        link_reply = self.service.handle_command(
            "/people link Pablo | 2021/2021-08-15_city_trip",
            chat_id=1234,
        )
        self.assertIn("Person linked: Pablo", link_reply.text)

        show_reply = self.service.handle_command("/people show pablito", chat_id=1234)
        self.assertIn("Person: Pablo", show_reply.text)
        self.assertIn("Pablito", show_reply.text)
        self.assertIn("2021/2021-08-15_city_trip", show_reply.text)

    def test_people_command_lists_people(self) -> None:
        self.service.handle_command("/people add Pablo", chat_id=1234)

        reply = self.service.handle_command("/people", chat_id=1234)

        self.assertIn("Curated people:", reply.text)
        self.assertIn("Pablo", reply.text)

    def test_people_write_requires_admin_when_admin_allowlist_is_configured(self) -> None:
        restricted_service = TelegramBotService(
            SearchService(self.repository),
            chat_allowlist=(1234,),
            admin_chat_allowlist=(9999,),
            stats_provider=self.repository.get_index_stats,
            access_code="246810",
            auth_checker=self.repository.is_chat_authorized,
            auth_granter=self.repository.authorize_chat,
            auth_revoker=self.repository.revoke_chat,
            session_loader=self.repository.get_chat_session,
            session_saver=self.repository.save_chat_session,
            session_clearer=self.repository.clear_chat_session,
        )

        reply = restricted_service.handle_command("/people add Pablo", chat_id=1234)

        self.assertEqual(reply.text, "Admin privileges are required for /people write commands.")

    def test_images_command_supports_people_alias_and_year_range(self) -> None:
        self.service.handle_command("/people add Pablo", chat_id=1234)
        self.service.handle_command("/people alias Pablo | Pablito", chat_id=1234)
        self.service.handle_command(
            "/people link Pablo | 2021/2021-08-15_city_trip",
            chat_id=1234,
        )

        reply = self.service.handle_command("/images 2 pablito 2020-2021", chat_id=1234)

        self.assertEqual(len(reply.image_paths), 2)
        self.assertIn('person="Pablo"', reply.text)
        self.assertIn("year_range=2020-2021", reply.text)

    def test_more_returns_additional_images_from_same_scope(self) -> None:
        first = self.service.handle_command("/images 1 city", chat_id=1234)
        second = self.service.handle_command("/more 1", chat_id=1234)

        self.assertEqual(len(first.image_paths), 1)
        self.assertEqual(len(second.image_paths), 1)
        self.assertNotEqual(first.image_paths[0], second.image_paths[0])
        self.assertIn("More images", second.text)

    def test_same_folder_callback_returns_additional_images(self) -> None:
        first = self.service.handle_command("/images 1 city", chat_id=1234)
        second = self.service.handle_callback("nav:same_folder", chat_id=1234)

        self.assertEqual(len(first.image_paths), 1)
        self.assertEqual(len(second.image_paths), 1)
        self.assertNotEqual(first.image_paths[0], second.image_paths[0])
        self.assertIn("Same folder", second.text)

    def test_same_year_callback_returns_images(self) -> None:
        self.service.handle_command("/images 1 city", chat_id=1234)
        reply = self.service.handle_callback("nav:same_year", chat_id=1234)

        self.assertGreaterEqual(len(reply.image_paths), 1)
        self.assertIn("Same year", reply.text)

    def test_back_callback_restores_previous_view(self) -> None:
        first = self.service.handle_command("/images 1 city", chat_id=1234)
        self.service.handle_callback("nav:same_year", chat_id=1234)
        back = self.service.handle_callback("nav:back", chat_id=1234)

        self.assertEqual(back.image_paths, first.image_paths)
        self.assertEqual(back.text, first.text)

    def test_refine_callback_returns_text(self) -> None:
        self.service.handle_command("/images 2 city", chat_id=1234)
        reply = self.service.handle_callback("nav:refine", chat_id=1234)

        self.assertIn("Refine this search:", reply.text)
        self.assertIn("/images", reply.text)

    def test_mixed_folder_batch_discloses_folder_breakdown(self) -> None:
        reply = self.service.handle_command("/images 4 summer", chat_id=1234)

        self.assertEqual(len(reply.image_paths), 4)
        self.assertIn("Folders in this batch: 2", reply.text)
        self.assertIn("2021/2021-08-15_city_trip: 2", reply.text)
        self.assertIn("2019/2019-07-10_beach_day: 2", reply.text)
        labels = {button.label for row in reply.buttons for button in row}
        self.assertIn("Folders", labels)
        self.assertNotIn("Same Folder", labels)
        self.assertNotIn("Same Year", labels)
        self.assertNotIn("Random Similar", labels)

    def test_folder_picker_callback_lists_batch_folders(self) -> None:
        self.service.handle_command("/images 4 summer", chat_id=1234)
        reply = self.service.handle_callback("nav:folders", chat_id=1234)

        self.assertIn("Choose a folder from this batch:", reply.text)
        labels = [button.label for row in reply.buttons for button in row]
        self.assertIn("2021/2021-08-15_city_trip (2)", labels)
        self.assertIn("2019/2019-07-10_beach_day (2)", labels)

    def test_folder_selection_continues_with_more_from_that_folder(self) -> None:
        self.service.handle_command("/images 3 summer", chat_id=1234)
        self.service.handle_callback("nav:folders", chat_id=1234)
        reply = self.service.handle_callback("nav:folder:1", chat_id=1234)

        self.assertEqual(len(reply.image_paths), 1)
        self.assertIn("More from 2019/2019-07-10_beach_day", reply.text)

    def test_more_from_folder_picker_requires_returning_to_images(self) -> None:
        self.service.handle_command("/images 4 summer", chat_id=1234)
        self.service.handle_callback("nav:folders", chat_id=1234)
        reply = self.service.handle_command("/more 1", chat_id=1234)

        self.assertIn("Current view is not an image batch", reply.text)

    def test_more_requires_previous_image_context(self) -> None:
        reply = self.service.handle_command("/more 1", chat_id=1234)
        self.assertIn("No previous image search", reply.text)

    def test_session_is_persisted_for_navigation(self) -> None:
        self.service.handle_command("/images 2 city", chat_id=1234)

        raw_session = self.repository.get_chat_session(1234)

        self.assertIsNotNone(raw_session)
        session = ChatSession.from_json(raw_session)
        self.assertIsNotNone(session.current)
        self.assertEqual(session.current.scope, "search_images")

    def test_app_uses_image_fetcher_for_remote_images(self) -> None:
        fetched_paths: list[str] = []

        def image_fetcher(path: str) -> bytes:
            fetched_paths.append(path)
            return b"remote-image"

        app = TelegramBotApp(
            token="dummy-token",
            service=self.service,
            image_fetcher=image_fetcher,
        )
        image_file = app._open_image("/ftp/root/2021/folder/IMG_001.jpg")

        self.assertIsInstance(image_file, BytesIO)
        self.assertEqual(image_file.read(), b"remote-image")
        self.assertEqual(image_file.name, "IMG_001.jpg")
        self.assertEqual(fetched_paths, ["/ftp/root/2021/folder/IMG_001.jpg"])
        image_file.close()

    def test_app_can_open_local_image_path(self) -> None:
        app = TelegramBotApp(token="dummy-token", service=self.service)
        local_image = PHOTOS_ROOT / "2021" / "2021-08-15_city_trip" / "IMG_001.jpg"

        image_file = app._open_image(str(local_image))

        self.assertEqual(image_file.read(), b"fake image 2\n")
        image_file.close()

    def test_app_uses_batch_image_fetcher_for_multiple_remote_images(self) -> None:
        fetched_batches: list[tuple[str, ...]] = []
        single_fetches: list[str] = []

        def image_fetcher(path: str) -> bytes:
            single_fetches.append(path)
            return f"single:{Path(path).name}".encode()

        def image_batch_fetcher(paths: tuple[str, ...]) -> tuple[bytes, ...]:
            fetched_batches.append(paths)
            return tuple(f"batch:{Path(path).name}".encode() for path in paths)

        app = TelegramBotApp(
            token="dummy-token",
            service=self.service,
            image_fetcher=image_fetcher,
            image_batch_fetcher=image_batch_fetcher,
        )

        image_files = app._open_images(
            (
                "/ftp/root/2021/folder/IMG_001.jpg",
                "/ftp/root/2021/folder/IMG_002.jpg",
            )
        )

        self.assertEqual(fetched_batches, [("/ftp/root/2021/folder/IMG_001.jpg", "/ftp/root/2021/folder/IMG_002.jpg")])
        self.assertEqual(single_fetches, [])
        self.assertEqual([image_file.read() for image_file in image_files], [b"batch:IMG_001.jpg", b"batch:IMG_002.jpg"])
        for image_file in image_files:
            image_file.close()

    def test_app_registers_handlers(self) -> None:
        app = TelegramBotApp(token="dummy-token", service=self.service).build()

        commands = {
            next(iter(handler.commands))
            for handlers in app.handlers.values()
            for handler in handlers
            if hasattr(handler, "commands") and handler.commands
        }

        self.assertIn("login", commands)
        self.assertIn("logout", commands)
        self.assertIn("more", commands)
        self.assertIn("people", commands)
        callback_handlers = [
            handler
            for handlers in app.handlers.values()
            for handler in handlers
            if handler.__class__.__name__ == "CallbackQueryHandler"
        ]
        self.assertTrue(callback_handlers)
