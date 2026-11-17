package org.chromantis.android

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class AlbumSearchFiltersTest {
    @Test
    fun preservesTheServerQueriesForRemovingOnlyOneFilter() {
        val response =
            JSONObject(
                """
                {
                  "items": [],
                  "filters": {
                    "q": "playa years:1000-2019 person:4",
                    "text": "playa",
                    "active": [
                      {"kind": "year", "label": "≤ 2019", "without": "playa person:4"},
                      {"kind": "person", "label": "Ana", "without": "playa years:1000-2019"}
                    ]
                  }
                }
                """
                    .trimIndent()
            )

        assertEquals(
            AlbumSearchFilters(
                "playa",
                listOf(
                    AlbumFilter("year", "≤ 2019", "playa person:4"),
                    AlbumFilter("person", "Ana", "playa years:1000-2019"),
                ),
            ),
            albumSearchFilters(response),
        )
    }

    @Test
    fun supportsAnEmptyQueryAfterTheLastFilterIsRemoved() {
        val response =
            JSONObject(
                """
                {"filters": {"text": "", "active": [{"kind": "album", "label": "Playa", "without": ""}]}}
                """
                    .trimIndent()
            )

        assertEquals("", albumSearchFilters(response)?.active?.single()?.without)
    }

    @Test
    fun acceptsResponsesFromServersWithoutFilterMetadata() {
        assertNull(albumSearchFilters(JSONObject("""{"items": []}""")))
    }
}
