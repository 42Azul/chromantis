package org.chromantis.android

import android.content.ClipData
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.webkit.MimeTypeMap
import androidx.core.content.FileProvider
import java.io.File
import java.io.IOException
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

private val shareCacheLock = Mutex()

internal const val MAX_SHARE_PHOTOS = 10

internal suspend fun prepareOriginalShare(
    context: Context,
    path: String,
    bytes: ByteArray,
): Intent = prepareOriginalShare(context, listOf(path)) { _, _ -> bytes }

internal suspend fun prepareOriginalShare(
    context: Context,
    paths: List<String>,
    readOriginal: suspend (String, Int) -> ByteArray,
): Intent =
    withContext(Dispatchers.IO) {
        require(paths.size in 1..MAX_SHARE_PHOTOS)
        shareCacheLock.withLock {
            val root = File(context.cacheDir, "original-share")
            // Give every export a new URI so an earlier grant cannot see replacement bytes.
            val folder = File(root, UUID.randomUUID().toString())
            if (!folder.mkdirs()) throw IOException("Could not prepare photo.")
            try {
                for (previous in root.listFiles().orEmpty()) {
                    if (previous != folder && !previous.deleteRecursively()) {
                        throw IOException("Could not clear previous export.")
                    }
                }
                var remaining = 32 shl 20
                val uris = ArrayList<Uri>()
                val types = mutableSetOf<String>()
                for ((index, path) in paths.withIndex()) {
                    ensureActive()
                    val name = path.substringAfterLast('/').substringAfterLast('\\')
                    val mime =
                        MimeTypeMap.getSingleton()
                            .getMimeTypeFromExtension(name.substringAfterLast('.').lowercase())
                    if (mime == null || !mime.startsWith("image/"))
                        throw IOException("Unsupported image format.")
                    val bytes = readOriginal(path, remaining)
                    if (bytes.size > remaining) throw ResponseTooLarge()
                    remaining -= bytes.size
                    val entry = File(folder, index.toString())
                    if (!entry.mkdir()) throw IOException("Could not prepare photo.")
                    val file = File(entry, name)
                    file.writeBytes(bytes)
                    uris +=
                        FileProvider.getUriForFile(
                            context,
                            "${context.packageName}.originals",
                            file,
                        )
                    types += mime
                }
                ensureActive()
                val single = uris.size == 1
                val clips = ClipData.newRawUri(null, uris.first())
                for (uri in uris.drop(1)) clips.addItem(ClipData.Item(uri))
                Intent(if (single) Intent.ACTION_SEND else Intent.ACTION_SEND_MULTIPLE).apply {
                    type = types.singleOrNull() ?: "image/*"
                    if (single) putExtra(Intent.EXTRA_STREAM, uris.first())
                    else putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris)
                    clipData = clips
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
            } catch (error: Exception) {
                folder.deleteRecursively()
                throw error
            }
        }
    }
