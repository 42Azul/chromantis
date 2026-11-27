package org.chromantis.android

import org.json.JSONArray
import org.json.JSONObject

internal data class PhotoSearchBookmark(val tag: String, val person: String, val year: Int?) {
    fun encode(): String =
        JSONObject().put("tag", tag).put("person", person).put("year", year).toString()

    companion object {
        fun decode(value: String?): PhotoSearchBookmark? =
            value?.let {
                runCatching {
                        val json = JSONObject(it)
                        val tag = json.getString("tag")
                        val person = json.getString("person")
                        val year = if (json.has("year")) json.getInt("year") else null
                        PhotoSearchBookmark(tag, person, year)
                    }
                    .getOrNull()
            }
    }
}

internal fun decodePhotoSearchBookmarks(value: String?): List<PhotoSearchBookmark> {
    if (value == null) return emptyList()
    return runCatching {
            if (value.startsWith("{")) {
                listOfNotNull(PhotoSearchBookmark.decode(value))
            } else {
                val array = JSONArray(value)
                (0 until minOf(array.length(), 3)).mapNotNull {
                    PhotoSearchBookmark.decode(array.optString(it))
                }
            }
        }
        .getOrDefault(emptyList())
        .distinct()
}

internal fun List<PhotoSearchBookmark>.encodePhotoSearchBookmarks(): String =
    JSONArray(map { JSONObject(it.encode()) }).toString()

internal fun List<PhotoSearchBookmark>.updatePhotoSearchBookmark(
    bookmark: PhotoSearchBookmark,
    remove: Boolean,
): List<PhotoSearchBookmark> {
    val others = filterNot { it == bookmark }
    return if (remove) others else (listOf(bookmark) + others).take(3)
}
