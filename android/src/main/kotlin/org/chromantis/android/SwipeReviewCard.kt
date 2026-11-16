package org.chromantis.android

import androidx.annotation.StringRes
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp

@Composable
internal fun SwipeReviewCard(
    enabled: Boolean,
    canAccept: Boolean,
    onSkip: () -> Unit,
    onAccept: () -> Unit,
    @StringRes hint: Int,
    @StringRes acceptHint: Int,
    @StringRes skipHint: Int,
    content: @Composable ColumnScope.() -> Unit,
) {
    val skip by rememberUpdatedState(onSkip)
    val accept by rememberUpdatedState(onAccept)
    var drag by remember { mutableFloatStateOf(0f) }
    var armed by remember { mutableStateOf<ReviewGesture?>(null) }
    fun resetDrag() {
        drag = 0f
        armed = null
    }
    Box(
        Modifier.fillMaxWidth().pointerInput(enabled, canAccept) {
            if (!enabled) return@pointerInput
            val threshold = minOf(72.dp.toPx(), size.width * 0.3f)
            try {
                detectHorizontalDragGestures(
                    onDragCancel = ::resetDrag,
                    onDragEnd = {
                        val decision = armed
                        resetDrag()
                        when (decision) {
                            ReviewGesture.SKIP -> skip()
                            ReviewGesture.ACCEPT -> accept()
                            null -> Unit
                        }
                    },
                ) { _, amount ->
                    drag += amount
                    armed = reviewGesture(drag, threshold, canAccept)
                }
            } finally {
                resetDrag()
            }
        }
    ) {
        Card(
            Modifier.fillMaxWidth().graphicsLayer {
                val maxRight = if (canAccept) 36.dp.toPx() else 0f
                translationX = (drag * 0.45f).coerceIn(-36.dp.toPx(), maxRight)
            },
            content = content,
        )
    }
    Text(
        stringResource(
            when (armed) {
                ReviewGesture.SKIP -> skipHint
                ReviewGesture.ACCEPT -> acceptHint
                null -> hint
            }
        ),
        style = MaterialTheme.typography.bodySmall,
    )
}
