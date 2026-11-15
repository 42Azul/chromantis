from __future__ import annotations

import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from chromantis.bot.telegram_bot import ChatSession, TelegramBotApp, TelegramBotService
from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser
from chromantis.search.service import SearchService
from chromantis.source import ArchiveScanner, LocalArchiveSource


PHOTOS_ROOT = (
    Path(__file__).parent / "fixtures" / "ftp_tree" / "server_root" / "photos" / "archive"
)
VIEWER_CHAT_ID = 1234
OWNER_CHAT_ID = 9999


class TelegramBotServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = str(Path(self.temp_dir.name) / "chromantis.db")
        repository = Repository(db_path)
        repository.init_schema()
        scanner = ArchiveScanner(LocalArchiveSource(str(PHOTOS_ROOT)), repository, PathParser())
        scanner.scan()
        self.service = TelegramBotService(
            SearchService(repository),
            chat_allowlist=(VIEWER_CHAT_ID,),
            admin_chat_allowlist=(OWNER_CHAT_ID,),
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
        reply = self.service.handle_command("/years", chat_id=VIEWER_CHAT_ID)
        self.assertIn("2019", reply.text)
        self.assertIn("2021", reply.text)
        self.assertIn("folder(s)", reply.text)

    def test_whoami_command(self) -> None:
        reply = self.service.handle_command(
            "/whoami",
            chat_id=VIEWER_CHAT_ID,
            username="tester",
            first_name="Test",
        )
        self.assertIn(f"Chat ID: {VIEWER_CHAT_ID}", reply.text)
        self.assertIn("Auth mode: static_viewer", reply.text)
        self.assertIn("Role: viewer", reply.text)
        self.assertIn("Admin: no", reply.text)

    def test_whoami_reports_static_owner(self) -> None:
        reply = self.service.handle_command("/whoami", chat_id=OWNER_CHAT_ID)
        self.assertIn("Auth mode: static_owner", reply.text)
        self.assertIn("Role: owner", reply.text)
        self.assertIn("Admin: yes", reply.text)

    def test_random_command_returns_image_path(self) -> None:
        reply = self.service.handle_command("/random city", chat_id=VIEWER_CHAT_ID)
        self.assertEqual(len(reply.image_paths), 1)
        self.assertTrue(reply.buttons)

    def test_unauthorized_chat_is_rejected(self) -> None:
        reply = self.service.handle_command("/years", chat_id=999)
        self.assertEqual(reply.text, "Unauthorized chat. Use /login <access-code>.")

    def test_stats_command(self) -> None:
        reply = self.service.handle_command("/stats", chat_id=VIEWER_CHAT_ID)
        self.assertIn("Indexed folders:", reply.text)
        self.assertIn("Indexed images:", reply.text)

    def test_years_accepts_range(self) -> None:
        reply = self.service.handle_command("/years 2019-2021", chat_id=VIEWER_CHAT_ID)
        self.assertIn("2019", reply.text)
        self.assertIn("2021", reply.text)

    def test_years_rejects_non_year_arguments(self) -> None:
        reply = self.service.handle_command("/years city", chat_id=VIEWER_CHAT_ID)
        self.assertEqual(reply.text, "Usage: /years or /years 2018-2021")

    def test_start_for_unauthorized_chat_shows_login_message(self) -> None:
        reply = self.service.handle_command("/start", chat_id=999)
        self.assertIn("Choose your preferred language", reply.text)
        labels = {button.label for row in reply.buttons for button in row}
        self.assertIn("English", labels)
        self.assertIn("Español", labels)

    def test_start_for_authorized_chat_without_preference_shows_language_picker(self) -> None:
        reply = self.service.handle_command("/start", chat_id=VIEWER_CHAT_ID)

        labels = {button.label for row in reply.buttons for button in row}
        self.assertIn("English", labels)
        self.assertIn("Español", labels)

    def test_language_selection_opens_authorized_home_in_selected_language(self) -> None:
        reply = self.service.handle_callback("language:set:es", chat_id=VIEWER_CHAT_ID)

        self.assertIn("Chromantis ya esta listo", reply.text)
        labels = {button.label for row in reply.buttons for button in row}
        self.assertIn("Años", labels)
        self.assertIn("Ajustes", labels)

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
        self.assertIn("Chat authorized.", reply.text)
        self.assertIn("The easiest way to use it", reply.text)
        self.assertTrue(self.repository.is_chat_authorized(999))
        self.assertEqual(self.repository.get_chat_role(999), "viewer")

        help_reply = self.service.handle_command("/help", chat_id=999)
        self.assertIn("How to use Chromantis", help_reply.text)

    def test_invite_authorizes_new_viewer_chat(self) -> None:
        invite_reply = self.service.handle_command("/invite viewer 5", chat_id=OWNER_CHAT_ID)
        self.assertIn("Invite created.", invite_reply.text)
        code = next(
            line.split(": ", 1)[1]
            for line in invite_reply.text.splitlines()
            if line.startswith("Code: ")
        )

        login_reply = self.service.handle_command(
            f"/login {code}",
            chat_id=5678,
            username="viewer",
            first_name="Viewer",
        )

        self.assertIn("Chat authorized.", login_reply.text)
        self.assertIn("Good examples", login_reply.text)
        self.assertEqual(self.repository.get_chat_role(5678), "viewer")

    def test_unauthorized_language_selection_shows_localized_guest_onboarding(self) -> None:
        reply = self.service.handle_callback("language:set:es", chat_id=5678)

        self.assertIn("Bienvenido a Chromantis.", reply.text)
        self.assertIn("/login <access-code>", reply.text)
        labels = {button.label for row in reply.buttons for button in row}
        self.assertIn("Ayuda de Busqueda", labels)
        self.assertIn("Ajustes", labels)

    def test_logout_revokes_dynamic_authorization(self) -> None:
        self.repository.authorize_chat(999, username="tester", first_name="Test")

        reply = self.service.handle_command("/logout", chat_id=999)

        self.assertEqual(reply.text, "Chat authorization removed.")
        self.assertFalse(self.repository.is_chat_authorized(999))
        self.assertIsNone(self.repository.get_chat_session(999))

    def test_logout_does_not_revoke_static_allowlist(self) -> None:
        reply = self.service.handle_command("/logout", chat_id=VIEWER_CHAT_ID)
        self.assertIn("static configuration", reply.text)

    def test_images_command_accepts_count_and_returns_multiple_images(self) -> None:
        reply = self.service.handle_command("/images 2 city", chat_id=VIEWER_CHAT_ID)

        self.assertEqual(len(reply.image_paths), 2)
        self.assertIn("Showing images: 2 image(s)", reply.text)
        labels = {button.label for row in reply.buttons for button in row}
        self.assertIn("More", labels)
        self.assertIn("Same Folder", labels)

    def test_plain_text_query_is_interpreted(self) -> None:
        reply = self.service.handle_text_input("show me 2 city photos from 2021", chat_id=VIEWER_CHAT_ID)

        self.assertEqual(len(reply.image_paths), 2)
        self.assertIn("Showing images: 2 image(s)", reply.text)

    def test_spanish_plain_text_query_is_interpreted(self) -> None:
        self.service.handle_callback("language:set:es", chat_id=VIEWER_CHAT_ID)

        reply = self.service.handle_text_input("ensename 2 fotos de city de 2021", chat_id=VIEWER_CHAT_ID)

        self.assertEqual(len(reply.image_paths), 2)
        self.assertIn("imagen(es)", reply.text)

    def test_low_information_text_returns_clarification(self) -> None:
        reply = self.service.handle_text_input("show me photos", chat_id=VIEWER_CHAT_ID)

        self.assertIn("I need a little more detail", reply.text)
        labels = {button.label for row in reply.buttons for button in row}
        self.assertIn("Browse Years", labels)
        self.assertIn("Random Memory", labels)

    def test_people_add_and_show_commands(self) -> None:
        create_reply = self.service.handle_command("/people add Pablo", chat_id=OWNER_CHAT_ID)
        self.assertIn("Person created: Pablo", create_reply.text)

        alias_reply = self.service.handle_command(
            "/people alias Pablo | Pablito",
            chat_id=OWNER_CHAT_ID,
        )
        self.assertIn("Alias added: Pablo", alias_reply.text)

        link_reply = self.service.handle_command(
            "/people link Pablo | 2021/2021-08-15_city_trip",
            chat_id=OWNER_CHAT_ID,
        )
        self.assertIn("Person linked: Pablo", link_reply.text)

        show_reply = self.service.handle_command("/people show pablito", chat_id=VIEWER_CHAT_ID)
        self.assertIn("Person: Pablo", show_reply.text)
        self.assertIn("Pablito", show_reply.text)
        self.assertIn("2021/2021-08-15_city_trip", show_reply.text)

    def test_people_command_lists_people(self) -> None:
        self.service.handle_command("/people add Pablo", chat_id=OWNER_CHAT_ID)

        reply = self.service.handle_command("/people", chat_id=VIEWER_CHAT_ID)

        self.assertIn("Curated people:", reply.text)
        self.assertIn("Pablo", reply.text)

    def test_people_write_requires_admin(self) -> None:
        reply = self.service.handle_command("/people add Pablo", chat_id=VIEWER_CHAT_ID)

        self.assertEqual(reply.text, "Admin privileges are required for /people write commands.")

    def test_recent_search_can_be_pinned_resumed_and_unpinned(self) -> None:
        chat = VIEWER_CHAT_ID
        self.service.handle_command("/images 1 city", chat_id=chat)
        page = self.service.handle_callback("saved:recent:0", chat_id=chat)
        run, pin = page.buttons[0]
        self.assertIn("city", run.label)
        self.service.handle_callback(pin.callback_data, chat_id=chat)
        pinned = self.service.handle_callback("saved:pinned:0", chat_id=chat)
        run, unpin = pinned.buttons[0]
        self.assertIn("Unpin", unpin.label)
        self.assertTrue(self.service.handle_callback(run.callback_data, chat_id=chat).image_paths)
        self.assertFalse(self.service.handle_callback(run.callback_data, chat_id=OWNER_CHAT_ID).image_paths)
        self.service.handle_callback(unpin.callback_data, chat_id=chat)
        self.assertFalse(self.repository.list_saved_searches(chat, pinned_only=True))
        self.assertEqual(len(self.repository.list_saved_searches(chat)), 1)

    def test_plain_text_distinguishes_separate_years_from_an_inclusive_range(self) -> None:
        ambiguous = self.service.handle_text_input(
            "photos from 2019 or 2021", chat_id=VIEWER_CHAT_ID
        )
        self.assertIn("Which year", ambiguous.text)
        self.assertFalse(ambiguous.image_paths)
        folders = self.service.handle_text_input("show me folders", chat_id=VIEWER_CHAT_ID)
        self.assertIn("Which folders", folders.text)
        result = self.service.handle_text_input("photos from 2019–2021", chat_id=VIEWER_CHAT_ID)
        self.assertTrue(result.image_paths)
        self.assertIn("2019-2021", self.repository.list_saved_searches(VIEWER_CHAT_ID)[0].query)

    def test_people_wizard_adds_renames_links_and_unlinks(self) -> None:
        chat = OWNER_CHAT_ID

        def press(callback: str):
            return self.service.handle_callback(callback, chat_id=chat)

        def send(text: str):
            return self.service.handle_text_input(text, chat_id=chat)

        people = press("nav:people")
        self.assertIn("people:add", [button.callback_data for row in people.buttons for button in row])
        self.assertIn("display name", press("people:add").text)
        self.assertIn("Person created", send("Ana Original").text)
        person = self.service.app_service.get_person_detail("Ana Original")
        self.assertIsNotNone(person)
        person_id = person.id
        press(f"people:rename:{person_id}")
        self.assertIn("Ana Nueva", send("Ana Nueva").text)
        press(f"people:alias:{person_id}")
        self.assertIn("Ani", send("Ani").text)

        press(f"people:link:{person_id}")
        picker = send("city")
        choose = picker.buttons[0][0].callback_data
        self.assertTrue(choose.startswith("people:choose:"))
        self.assertIn("2021/2021-08-15_city_trip", press(choose).text)
        self.assertEqual(self.service.app_service.get_person_detail("Ani").folder_paths, ("2021/2021-08-15_city_trip",))
        self.assertIn("Unknown", press(choose).text)
        unlink = press(f"people:unlink:{person_id}").buttons[0][0].callback_data
        press(unlink)
        self.assertEqual(self.service.app_service.get_person_detail("Ani").folder_paths, ())

    def test_people_wizard_cancels_and_checks_current_role(self) -> None:
        admin = 9876
        self.repository.authorize_chat(admin, role="admin")
        self.service.handle_callback("people:add", chat_id=admin)
        self.service.handle_callback("people:list:0", chat_id=admin)
        self.service.handle_text_input("Nobody New", chat_id=admin)
        self.assertIsNone(self.service.app_service.get_person_detail("Nobody New"))

        self.service.handle_callback("people:add", chat_id=admin)
        self.repository.set_chat_role(admin, "viewer")
        attempted = self.service.handle_text_input("Still Nobody", chat_id=admin)
        self.assertIn("Admin privileges", attempted.text)
        self.assertIsNone(self.service.app_service.get_person_detail("Still Nobody"))
        viewer_menu = self.service.handle_callback("nav:people", chat_id=admin)
        self.assertFalse(any(button.callback_data == "people:add" for row in viewer_menu.buttons for button in row))

    def test_images_command_supports_people_alias_and_year_range(self) -> None:
        self.service.handle_command("/people add Pablo", chat_id=OWNER_CHAT_ID)
        self.service.handle_command("/people alias Pablo | Pablito", chat_id=OWNER_CHAT_ID)
        self.service.handle_command(
            "/people link Pablo | 2021/2021-08-15_city_trip",
            chat_id=OWNER_CHAT_ID,
        )

        reply = self.service.handle_command("/images 2 pablito 2020-2021", chat_id=VIEWER_CHAT_ID)

        self.assertEqual(len(reply.image_paths), 2)
        self.assertIn('person="Pablo"', reply.text)
        self.assertIn("year_range=2020-2021", reply.text)

    def test_more_returns_additional_images_from_same_scope(self) -> None:
        first = self.service.handle_command("/images 1 city", chat_id=VIEWER_CHAT_ID)
        second = self.service.handle_command("/more 1", chat_id=VIEWER_CHAT_ID)

        self.assertEqual(len(first.image_paths), 1)
        self.assertEqual(len(second.image_paths), 1)
        self.assertNotEqual(first.image_paths[0], second.image_paths[0])
        self.assertIn("More images", second.text)

    def test_same_folder_callback_returns_additional_images(self) -> None:
        first = self.service.handle_command("/images 1 city", chat_id=VIEWER_CHAT_ID)
        second = self.service.handle_callback("nav:same_folder", chat_id=VIEWER_CHAT_ID)

        self.assertEqual(len(first.image_paths), 1)
        self.assertEqual(len(second.image_paths), 1)
        self.assertNotEqual(first.image_paths[0], second.image_paths[0])
        self.assertIn("Same folder", second.text)

    def test_same_year_callback_returns_images(self) -> None:
        self.service.handle_command("/images 1 city", chat_id=VIEWER_CHAT_ID)
        reply = self.service.handle_callback("nav:same_year", chat_id=VIEWER_CHAT_ID)

        self.assertGreaterEqual(len(reply.image_paths), 1)
        self.assertIn("Same year", reply.text)

    def test_back_callback_restores_previous_view(self) -> None:
        first = self.service.handle_command("/images 1 city", chat_id=VIEWER_CHAT_ID)
        self.service.handle_callback("nav:same_year", chat_id=VIEWER_CHAT_ID)
        back = self.service.handle_callback("nav:back", chat_id=VIEWER_CHAT_ID)

        self.assertEqual(back.image_paths, first.image_paths)
        self.assertEqual(back.text, first.text)

    def test_refine_callback_returns_text(self) -> None:
        self.service.handle_command("/images 2 city", chat_id=VIEWER_CHAT_ID)
        reply = self.service.handle_callback("nav:refine", chat_id=VIEWER_CHAT_ID)

        self.assertIn("Refine this search:", reply.text)
        self.assertIn("/images", reply.text)

    def test_mixed_folder_batch_discloses_folder_breakdown(self) -> None:
        reply = self.service.handle_command("/images 4 summer", chat_id=VIEWER_CHAT_ID)

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
        self.service.handle_command("/images 4 summer", chat_id=VIEWER_CHAT_ID)
        reply = self.service.handle_callback("nav:folders", chat_id=VIEWER_CHAT_ID)

        self.assertIn("Choose a folder from this batch:", reply.text)
        labels = [button.label for row in reply.buttons for button in row]
        self.assertIn("2021/2021-08-15_city_trip (2)", labels)
        self.assertIn("2019/2019-07-10_beach_day (2)", labels)

    def test_folder_selection_continues_with_more_from_that_folder(self) -> None:
        self.service.handle_command("/images 3 summer", chat_id=VIEWER_CHAT_ID)
        self.service.handle_callback("nav:folders", chat_id=VIEWER_CHAT_ID)
        reply = self.service.handle_callback("nav:folder:1", chat_id=VIEWER_CHAT_ID)

        self.assertEqual(len(reply.image_paths), 1)
        self.assertIn("More from 2019/2019-07-10_beach_day", reply.text)

    def test_more_from_folder_picker_requires_returning_to_images(self) -> None:
        self.service.handle_command("/images 4 summer", chat_id=VIEWER_CHAT_ID)
        self.service.handle_callback("nav:folders", chat_id=VIEWER_CHAT_ID)
        reply = self.service.handle_command("/more 1", chat_id=VIEWER_CHAT_ID)

        self.assertIn("Current view is not an image batch", reply.text)

    def test_more_requires_previous_image_context(self) -> None:
        reply = self.service.handle_command("/more 1", chat_id=VIEWER_CHAT_ID)
        self.assertIn("No previous image search", reply.text)

    def test_session_is_persisted_for_navigation(self) -> None:
        self.service.handle_command("/images 2 city", chat_id=VIEWER_CHAT_ID)

        raw_session = self.repository.get_chat_session(VIEWER_CHAT_ID)

        self.assertIsNotNone(raw_session)
        session = ChatSession.from_json(raw_session)
        self.assertIsNotNone(session.current)
        self.assertEqual(session.current.scope, "search_images")

    def test_invite_list_shows_active_invites(self) -> None:
        create_reply = self.service.handle_command("/invite viewer 5", chat_id=OWNER_CHAT_ID)
        code = next(
            line.split(": ", 1)[1]
            for line in create_reply.text.splitlines()
            if line.startswith("Code: ")
        )

        reply = self.service.handle_command("/invite list", chat_id=OWNER_CHAT_ID)

        self.assertIn("Active invites:", reply.text)
        self.assertIn(code, reply.text)
        self.assertIn("role=viewer", reply.text)

    def test_admin_list_omits_owner_only_invites(self) -> None:
        self.repository.authorize_chat(9876, role="admin")
        admin_invite = self.repository.create_invite("admin", created_by_chat_id=OWNER_CHAT_ID)
        viewer_invite = self.repository.create_invite("viewer", created_by_chat_id=9876)

        reply = self.service.handle_command("/invite list", chat_id=9876)

        self.assertIn(viewer_invite.code, reply.text)
        self.assertNotIn(admin_invite.code, reply.text)

    def test_owner_can_revoke_admin_invite(self) -> None:
        create_reply = self.service.handle_command("/invite admin 5", chat_id=OWNER_CHAT_ID)
        code = next(
            line.split(": ", 1)[1]
            for line in create_reply.text.splitlines()
            if line.startswith("Code: ")
        )

        reply = self.service.handle_command(f"/invite revoke {code}", chat_id=OWNER_CHAT_ID)

        self.assertIn("Invite revoked.", reply.text)
        self.assertIn(code, reply.text)

    def test_viewer_cannot_create_or_revoke_invites(self) -> None:
        create_reply = self.service.handle_command("/invite viewer 5", chat_id=VIEWER_CHAT_ID)
        self.assertEqual(create_reply.text, "Admin privileges are required for /invite.")

        owner_reply = self.service.handle_command("/invite viewer 5", chat_id=OWNER_CHAT_ID)
        code = next(
            line.split(": ", 1)[1]
            for line in owner_reply.text.splitlines()
            if line.startswith("Code: ")
        )
        revoke_reply = self.service.handle_command(f"/invite revoke {code}", chat_id=VIEWER_CHAT_ID)
        self.assertEqual(revoke_reply.text, "Admin privileges are required for /invite revoke.")

    def test_owner_can_change_dynamic_chat_role(self) -> None:
        self.service.handle_command("/login 246810", chat_id=5678, username="viewer")

        reply = self.service.handle_command("/authorized role 5678 admin", chat_id=OWNER_CHAT_ID)

        self.assertIn("Chat role updated.", reply.text)
        self.assertEqual(self.repository.get_chat_role(5678), "admin")

    def test_owner_can_assign_owner_role_to_dynamic_chat(self) -> None:
        self.service.handle_command("/login 246810", chat_id=5678)

        reply = self.service.handle_command("/authorized role 5678 owner", chat_id=OWNER_CHAT_ID)

        self.assertIn("Role: owner", reply.text)
        self.assertEqual(self.repository.get_chat_role(5678), "owner")

    def test_admin_role_change_requires_owner(self) -> None:
        self.service.handle_command("/login 246810", chat_id=5678)
        self.repository.authorize_chat(7777, role="admin")

        reply = self.service.handle_command("/authorized role 5678 admin", chat_id=7777)

        self.assertEqual(reply.text, "Owner privileges are required for /authorized role.")

    def test_admin_can_revoke_viewer_but_not_admin(self) -> None:
        self.repository.authorize_chat(7777, role="admin")
        self.service.handle_command("/login 246810", chat_id=5678)
        self.repository.authorize_chat(6789, role="admin")

        viewer_reply = self.service.handle_command("/authorized revoke 5678", chat_id=7777)
        admin_reply = self.service.handle_command("/authorized revoke 6789", chat_id=7777)

        self.assertEqual(viewer_reply.text, "Chat access revoked for 5678.")
        self.assertFalse(self.repository.is_chat_authorized(5678))
        self.assertEqual(admin_reply.text, "Owner privileges are required to revoke admin access.")
        self.assertTrue(self.repository.is_chat_authorized(6789))

    def test_authorized_list_includes_static_and_dynamic_auth_modes(self) -> None:
        self.service.handle_command("/login 246810", chat_id=5678, username="guest")

        reply = self.service.handle_command("/authorized", chat_id=OWNER_CHAT_ID)

        self.assertIn(f"- {VIEWER_CHAT_ID}: role=viewer, auth_mode=static_viewer", reply.text)
        self.assertIn(f"- {OWNER_CHAT_ID}: role=owner, auth_mode=static_owner", reply.text)
        self.assertIn("- 5678: role=viewer, auth_mode=dynamic, username=guest", reply.text)

    def test_static_chat_cannot_be_role_changed_or_revoked(self) -> None:
        role_reply = self.service.handle_command(
            f"/authorized role {VIEWER_CHAT_ID} admin",
            chat_id=OWNER_CHAT_ID,
        )
        revoke_reply = self.service.handle_command(
            f"/authorized revoke {VIEWER_CHAT_ID}",
            chat_id=OWNER_CHAT_ID,
        )

        self.assertEqual(role_reply.text, "Static chats cannot be role-changed.")
        self.assertEqual(revoke_reply.text, "Static chats cannot be revoked.")

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
        image_file = app._open_image("2021/folder/IMG_001.jpg")

        self.assertIsInstance(image_file, BytesIO)
        self.assertEqual(image_file.read(), b"remote-image")
        self.assertEqual(image_file.name, "IMG_001.jpg")
        self.assertEqual(fetched_paths, ["2021/folder/IMG_001.jpg"])
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
                "2021/folder/IMG_001.jpg",
                "2021/folder/IMG_002.jpg",
            )
        )

        self.assertEqual(fetched_batches, [("2021/folder/IMG_001.jpg", "2021/folder/IMG_002.jpg")])
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
        self.assertIn("settings", commands)
        callback_handlers = [
            handler
            for handlers in app.handlers.values()
            for handler in handlers
            if handler.__class__.__name__ == "CallbackQueryHandler"
        ]
        self.assertTrue(callback_handlers)

    def test_settings_reports_current_language(self) -> None:
        self.service.handle_callback("language:set:es", chat_id=VIEWER_CHAT_ID)

        reply = self.service.handle_command("/settings", chat_id=VIEWER_CHAT_ID)

        self.assertIn("Idioma actual: Español", reply.text)
        labels = {button.label for row in reply.buttons for button in row}
        self.assertIn("Cambiar idioma", labels)
