package org.chromantis.android

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class WorkspaceTest {
    @Test
    fun appearancePreferenceCanOverrideOrFollowAndroid() {
        assertTrue(Appearance.fromPreference("DARK").isDark(systemDark = false))
        assertFalse(Appearance.fromPreference("LIGHT").isDark(systemDark = true))
        assertTrue(Appearance.fromPreference(null).isDark(systemDark = true))
        assertFalse(Appearance.fromPreference("unknown").isDark(systemDark = false))
    }

    @Test
    fun searchRefinementKeepsTheServerQueryOrAlbumChoices() {
        assertEquals(
            AlbumRefinement("playa 2020", emptyList()),
            albumRefinement(JSONObject("""{"q":"playa 2020","choices":[]}""")),
        )
        assertEquals(
            AlbumRefinement(null, listOf(Entry("Playa", "2024/playa"))),
            albumRefinement(
                JSONObject("""{"q":null,"choices":[{"title":"Playa","path":"2024/playa"}]}""")
            ),
        )
    }
}
