package org.chromantis.android

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class AlbumMetadataTest {
    @Test
    fun readsNumericYearInIndex() {
        val item = JSONObject("""{"year":2024,"folders":7}""")

        assertEquals(Entry("2024", "2024", albumCount = 7), yearEntry(item))
    }

    @Test
    fun readsPhotoRevisionAndAcceptsServersWithoutIt() {
        val item = JSONObject("""{"path":"2024/trip/photo.jpg","identity":"revision-one"}""")
        assertEquals("revision-one", photoEntry(item).identity)
        item.put("identity", "revision-two")
        assertEquals("revision-two", photoEntry(item).identity)
        item.remove("identity")
        assertNull(photoEntry(item).identity)
    }

    @Test
    fun displaysTheBestKnownAlbumDate() {
        assertEquals(
            "2024-07-01",
            albumDate(JSONObject("""{"event_date":"2024-07-01","year":2024}""")),
        )
        assertEquals("2024", albumDate(JSONObject("""{"event_date":null,"year":2024}""")))
        assertNull(albumDate(JSONObject("""{"event_date":null,"year":null}""")))
    }
}
