package org.chromantis.android

import android.content.ClipData
import android.content.Context
import android.content.Intent
import android.webkit.MimeTypeMap
import androidx.core.content.FileProvider
import java.io.File
import java.io.IOException
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

private val shareCacheLock = Mutex()

internal suspend fun prepareOriginalShare(
    context: Context,
    path: String,
    bytes: ByteArray,
): Intent =
    withContext(Dispatchers.IO) {
        shareCacheLock.withLock {
            val name = path.substringAfterLast('/').substringAfterLast('\\')
            val mime =
                MimeTypeMap.getSingleton()
                    .getMimeTypeFromExtension(name.substringAfterLast('.').lowercase())
            if (mime == null || !mime.startsWith("image/"))
                throw IOException("Unsupported image format.")
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
                val file = File(folder, name)
                file.writeBytes(bytes)
                val uri =
                    FileProvider.getUriForFile(context, "${context.packageName}.originals", file)
                Intent(Intent.ACTION_SEND).apply {
                    type = mime
                    putExtra(Intent.EXTRA_STREAM, uri)
                    clipData = ClipData.newRawUri(null, uri)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
            } catch (error: Exception) {
                folder.deleteRecursively()
                throw error
            }
        }
    }
