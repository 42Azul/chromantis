package org.chromantis.android

import androidx.compose.runtime.saveable.SaverScope
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
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

    @Test
    fun folderTrailLinksToTheOriginalAncestorsAndLeavesSearchAlone() {
        val root = Page(Level.YEARS, "Carpetas")
        val year = Page(Level.ALBUMS, "2024", "2024")
        val album = Page(Level.PHOTOS, "Playa", "2024/playa")
        val photo = Page(Level.ORIGINAL, "first.jpg", "2024/playa/first.jpg")

        assertEquals(listOf(root, year), folderAncestors(listOf(root, year, album)))
        assertEquals(listOf(root, year, album), folderAncestors(listOf(root, year, album, photo)))
        assertEquals(
            emptyList<Page>(),
            folderAncestors(listOf(Page(Level.ASK, "Buscar"), album, photo)),
        )
    }

    @Test
    fun resumeKeepsTheListedYearAndGalleryPageEvenWhenPathHasAnotherYear() {
        val year = Page(Level.ALBUMS, "2023", "2023")
        val album = Page(Level.PHOTOS, "Playa", "2024/playa")
        val selection = listOf(Page(Level.YEARS, "Carpetas"), year, album)
        val saved = albumResume(selection, ChromantisApi.pageSize)

        assertEquals(AlbumResume(year, album, 30), saved)
        assertEquals(saved, AlbumResume.decode(saved?.encode()))
        assertNull(AlbumResume.decode("""{"albumPath":"2024/playa"}"""))
        assertNull(albumResume(listOf(Page(Level.ASK, "Buscar"), album), 30))
    }
}
