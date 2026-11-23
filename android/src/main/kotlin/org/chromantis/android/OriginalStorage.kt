package org.chromantis.android

import android.content.ContentResolver
import android.content.ContentValues
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.webkit.MimeTypeMap
import androidx.annotation.RequiresApi
import java.io.IOException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@RequiresApi(Build.VERSION_CODES.Q)
internal suspend fun saveOriginal(resolver: ContentResolver, path: String, bytes: ByteArray): Uri =
    withContext(Dispatchers.IO) {
        val name = path.substringAfterLast('/').substringAfterLast('\\')
        val mime =
            MimeTypeMap.getSingleton()
                .getMimeTypeFromExtension(name.substringAfterLast('.').lowercase())
        if (mime == null || !mime.startsWith("image/"))
            throw IOException("Unsupported image format.")
        val values =
            ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, name)
                put(MediaStore.MediaColumns.MIME_TYPE, mime)
                put(
                    MediaStore.MediaColumns.RELATIVE_PATH,
                    "${Environment.DIRECTORY_PICTURES}/Chromantis",
                )
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            }
        val collection = MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        val uri =
            resolver.insert(collection, values) ?: throw IOException("Could not create photo.")
        try {
            val output =
                resolver.openOutputStream(uri) ?: throw IOException("Could not open photo.")
            output.use { it.write(bytes) }
            values.clear()
            values.put(MediaStore.MediaColumns.IS_PENDING, 0)
            if (resolver.update(uri, values, null, null) != 1)
                throw IOException("Could not publish photo.")
        } catch (error: Exception) {
            resolver.delete(uri, null, null)
            throw error
        }
        uri
    }
