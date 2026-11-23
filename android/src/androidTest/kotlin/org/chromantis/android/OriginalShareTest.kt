package org.chromantis.android

import android.content.Intent
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.FileNotFoundException
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class OriginalShareTest {
    @Test
    fun sendsReadOnlyContentUriAndDropsThePreviousCachedFile() = runBlocking {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val bytes = byteArrayOf(1, 2, 3)
        val first = prepareOriginalShare(context, "fixture/photo.jpg", bytes)
        val original = checkNotNull(first.clipData).getItemAt(0).uri
        assertEquals(Intent.ACTION_SEND, first.action)
        assertEquals("image/jpeg", first.type)
        assertEquals("content", original.scheme)
        assertEquals(Intent.FLAG_GRANT_READ_URI_PERMISSION, first.flags)
        assertArrayEquals(
            bytes,
            context.contentResolver.openInputStream(original)!!.use { it.readBytes() },
        )

        val next = prepareOriginalShare(context, "fixture/photo.jpg", byteArrayOf(4))
        assertNotEquals(original, checkNotNull(next.clipData).getItemAt(0).uri)
        val oldStream =
            try {
                context.contentResolver.openInputStream(original)
            } catch (_: FileNotFoundException) {
                null
            }
        oldStream.use { assertNull(it) }
    }

    @Test
    fun sendsOnlyRequestedOriginalsEvenWithTheSameFilename() = runBlocking {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val paths = listOf("first/photo.jpg", "second/photo.jpg")
        val reads = mutableListOf<String>()
        val send =
            prepareOriginalShare(context, paths) { path, limit ->
                assertEquals((32 shl 20) - reads.size, limit)
                reads.add(path)
                byteArrayOf(reads.size.toByte())
            }
        assertEquals(paths, reads)
        assertEquals(Intent.ACTION_SEND_MULTIPLE, send.action)
        assertEquals(Intent.FLAG_GRANT_READ_URI_PERMISSION, send.flags)
        val clips = checkNotNull(send.clipData)
        assertEquals(2, clips.itemCount)
        for (index in paths.indices) {
            val uri = clips.getItemAt(index).uri
            assertArrayEquals(
                byteArrayOf((index + 1).toByte()),
                context.contentResolver.openInputStream(uri)!!.use { it.readBytes() },
            )
        }
    }
}
