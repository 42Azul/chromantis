from __future__ import annotations

import unittest

from chromantis.db.repository import ResolvedPerson
from chromantis.search.query_parser import QueryParseError, parse_query


class QueryParserTests(unittest.TestCase):
    def test_parse_single_year_and_keywords(self) -> None:
        query = parse_query("2019 beach dinner")

        self.assertEqual(query.year_from, 2019)
        self.assertEqual(query.year_to, 2019)
        self.assertEqual(query.keywords, ("beach", "dinner"))

    def test_parse_year_range(self) -> None:
        query = parse_query("2018-2021 beach")

        self.assertEqual(query.year_from, 2018)
        self.assertEqual(query.year_to, 2021)
        self.assertEqual(query.keywords, ("beach",))

    def test_parse_rejects_reversed_year_range(self) -> None:
        with self.assertRaises(QueryParseError):
            parse_query("2021-2018 beach")

    def test_parse_people_aliases_before_keywords(self) -> None:
        query = parse_query(
            "Pablo beach summer",
            alias_map={
                "pablo": ResolvedPerson(id=1, display_name="Pablo"),
                "summer": ResolvedPerson(id=2, display_name="Summer Person"),
            },
        )

        self.assertEqual(query.person_ids, (1, 2))
        self.assertEqual(query.keywords, ("beach",))

    def test_parse_multi_word_alias(self) -> None:
        query = parse_query(
            "tio pepe beach",
            alias_map={
                "tio pepe": ResolvedPerson(id=3, display_name="Pepe"),
            },
        )

        self.assertEqual(query.person_ids, (3,))
        self.assertEqual(query.keywords, ("beach",))
