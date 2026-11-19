package org.chromantis.android

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
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
    Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                stringResource(R.string.quick_review_title),
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                stringResource(R.string.quick_review_help),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        SwipeReviewCard(
            enabled = !busy && !conflict,
            canAccept = suggestion != null,
            onSkip = { if (!busy) onSkip() },
            onAccept = ::accept,
            hint = if (suggestion == null) R.string.swipe_skip_album else R.string.swipe_album_help,
            acceptHint = R.string.release_to_accept,
            skipHint = R.string.release_to_skip,
        ) {
            Column(
                Modifier.fillMaxWidth().heightIn(min = 196.dp).padding(14.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Surface(
                        shape = CircleShape,
                        color = MaterialTheme.colorScheme.secondaryContainer,
                        modifier = Modifier.size(40.dp),
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            LibraryIcon(R.drawable.ic_folder, Modifier.size(22.dp))
                        }
                    }
                    Text(
                        stringResource(R.string.pending_album),
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(
                        albumDisplayTitle(album.title),
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.SemiBold,
                    )
                    (albumDisplayDate(album.path) ?: album.date)?.let {
                        Text(
                            it,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                if (suggestion == null) {
                    Surface(
                        shape = RoundedCornerShape(18.dp),
                        color = MaterialTheme.colorScheme.surfaceContainerHighest,
                    ) {
                        Column(
                            Modifier.padding(14.dp),
                            verticalArrangement = Arrangement.spacedBy(2.dp),
                        ) {
                            Text(
                                stringResource(R.string.no_tag_suggestion),
                                fontWeight = FontWeight.SemiBold,
                            )
                            Text(
                                stringResource(R.string.no_tag_suggestion_help),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                } else {
                    Surface(
                        shape = RoundedCornerShape(18.dp),
                        color = MaterialTheme.colorScheme.primaryContainer,
                    ) {
                        Column(
                            Modifier.padding(14.dp),
                            verticalArrangement = Arrangement.spacedBy(2.dp),
                        ) {
                            Text(
                                suggestion.label.replaceFirstChar { it.uppercase() },
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.SemiBold,
                            )
                            Text(
                                stringResource(R.string.suggestion_source, suggestion.evidence),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onPrimaryContainer,
                            )
                        }
                    }
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
                shape = RoundedCornerShape(18.dp),
            ) {
                Text(stringResource(R.string.leave_pending))
            }
            if (suggestion != null) {
                Button(
                    onClick = ::accept,
                    enabled = !busy && !conflict,
                    modifier = Modifier.weight(1f),
                    shape = RoundedCornerShape(18.dp),
                ) {
                    Text(
                        if (busy) stringResource(R.string.saving)
                        else stringResource(R.string.accept_named_tag, suggestion.label)
                    )
                }
            }
        }
        OutlinedButton(
            onClick = { if (!busy) onEdit() },
            enabled = !busy,
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(18.dp),
        ) {
            LibraryIcon(R.drawable.ic_organize, Modifier.size(18.dp))
            Spacer(Modifier.size(8.dp))
            Text(stringResource(R.string.edit_review_details))
        }
        error?.let {
            Text(
                stringResource(if (conflict) R.string.review_conflict else errorLabel(it)),
                color = MaterialTheme.colorScheme.error,
            )
        }
        if (conflict) {
            Button(onClick = onReload, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.reload_review))
            }
        }
    }
}
