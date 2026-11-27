package org.chromantis.android

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
