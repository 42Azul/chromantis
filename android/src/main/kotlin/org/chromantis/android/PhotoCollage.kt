package org.chromantis.android

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import androidx.annotation.RequiresApi
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import java.io.ByteArrayOutputStream
import java.io.IOException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private const val TILE_SIZE = 480
internal const val MAX_COLLAGE_PHOTOS = 4

private suspend fun renderCollage(api: ChromantisApi, paths: List<String>): Bitmap =
    withContext(Dispatchers.Default) {
        require(paths.size in 2..MAX_COLLAGE_PHOTOS)
        val rows = (paths.size + 1) / 2
        val output = Bitmap.createBitmap(2 * TILE_SIZE, rows * TILE_SIZE, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(output)
        canvas.drawColor(0xFFF5F3EE.toInt())
        val paint = Paint(Paint.FILTER_BITMAP_FLAG)
        paths.forEachIndexed { index, path ->
            val photo = api.photo(path, preview = true)
            try {
                val scale = (TILE_SIZE - 12f) / maxOf(photo.width, photo.height)
                val width = photo.width * scale
                val height = photo.height * scale
                val left = index % 2 * TILE_SIZE + (TILE_SIZE - width) / 2
                val top = index / 2 * TILE_SIZE + (TILE_SIZE - height) / 2
                canvas.drawBitmap(photo, null, RectF(left, top, left + width, top + height), paint)
            } finally {
                photo.recycle()
            }
        }
        output
    }

@RequiresApi(29)
@Composable
internal fun PhotoCollage(
    api: ChromantisApi,
    paths: List<String>,
    onExpired: () -> Unit,
    onClose: () -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var preview by remember { mutableStateOf<Bitmap?>(null) }
    var message by remember { mutableStateOf(R.string.collage_loading) }
    var saving by remember { mutableStateOf(false) }
    var saved by remember { mutableStateOf(false) }
    LaunchedEffect(api, paths) {
        attempt { renderCollage(api, paths) }
            .onSuccess {
                preview = it
                message = 0
            }
            .onFailure {
                if (it.hasStatus(401)) onExpired()
                message = errorLabel(it)
            }
    }
    val image = preview
    AlertDialog(
        onDismissRequest = { if (!saving) onClose() },
        title = { Text(stringResource(R.string.make_collage)) },
        text = {
            Column {
                if (image != null) {
                    Image(
                        image.asImageBitmap(),
                        contentDescription = stringResource(R.string.collage_preview),
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
                if (message != 0) Text(stringResource(message))
            }
        },
        confirmButton = {
            if (image != null) {
                Button(
                    enabled = !saving && !saved,
                    onClick = {
                        saving = true
                        message = R.string.collage_saving
                        scope.launch {
                            val result = attempt {
                                val bytes =
                                    withContext(Dispatchers.Default) {
                                        val stream = ByteArrayOutputStream()
                                        if (!image.compress(Bitmap.CompressFormat.JPEG, 92, stream))
                                            throw IOException("Could not encode collage.")
                                        stream.toByteArray()
                                    }
                                saveOriginal(
                                    context.contentResolver,
                                    "Chromantis-collage-${System.currentTimeMillis()}.jpg",
                                    bytes,
                                )
                            }
                            saving = false
                            saved = result.isSuccess
                            message =
                                if (saved) R.string.collage_saved else R.string.collage_save_error
                        }
                    },
                ) {
                    Text(stringResource(R.string.save_collage))
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onClose, enabled = !saving) {
                Text(stringResource(R.string.close_collage))
            }
        },
    )
}
