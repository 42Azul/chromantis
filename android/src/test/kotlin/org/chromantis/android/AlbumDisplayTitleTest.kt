package org.chromantis.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class AlbumDisplayTitleTest {
    @Test
    fun displayDropsOnlyAFullLeadingDateAndKeepsTheIndexedNameIntact() {
        val original = "2023-10-05_excursion"
        assertEquals("Excursion", albumDisplayTitle(original))
        assertEquals("2023-10-05_excursion", original)
        assertEquals("Ana y Luis", albumDisplayTitle("Ana_y_Luis"))
        assertEquals("2023", albumDisplayTitle("2023"))
        assertEquals("2023 Summer", albumDisplayTitle("2023 Summer"))
    }

    @Test
    fun onlyValidFolderDatesBecomeDateCaptions() {
        assertNotNull(albumDisplayDate("2023/2023-10-05_excursion"))
        assertNull(albumDisplayDate("2023/2023-99-05_excursion"))
        assertNull(albumDisplayDate("2023/Ana_y_Luis"))
    }
}
