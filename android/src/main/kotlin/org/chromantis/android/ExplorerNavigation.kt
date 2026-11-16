package org.chromantis.android

import org.json.JSONObject

internal data class AlbumResume(val year: Page, val album: Page, val offset: Int) {
    fun encode(): String =
        JSONObject()
            .put("yearTitle", year.title)
            .put("yearQuery", year.path)
            .put("albumTitle", album.title)
            .put("albumPath", album.path)
            .put("offset", offset)
            .toString()

    companion object {
        fun decode(value: String?): AlbumResume? =
            value?.let {
                runCatching {
                        val record = JSONObject(it)
                        val year = record.getString("yearQuery")
                        val path = record.getString("albumPath")
                        val offset = record.getInt("offset")
                        require(year.isNotBlank() && path.isNotBlank() && offset >= 0)
                        AlbumResume(
                            Page(Level.ALBUMS, record.getString("yearTitle"), year),
                            Page(Level.PHOTOS, record.getString("albumTitle"), path),
                            offset,
                        )
                    }
                    .getOrNull()
            }
    }
}

internal fun folderAncestors(pages: List<Page>): List<Page> {
    val level = pages.last().level
    return if (
        pages.first().level == Level.YEARS &&
            level in listOf(Level.ALBUMS, Level.PHOTOS, Level.ORIGINAL)
    ) {
        pages.dropLast(1).takeWhile { it.level in listOf(Level.YEARS, Level.ALBUMS, Level.PHOTOS) }
    } else {
        emptyList()
    }
}

internal fun albumResume(pages: List<Page>, offset: Int): AlbumResume? {
    val (root, year, album) = pages.takeIf { it.size == 3 } ?: return null
    return if (
        root.level == Level.YEARS &&
            year.level == Level.ALBUMS &&
            year.path != null &&
            album.level == Level.PHOTOS &&
            album.path != null
    ) {
        AlbumResume(year, album, offset)
    } else {
        null
    }
}
