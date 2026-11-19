from __future__ import annotations

import json
import tempfile
import unittest
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode

from chromantis.api.server import ApiServer, make_api_handler
from chromantis.app import ApplicationService
from chromantis.app.recall import RefinementError
from chromantis.bot.telegram_bot import TelegramBotService
from chromantis.db.repository import Repository
from chromantis.parsing.path_parser import PathParser
from chromantis.search.query_parser import split_recall
from chromantis.source import ArchiveScanner, LocalArchiveSource


OLD = "2019/2019-08-02_playa_norte"
SECOND = '2018/2018-07-01_playa "sur"'
BOUNDARY = "2020/2020-08-02_playa_verano"
UNLINKED = "2018/2018-06-23_playa_ana"


class GuidedRecallTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.archive = Path(temp.name) / "photos"
        for album in (OLD, SECOND, BOUNDARY, UNLINKED):
            image = self.archive / album / "fixture.jpg"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"synthetic photo")
        self.repository = Repository(str(Path(temp.name) / "index.db"))
        self.repository.init_schema()
        ArchiveScanner(LocalArchiveSource(str(self.archive)), self.repository, PathParser()).scan()
        self.app = ApplicationService(self.repository, static_owner_chat_ids=(1,), static_viewer_chat_ids=(2,))
        person = self.app.create_person("Ana")
        self.app.add_person_alias(person.id, "Ani")
        for path in (OLD, SECOND, BOUNDARY):
            self.app.link_person_to_folder(person.id, path)
        for path in (OLD, SECOND, BOUNDARY):
            item = self.app.get_album_review(1, path=path)
            self.app.edit_album_context(1, path, item["id"], item["context_revision"], {"aliases": ["Verano"]})

    def test_year_person_and_album_intersect_and_keep_literal_quotes(self):
        base = "playa con Ana"
        self.assertEqual(len(self.app.search_folders(base)), 4)
        year = self.app.refine_query(base, "antes de 2020").query
        self.assertEqual(len(self.app.search_folders(year)), 3)
        person = self.app.refine_query(year, "con Ani").query
        self.assertEqual({item.path for item in self.app.search_folders(person)}, {OLD, SECOND})
        self.assertEqual(self.app.refine_query(person, "with Ana").query, person)
        options = self.app.refine_query(person, "álbum Verano")
        self.assertIsNone(options.query)
        self.assertEqual({item.path for item in options.choices}, {OLD, SECOND})
        chosen = self.app.refine_query(person, f"album {SECOND}").query
        self.assertEqual(split_recall(chosen)[1].album, SECOND)
        self.assertEqual([item.folder_path for item in self.app.search_images(chosen)], [SECOND])
        with self.assertRaisesRegex(RefinementError, "does not overlap"):
            self.app.refine_query(chosen, "only 2020")
        with self.assertRaises(RefinementError):
            self.app.refine_query(chosen, "with Unknown")

    def test_person_lists_intersect_links_and_reuse_aliases_without_partial_filters(self):
        luis = self.app.create_person("Luis")
        self.app.add_person_alias(luis.id, "Lucho")
        self.app.add_person_alias(luis.id, "tío Luis")
        self.app.link_person_to_folder(luis.id, OLD)
        self.app.link_person_to_folder(luis.id, UNLINKED)
        self.archive.rename(self.archive.with_name("disconnected"))
        for request in ("con Ani y Lucho", "with Ana and Luis", "con Ana, Lucho", "con Ana e Luis", "con Ana y tío Luis"):
            with self.subTest(request=request):
                query = self.app.refine_query("playa", request).query
                self.assertEqual({item.path for item in self.app.search_folders(query)}, {OLD})
                self.assertEqual({item.folder_path for item in self.app.search_images(query)}, {OLD})
                self.assertEqual(len(split_recall(query)[1].people), 2)
                self.assertEqual(self.app.refine_query(query, "con Lucho y Ana").query, query)
        duplicate = self.app.refine_query("playa", "con Ana, Luis y Lucho").query
        self.assertEqual(len(split_recall(duplicate)[1].people), 2)
        spoken = "fotos de la playa con Ani y Lucho antes de 2020"
        self.assertEqual({item.path for item in self.app.search_folders(spoken)}, {OLD})
        for invalid in ("con Ana y Unknown", "con Ana,,Luis", "con Ana o Luis"):
            with self.subTest(request=invalid), self.assertRaises(RefinementError):
                self.app.refine_query("playa", invalid)
        with self.assertRaisesRegex(RefinementError, "Unknown"):
            self.app.search_folders("fotos de la playa con Ana y Unknown antes de 2020")
        bot = TelegramBotService(self.app)
        self.app.set_chat_language(1, "es", actor_chat_id=1)
        bot.handle_command("/folders playa", chat_id=1)
        reply = bot.handle_text_input("con Ani y Lucho", chat_id=1)
        self.assertIn(OLD, reply.text)
        self.assertNotIn(SECOND, reply.text)
        self.assertNotIn(UNLINKED, reply.text)
        saved = self.repository.list_saved_searches(1, limit=1)[0].query
        bot.handle_text_input("con Ana y Unknown", chat_id=1)
        self.assertEqual(self.repository.list_saved_searches(1, limit=1)[0].query, saved)


    def test_an_exact_alias_containing_a_list_separator_stays_one_person(self):
        person = self.app.create_person("María")
        self.app.add_person_alias(person.id, "María y compañía")
        self.app.link_person_to_folder(person.id, SECOND)
        query = self.app.refine_query("playa", "con María y compañía").query
        self.assertEqual(split_recall(query)[1].people, (person.id,))
        self.assertEqual([item.path for item in self.app.search_folders(query)], [SECOND])

    def test_refinement_layer_cannot_bypass_person_filters_with_an_exact_alias(self):
        item = self.app.get_album_review(1, path=UNLINKED)
        self.app.edit_album_context(1, UNLINKED, item["id"], item["context_revision"],
                                    {"aliases": ["Verano de Ana 2018"]})
        # Exact metadata can match while the added person condition still requires a link.
        refined = self.app.refine_query("Verano de Ana 2018", "con Ana").query
        self.assertEqual(self.app.search_folders(refined), [])
        self.assertEqual(self.app.search_images(refined), [])

    def test_telegram_reuses_and_saves_the_previous_search(self):
        bot = TelegramBotService(self.app)
        self.app.set_chat_language(1, "es", actor_chat_id=1)
        self.assertIn("Busca fotos", bot.handle_text_input("antes de 2020", chat_id=1).text)
        self.assertIn(BOUNDARY, bot.handle_command("/folders playa con Ana", chat_id=1).text)
        self.assertNotIn(BOUNDARY, bot.handle_text_input("antes de 2020", chat_id=1).text)
        choice = bot.handle_command("/refine album Verano", chat_id=1)
        self.assertIn("¿A qué álbum te refieres?", choice.text)
        self.assertIn(OLD, choice.text)
        self.assertNotIn(BOUNDARY, choice.text)
        selected = bot.handle_command(f"/refine album {OLD}", chat_id=1)
        self.assertIn(OLD, selected.text)
        self.assertNotIn(SECOND, selected.text)
        self.assertIn("search", bot.handle_text_input("before 2020", chat_id=2).text)
        saved, = self.repository.list_saved_searches(1, limit=1)
        self.assertEqual(split_recall(saved.query)[1].album, OLD)
        self.assertIsNotNone(self.app.set_search_pinned(1, saved.id, True))
        self.assertEqual(self.repository.list_saved_searches(1, pinned_only=True)[0].query, saved.query)

    def test_family_api_refines_and_lists_only_authorized_results(self):
        self.archive.rename(self.archive.with_name("disconnected"))
        identity, code = self.app.family_access.invite("synthetic")
        cookie = "chromantis_family=" + self.app.family_access.redeem(code)
        server = ApiServer(("127.0.0.1", 0), make_api_handler(self.app, api_chat_tokens=((1, "owner-fixture"),)))
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)

        def request(method, path, body=None, *, with_cookie=True):
            http = HTTPConnection(*server.server_address, timeout=2)
            try:
                headers = {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{server.server_port}"}
                if with_cookie:
                    headers["Cookie"] = cookie
                http.request(method, "/api/v1" + path, json.dumps(body) if body else None, headers)
                response = http.getresponse()
                return response.status, json.loads(response.read())
            finally:
                http.close()

        spoken_query = "fotos de la playa con Ani antes de 2020"
        status, albums = request("GET", "/folders?" + urlencode({"q": spoken_query}))
        self.assertEqual(status, 200)
        self.assertEqual({row["path"] for row in albums["items"]}, {OLD, SECOND})
        self.assertNotIn("filters", albums)

        def filtered(query):
            status, response = request("GET", "/folders?" + urlencode({"q": query, "filters": 1}))
            self.assertEqual(status, 200)
            return {row["path"] for row in response["items"]}, response["filters"]

        paths, filters = filtered(spoken_query)
        self.assertEqual(paths, {OLD, SECOND})
        self.assertEqual(filters["text"], "playa")
        year, person = filters["active"]
        self.assertEqual((year["kind"], year["label"]), ("year", "≤ 2019"))
        self.assertEqual((person["kind"], person["label"]), ("person", "Ana"))
        self.assertEqual(filtered(year["without"])[0], {OLD, SECOND, BOUNDARY})
        self.assertEqual(filtered(person["without"])[0], {OLD, SECOND, UNLINKED})

        luis = self.app.create_person("Luis")
        self.app.add_person_alias(luis.id, "Lucho")
        self.app.link_person_to_folder(luis.id, OLD)
        status, together = request("POST", "/refine", {"q": "playa", "text": "con Ani y Lucho"})
        self.assertEqual(status, 200)
        together_paths, together_filters = filtered(together["q"])
        self.assertEqual(together_paths, {OLD})
        self.assertEqual([item["label"] for item in together_filters["active"]], ["Ana", "Luis"])
        self.assertEqual(filtered(together_filters["active"][1]["without"])[0], {OLD, SECOND, BOUNDARY})
        status, error = request("POST", "/refine", {"q": "playa", "text": "con Ana y Unknown"})
        self.assertEqual((status, error["code"]), (400, "person"))

        narrowed = self.app.refine_query(spoken_query, f"álbum {OLD}").query
        paths, selected = filtered(narrowed)
        self.assertEqual(paths, {OLD})
        album = selected["active"][-1]
        self.assertEqual(album["kind"], "album")
        self.assertEqual(filtered(album["without"])[0], {OLD, SECOND})
        status, narrowed = request("POST", "/refine", {"q": spoken_query, "text": "solo 2019"})
        self.assertEqual(status, 200)
        status, albums = request("GET", "/folders?" + urlencode({"q": narrowed["q"]}))
        self.assertEqual(status, 200)
        self.assertEqual([row["path"] for row in albums["items"]], [OLD])
        status, conflict = request("POST", "/refine", {"q": spoken_query, "text": "solo 2020"})
        self.assertEqual((status, conflict["code"]), (400, "year_conflict"))

        later = "álbumes de playa con Ana después de 2019"
        status, albums = request("GET", "/folders?" + urlencode({"q": later}))
        self.assertEqual(status, 200)
        self.assertEqual([row["path"] for row in albums["items"]], [BOUNDARY])
        unknown = "fotos de la playa con Alguien antes de 2020"
        status, error = request("GET", "/folders?" + urlencode({"q": unknown}))
        self.assertEqual((status, error["code"]), (400, "person"))

        body = {"q": "playa", "text": "antes de 2020"}
        self.assertEqual(request("POST", "/refine", body, with_cookie=False)[0], 401)
        status, data = request("POST", "/refine", body)
        self.assertEqual(status, 200)
        status, folders = request("GET", "/folders?" + urlencode({"q": data["q"]}))
        self.assertEqual(status, 200)
        self.assertNotIn(BOUNDARY, [row["path"] for row in folders["items"]])
        self.app.family_access.revoke(identity)
        self.assertEqual(request("POST", "/refine", body)[0], 401)


if __name__ == "__main__":
    unittest.main()
