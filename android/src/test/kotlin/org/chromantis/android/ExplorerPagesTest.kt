package org.chromantis.android

import androidx.compose.runtime.saveable.SaverScope
import org.junit.Assert.assertEquals
import org.junit.Test

class ExplorerPagesTest {
    @Test
    fun restoresSearchAndGalleryWhenRecreatingTheActivity() {
        val albumPath = "2024/2024-08-04_playa"
        val pages =
            listOf(
                Page(Level.YEARS, "Carpetas"),
                Page(Level.SEARCH, "Resultados", "Ana y José"),
                Page(Level.PHOTOS, "Playa", albumPath),
                Page(Level.ORIGINAL, "Foto 31.jpg", "$albumPath/Foto 31.jpg"),
            )
        val saved = with(explorerPagesSaver) { SaverScope { it is String }.save(pages) }

        val restored = requireNotNull(explorerPagesSaver.restore(requireNotNull(saved)))
        assertEquals(pages, restored)
        assertEquals(albumPath, restored.dropLast(1).last().path)
    }

    @Test
    fun restoresTheAlbumReviewQueueWithoutASelectedPath() {
        val pages = listOf(Page(Level.YEARS, "Carpetas"), Page(Level.REVIEW, "Etiquetar álbumes"))
        val saved = with(explorerPagesSaver) { SaverScope { it is String }.save(pages) }

        assertEquals(pages, explorerPagesSaver.restore(requireNotNull(saved)))
    }
}
