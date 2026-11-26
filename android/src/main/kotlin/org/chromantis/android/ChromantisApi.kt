package org.chromantis.android

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.LruCache
import java.io.IOException
import java.net.URI
import java.net.URLEncoder
import java.util.Locale
import javax.net.ssl.HttpsURLConnection
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

internal data class Entry(
    val title: String,
    val path: String,
    val albumCount: Int? = null,
    val identity: String? = null,
)

internal data class EntryPage(
    val entries: List<Entry>,
    val nextOffset: Int? = null,
    val hasThumbnails: Boolean = false,
    val searchFilters: AlbumSearchFilters? = null,
)

internal data class Person(val id: Long, val name: String, val aliases: List<String>)

internal data class TaggedPhoto(
    val path: String,
    val identity: String,
    val people: Set<Long>,
    val tags: Set<String>,
)

internal data class AlbumSearchFilters(val text: String, val active: List<AlbumFilter>)

internal data class AlbumFilter(val kind: String, val label: String, val without: String)

internal data class AlbumRefinement(val query: String?, val choices: List<Entry>)

internal data class Suggestion(
    val key: String,
    val label: String,
    val evidence: String,
    val state: String,
    val tag: String?,
)

internal data class ReviewAlbum(
    val id: Long,
    val path: String,
    val revision: Long,
    val title: String,
    val date: String?,
    val people: Set<Long>,
    val suggestions: List<Suggestion>,
)

internal class ChromantisApi(address: String, val secret: String? = null) {
    val origin = parseOrigin(address)
    private val thumbnailRequests = Semaphore(2)
    private val thumbnails =
        object : LruCache<Pair<String, String?>, Bitmap>(4 * 1024 * 1024) {
            override fun sizeOf(key: Pair<String, String?>, value: Bitmap) =
                value.allocationByteCount
        }

    suspend fun signIn(code: String): ChromantisApi =
        withContext(Dispatchers.IO) {
            request("POST", "/family/session", JSONObject().put("code", code)) { connection ->
                val session =
                    connection.headerFields.entries
                        .asSequence()
                        .filter { "Set-Cookie".equals(it.key, ignoreCase = true) }
                        .flatMap { it.value.asSequence() }
                        .mapNotNull { sessionCookie.find(it)?.groupValues?.get(1) }
                        .firstOrNull() ?: throw IOException("Missing family session cookie.")
                ChromantisApi(origin, session)
            }
        }

    suspend fun signOut() {
        try {
            withContext(Dispatchers.IO) { request("DELETE", "/family/session") { Unit } }
        } finally {
            thumbnails.evictAll()
        }
    }

    suspend fun years() = EntryPage(json("/years").getJSONArray("items").mapObjects(::yearEntry))

    suspend fun refineAlbums(query: String, text: String, tag: String? = null): AlbumRefinement =
        withContext(Dispatchers.IO) {
            val body = JSONObject().put("q", query).put("text", text).put("tag", tag)
            request("POST", "/refine", body) {
                albumRefinement(JSONObject(it.readBytes(1 shl 20).decodeToString()))
            }
        }

    suspend fun albums(
        query: String,
        offset: Int,
        includeFilters: Boolean = false,
        tag: String = "",
    ): EntryPage {
        val filters = if (includeFilters) "&filters=1" else ""
        val tagFilter = if (tag.isBlank()) "" else "&tag=${encode(tag)}"
        val response =
            json(
                "/folders?q=${encode(query)}&limit=${pageSize + 1}&offset=$offset$filters$tagFilter"
            )
        val entries =
            response.getJSONArray("items").mapObjects {
                Entry(it.getString("title"), it.getString("path"))
            }
        return EntryPage(
            entries.take(pageSize),
            (offset + pageSize).takeIf { entries.size > pageSize },
            searchFilters = albumSearchFilters(response),
        )
    }

    suspend fun tagCatalog(photos: Boolean, name: String, offset: Int): TagCatalogPage {
        val route = if (photos) "/photo-tag-catalog" else "/album-tags"
        return decodeTagCatalog(
            json("$route?name=${encode(name.trim())}&limit=$pageSize&offset=$offset")
        )
    }

    suspend fun albumTags(path: String): List<String> {
        val query = encode("album:" + JSONObject.quote(path))
        val items = json("/folders?q=$query&limit=1").getJSONArray("items")
        val item = items.optJSONObject(0) ?: return emptyList()
        if (item.optString("path") != path) return emptyList()
        val tags = item.optJSONArray("tags") ?: return emptyList()
        return (0 until tags.length()).map(tags::getString)
    }

    suspend fun taggedPhotos(tag: String, offset: Int, year: Int? = null): EntryPage =
        imagePage("/confirmed-images?tag=${encode(tag)}${photoYearParameter(year)}", offset)

    suspend fun photos(path: String, offset: Int): EntryPage {
        return imagePage("/album-images?path=${encode(path)}", offset)
    }

    suspend fun confirmedPhotos(
        person: String,
        offset: Int,
        tag: String = "",
        year: Int? = null,
    ): EntryPage {
        val filter = if (tag.isBlank()) "" else "&tag=${encode(tag.trim())}"
        return imagePage(
            "/confirmed-images?person=${encode(person)}$filter${photoYearParameter(year)}",
            offset,
        )
    }

    private fun photoYearParameter(year: Int?): String = if (year == null) "" else "&year=$year"

    private suspend fun imagePage(route: String, offset: Int): EntryPage {
        val response = json("$route&limit=$pageSize&offset=$offset")
        return EntryPage(
            response.getJSONArray("items").mapObjects(::photoEntry),
            if (response.isNull("next_offset")) null else response.getInt("next_offset"),
            thumbnailsEnabled(),
        )
    }

    suspend fun review(path: String?, after: Long): ReviewAlbum? {
        val query = if (path == null) "after=$after" else "path=${encode(path)}"
        val item = json("/album-review?$query").optJSONObject("item") ?: return null
        val suggestions = item.getJSONObject("suggestions")
        return ReviewAlbum(
            item.getLong("id"),
            item.getString("path"),
            item.getLong("revision"),
            item.getString("title"),
            albumDate(item),
            item.getJSONArray("person_ids").let { ids ->
                (0 until ids.length()).map(ids::getLong).toSet()
            },
            suggestions
                .keys()
                .asSequence()
                .sorted()
                .map { key ->
                    val suggestion = suggestions.getJSONObject(key)
                    Suggestion(
                        key,
                        suggestion.getString("label"),
                        suggestion.getString("evidence"),
                        suggestion.getString("state"),
                        suggestion.optionalString("tag"),
                    )
                }
                .toList(),
        )
    }

    suspend fun people() =
        json("/album-review/people").getJSONArray("items").mapObjects {
            Person(
                it.getLong("id"),
                it.getString("display_name"),
                it.getJSONArray("aliases").let { aliases ->
                    (0 until aliases.length()).map(aliases::getString)
                },
            )
        }

    suspend fun reviewPhotos(path: String) =
        EntryPage(
            json("/album-review/photos?path=${encode(path)}")
                .getJSONArray("items")
                .mapObjects(::photoEntry),
            hasThumbnails = thumbnailsEnabled(),
        )

    suspend fun photoTags(paths: List<String>): List<TaggedPhoto> {
        val query = paths.joinToString("&") { "path=${encode(it)}" }
        return json("/photo-tags?$query").getJSONArray("items").mapObjects(::taggedPhoto)
    }

    suspend fun savePhotoTags(
        photos: List<TaggedPhoto>,
        person: Long?,
        tag: String,
        remove: Boolean,
    ) =
        withContext(Dispatchers.IO) {
            request("PATCH", "/photo-tags", photoTagEdit(photos, person, tag, remove)) { Unit }
        }

    suspend fun saveReview(
        album: ReviewAlbum,
        selectedPeople: Set<Long>,
        newPerson: String,
        decisions: Map<String, String?>,
    ) =
        withContext(Dispatchers.IO) {
            val changes = JSONObject()
            decisions.forEach { (key, value) -> changes.put(key, value ?: JSONObject.NULL) }
            val body =
                JSONObject()
                    .put("id", album.id)
                    .put("revision", album.revision)
                    .put("path", album.path)
                    .put("add_people", JSONArray((selectedPeople - album.people).sorted()))
                    .put("remove_people", JSONArray((album.people - selectedPeople).sorted()))
                    .put("decisions", changes)
            if (newPerson.isNotBlank()) body.put("new_person", newPerson.trim())
            request("POST", "/album-review", body) { Unit }
        }

    suspend fun thumbnail(path: String, identity: String? = null): Bitmap =
        thumbnailRequests.withPermit {
            val key = path to identity
            if (identity == null) photo(path, preview = true)
            else thumbnails.get(key) ?: photo(path, preview = true).also { thumbnails.put(key, it) }
        }

    suspend fun albumCover(path: String): Bitmap? {
        try {
            return thumbnailRequests.withPermit { readPhoto("/album-cover", path, preview = true) }
        } catch (error: HttpFailure) {
            if (error.status !in setOf(403, 404)) throw error
        }
        val page = photos(path, 0)
        if (!page.hasThumbnails) return null
        return page.entries.firstOrNull()?.let { thumbnail(it.path, it.identity) }
    }

    suspend fun photo(path: String, preview: Boolean = false): Bitmap =
        readPhoto(if (preview) "/thumbnail" else "/image", path, preview)

    suspend fun originalBytes(path: String, limit: Int = 32 shl 20): ByteArray =
        withContext(Dispatchers.IO) {
            request("GET", "/image?path=${encode(path)}") { it.readBytes(limit) }
        }

    private suspend fun readPhoto(route: String, path: String, preview: Boolean): Bitmap =
        withContext(Dispatchers.IO) {
            request("GET", "$route?path=${encode(path)}") { connection ->
                val data = connection.readBytes(if (preview) 1 shl 20 else 32 shl 20)
                val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeByteArray(data, 0, data.size, options)
                val limit = if (preview) 480 else 2048
                options.inSampleSize = 1
                while (maxOf(options.outWidth, options.outHeight) / options.inSampleSize > limit) {
                    options.inSampleSize *= 2
                }
                options.inJustDecodeBounds = false
                BitmapFactory.decodeByteArray(data, 0, data.size, options)
                    ?: throw IOException("Invalid image data.")
            }
        }

    suspend fun indexStatus(): IndexStatus = indexStatus(json("/archive-status"))

    private suspend fun thumbnailsEnabled() =
        json("/archive-status").getJSONObject("item").optBoolean("thumbnails")

    private suspend fun json(route: String): JSONObject =
        withContext(Dispatchers.IO) {
            request("GET", route) { JSONObject(it.readBytes(1 shl 20).decodeToString()) }
        }

    private fun <T> request(
        method: String,
        route: String,
        body: JSONObject? = null,
        read: (HttpsURLConnection) -> T,
    ): T {
        val connection =
            URI.create("$origin/api/v1$route").toURL().openConnection() as HttpsURLConnection
        try {
            connection.instanceFollowRedirects = false
            connection.connectTimeout = 6000
            connection.readTimeout = 8000
            connection.useCaches = false
            connection.requestMethod = method
            secret?.let { connection.setRequestProperty("Cookie", "chromantis_family=$it") }
            if (method != "GET") connection.setRequestProperty("Origin", origin)
            body?.let {
                val bytes = it.toString().encodeToByteArray()
                connection.setRequestProperty("Content-Type", "application/json")
                connection.doOutput = true
                connection.setFixedLengthStreamingMode(bytes.size)
                connection.outputStream.use { output -> output.write(bytes) }
            }
            val status = connection.responseCode
            if (status == 401) thumbnails.evictAll()
            if (status !in 200..299) throw HttpFailure(status)
            return read(connection)
        } finally {
            connection.disconnect()
        }
    }

    internal class HttpFailure(val status: Int) : IOException("Chromantis returned HTTP $status")

    companion object {
        const val pageSize = 30
        private val sessionCookie = Regex("^chromantis_family=([A-Za-z0-9_-]{43})(?:;|$)")

        private fun encode(value: String) = URLEncoder.encode(value, "UTF-8")

        private fun parseOrigin(value: String): String {
            val uri =
                try {
                    URI(value.trim())
                } catch (error: java.net.URISyntaxException) {
                    throw IllegalArgumentException("Invalid server address.", error)
                }
            require(
                "https".equals(uri.scheme, ignoreCase = true) &&
                    uri.host != null &&
                    (uri.port == -1 || uri.port in 1..65535) &&
                    uri.rawUserInfo == null &&
                    uri.rawQuery == null &&
                    uri.rawFragment == null &&
                    uri.rawPath in setOf("", "/")
            ) {
                "Expected a private HTTPS server address."
            }
            val port = if (uri.port == -1 || uri.port == 443) "" else ":${uri.port}"
            return "https://${uri.host.lowercase(Locale.ROOT)}$port"
        }
    }
}

internal class ResponseTooLarge : IOException("Response is too large.")

private fun HttpsURLConnection.readBytes(limit: Int): ByteArray {
    if (contentLengthLong > limit) throw ResponseTooLarge()
    return inputStream.use { input ->
        val output = java.io.ByteArrayOutputStream()
        val buffer = ByteArray(16 * 1024)
        while (true) {
            val count = input.read(buffer)
            if (count == -1) break
            if (output.size() + count > limit) throw ResponseTooLarge()
            output.write(buffer, 0, count)
        }
        output.toByteArray()
    }
}

private inline fun <T> JSONArray.mapObjects(read: (JSONObject) -> T): List<T> =
    List(length()) { read(getJSONObject(it)) }

private fun JSONObject.optionalString(key: String): String? =
    if (isNull(key)) null else getString(key)

internal fun albumSearchFilters(response: JSONObject): AlbumSearchFilters? =
    response.optJSONObject("filters")?.let { filters ->
        AlbumSearchFilters(
            filters.getString("text"),
            filters.getJSONArray("active").mapObjects {
                AlbumFilter(it.getString("kind"), it.getString("label"), it.getString("without"))
            },
        )
    }

internal fun albumRefinement(response: JSONObject) =
    AlbumRefinement(
        response.optionalString("q"),
        response.getJSONArray("choices").mapObjects {
            Entry(it.getString("title"), it.getString("path"))
        },
    )

internal fun yearEntry(item: JSONObject): Entry {
    val year = item.getInt("year").toString()
    return Entry(year, year, albumCount = item.getInt("folders"))
}

internal fun albumDate(item: JSONObject): String? =
    item.optionalString("event_date")
        ?: if (item.isNull("year")) null else item.getInt("year").toString()

internal fun photoEntry(item: JSONObject): Entry {
    val path = item.getString("path")
    return Entry(path.substringAfterLast('/'), path, identity = item.optionalString("identity"))
}

internal fun taggedPhoto(item: JSONObject) =
    TaggedPhoto(
        item.getString("path"),
        item.getString("identity"),
        item.getJSONArray("people").mapObjects { it.getLong("person_id") }.toSet(),
        item.getJSONArray("manual_tags").mapObjects { it.getString("tag") }.toSet(),
    )

internal fun photoTagEdit(
    photos: List<TaggedPhoto>,
    person: Long?,
    tag: String,
    remove: Boolean,
): JSONObject {
    val payload =
        JSONObject()
            .put(
                "photos",
                JSONArray(
                    photos.map { JSONObject().put("path", it.path).put("identity", it.identity) }
                ),
            )
    if (person != null)
        payload.put(if (remove) "remove_people" else "add_people", JSONArray(listOf(person)))
    if (tag.isNotBlank())
        payload.put(if (remove) "manual_remove" else "manual_add", JSONArray(listOf(tag.trim())))
    return payload
}

internal data class CatalogTag(val label: String, val count: Int)

internal data class TagCatalogPage(val items: List<CatalogTag>, val nextOffset: Int?)

internal fun decodeTagCatalog(response: JSONObject): TagCatalogPage =
    TagCatalogPage(
        response.getJSONArray("items").mapObjects {
            CatalogTag(it.getString("tag"), it.getInt("count"))
        },
        if (response.isNull("next_offset")) null else response.getInt("next_offset"),
    )
