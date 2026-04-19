from __future__ import annotations

import unittest

from chromantis.bot.i18n import catalog_keys


class I18nCatalogTests(unittest.TestCase):
    def test_catalogs_expose_the_same_keys(self) -> None:
        keys = catalog_keys()
        self.assertEqual(keys["en"], keys["es"])
