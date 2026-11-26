package org.chromantis.android

import android.graphics.Bitmap
import android.graphics.Color
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PhotoCollageTest {
    @Test
    fun rendersFourPhotosWithOnlyOneDecodedThumbnailAtATime() = runBlocking {
        val colors = listOf(Color.RED, Color.GREEN, Color.BLUE, Color.YELLOW)
        var previous: Bitmap? = null
        var maxThumbnailBytes = 0
        val output =
            renderCollage(colors.indices.map(Int::toString)) { index ->
                check(previous?.isRecycled != false)
                Bitmap.createBitmap(480, 480, Bitmap.Config.ARGB_8888).also { bitmap ->
                    bitmap.eraseColor(colors[index.toInt()])
                    previous = bitmap
                    maxThumbnailBytes = maxOf(maxThumbnailBytes, bitmap.allocationByteCount)
                }
            }
        try {
            assertTrue(previous!!.isRecycled)
            assertEquals(960, output.width)
            assertEquals(960, output.height)
            assertEquals(4_608_000, output.allocationByteCount + maxThumbnailBytes)
            colors.forEachIndexed { index, color ->
                assertEquals(color, output.getPixel(240 + index % 2 * 480, 240 + index / 2 * 480))
            }
        } finally {
            output.recycle()
        }
    }

    @Test
    fun cancellationDuringThumbnailLoadDoesNotRequestAnother() = runBlocking {
        val started = CompletableDeferred<Unit>()
        var attempts = 0
        val job = launch {
            renderCollage(listOf("first", "second")) {
                attempts++
                started.complete(Unit)
                awaitCancellation()
            }
        }
        withTimeout(5000) { started.await() }
        job.cancelAndJoin()
        assertTrue(job.isCancelled)
        assertEquals(1, attempts)
    }
}
