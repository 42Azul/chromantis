package org.chromantis.android

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class TagCatalogTest {
    @Test
    fun keepsLabelsCountsAndNextOffset() {
        val page =
            decodeTagCatalog(
                JSONObject("""{"items":[{"tag":"2024-07","count":2}],"next_offset":30}""")
            )
        assertEquals(TagCatalogPage(listOf(CatalogTag("2024-07", 2)), 30), page)
    }

    @Test
    fun emptyFinalPageHasNoNextOffset() {
        val page = decodeTagCatalog(JSONObject("""{"items":[],"next_offset":null}"""))
        assertEquals(TagCatalogPage(emptyList(), null), page)
    }
}
