package org.chromantis.android

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
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
    Column(
        Modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        SwipeReviewCard(
            enabled = !busy && !conflict,
            canAccept = suggestion != null,
            onSkip = { if (!busy) onSkip() },
            onAccept = ::accept,
            hint = if (suggestion == null) R.string.swipe_skip_album else R.string.swipe_album_help,
            acceptHint = R.string.release_to_accept,
            skipHint = R.string.release_to_skip,
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
