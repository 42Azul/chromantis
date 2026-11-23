package org.chromantis.android

import android.graphics.Bitmap
import android.os.Build
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.ByteArrayOutputStream
import java.util.UUID
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertArrayEquals
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class OriginalStorageTest {
    @Test
    fun savesTheOriginalBytesToMediaStore() {
        assumeTrue(Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q)
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return
        val resolver = InstrumentationRegistry.getInstrumentation().targetContext.contentResolver
        val output = ByteArrayOutputStream()
        val image = Bitmap.createBitmap(4, 4, Bitmap.Config.ARGB_8888)
        image.compress(Bitmap.CompressFormat.JPEG, 95, output)
        image.recycle()
        val bytes = output.toByteArray()
        val uri = runBlocking { saveOriginal(resolver, "fixture/${UUID.randomUUID()}.jpg", bytes) }
        try {
            assertArrayEquals(bytes, resolver.openInputStream(uri)!!.use { it.readBytes() })
        } finally {
            resolver.delete(uri, null, null)
        }
    }
}
