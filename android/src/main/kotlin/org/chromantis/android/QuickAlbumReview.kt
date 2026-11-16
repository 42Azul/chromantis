package org.chromantis.android

import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

internal enum class ReviewGesture {
    SKIP,
    ACCEPT,
}

internal fun reviewGesture(distance: Float, threshold: Float, canAccept: Boolean): ReviewGesture? =
    when {
        distance <= -threshold -> ReviewGesture.SKIP
        distance >= threshold && canAccept -> ReviewGesture.ACCEPT
        else -> null
    }

@Composable
internal fun QuickAlbumReview(
    api: ChromantisApi,
    album: ReviewAlbum,
    onExpired: () -> Unit,
    onReload: () -> Unit,
    onSkip: () -> Unit,
    onEdit: () -> Unit,
    onAccepted: () -> Unit,
) {
    val suggestion = album.suggestions.firstOrNull { it.state == "pending" }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<Throwable?>(null) }
    val scope = rememberCoroutineScope()
    val conflict = error?.hasStatus(409) == true
    fun accept() {
        if (busy || error?.hasStatus(409) == true || suggestion == null) return
        busy = true
        error = null
        scope.launch {
            attempt {
                    api.saveReview(album, album.people, "", mapOf(suggestion.key to suggestion.key))
                }
                .fold(
                    onSuccess = { onAccepted() },
                    onFailure = {
                        if (it.hasStatus(401)) onExpired()
                        else {
                            error = it
                            busy = false
                        }
                    },
                )
        }
    }
    val finishDrag by
        rememberUpdatedState<(ReviewGesture?) -> Unit> { gesture ->
            if (!busy) {
                when (gesture) {
                    ReviewGesture.SKIP -> onSkip()
                    ReviewGesture.ACCEPT -> accept()
                    null -> Unit
                }
            }
        }
    var drag by remember { mutableFloatStateOf(0f) }
    var armed by remember { mutableStateOf<ReviewGesture?>(null) }
    fun resetDrag() {
        drag = 0f
        armed = null
    }
    Column(
        Modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Box(
            Modifier.fillMaxWidth().pointerInput(busy, conflict, suggestion?.key) {
                if (busy || conflict) return@pointerInput
                val threshold = minOf(72.dp.toPx(), size.width * 0.3f)
                try {
                    detectHorizontalDragGestures(
                        onDragCancel = ::resetDrag,
                        onDragEnd = {
                            val decision = armed
                            resetDrag()
                            finishDrag(decision)
                        },
                    ) { _, amount ->
                        drag += amount
                        armed = reviewGesture(drag, threshold, suggestion != null)
                    }
                } finally {
                    resetDrag()
                }
            }
        ) {
            Card(
                Modifier.fillMaxWidth().graphicsLayer {
                    val maxRight = if (suggestion == null) 0f else 36.dp.toPx()
                    translationX = (drag * 0.45f).coerceIn(-36.dp.toPx(), maxRight)
                }
            ) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(album.title, style = MaterialTheme.typography.titleLarge)
                    album.date?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
                    if (suggestion == null) {
                        Text(stringResource(R.string.no_tag_suggestion))
                    } else {
                        Text(
                            stringResource(
                                R.string.suggestion_evidence,
                                suggestion.label,
                                suggestion.evidence,
                            ),
                            style = MaterialTheme.typography.bodyMedium,
                        )
                    }
                }
            }
        }
        Text(
            stringResource(
                when (armed) {
                    ReviewGesture.SKIP -> R.string.release_to_skip
                    ReviewGesture.ACCEPT -> R.string.release_to_accept
                    null ->
                        if (suggestion == null) R.string.swipe_skip_album
                        else R.string.swipe_album_help
                }
            ),
            style = MaterialTheme.typography.bodySmall,
        )
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            OutlinedButton(
                onClick = { if (!busy) onSkip() },
                enabled = !busy,
                modifier = if (suggestion == null) Modifier else Modifier.weight(1f),
            ) {
                Text(stringResource(R.string.leave_pending))
            }
            if (suggestion != null) {
                Button(
                    onClick = ::accept,
                    enabled = !busy && !conflict,
                    modifier = Modifier.weight(1f),
                ) {
                    Text(
                        if (busy) stringResource(R.string.saving)
                        else stringResource(R.string.accept_named_tag, suggestion.label)
                    )
                }
            }
        }
        TextButton(onClick = { if (!busy) onEdit() }, enabled = !busy) {
            Text(stringResource(R.string.edit_review_details))
        }
        error?.let {
            Text(
                stringResource(if (conflict) R.string.review_conflict else errorLabel(it)),
                color = MaterialTheme.colorScheme.error,
            )
        }
        if (conflict) {
            TextButton(onClick = onReload) { Text(stringResource(R.string.reload_review)) }
        }
    }
}
