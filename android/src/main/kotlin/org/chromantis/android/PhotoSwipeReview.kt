package org.chromantis.android

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import kotlinx.coroutines.launch

internal fun photoReviewTargets(
    photos: List<TaggedPhoto>,
    decisions: List<ReviewGesture>,
    person: Long,
): List<TaggedPhoto> =
    photos.zip(decisions).mapNotNull { (photo, decision) ->
        photo.takeIf { decision == ReviewGesture.ACCEPT && person !in it.people }
    }

@Composable
internal fun PhotoSwipeReview(
    api: ChromantisApi,
    entries: List<Entry>,
    onExpired: () -> Unit,
    onClose: () -> Unit,
    onReload: () -> Unit,
    onSaved: () -> Unit,
) {
    val saving = remember { mutableStateOf(false) }
    val busy by saving
    var decisions by remember { mutableStateOf(emptyList<ReviewGesture>()) }
    var confirmDiscard by remember { mutableStateOf(false) }
    val requestClose = {
        if (!busy) {
            if (decisions.isEmpty()) onClose() else confirmDiscard = true
        }
    }
    Dialog(onDismissRequest = requestClose) {
        Surface(shape = MaterialTheme.shapes.large) {
            Column(
                Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    stringResource(R.string.review_photos),
                    style = MaterialTheme.typography.titleLarge,
                )
                LoadContent(
                    onExpired,
                    load = {
                        val tags = api.photoTags(entries.map { it.path }).associateBy { it.path }
                        entries.map { tags.getValue(it.path) } to api.people()
                    },
                ) { (photos, people) ->
                    var person by remember { mutableStateOf<Person?>(null) }
                    var query by remember { mutableStateOf("") }
                    val focus = LocalFocusManager.current
                    val chosen = person
                    if (chosen == null) {
                        Text(stringResource(R.string.review_choose_person))
                        PhotoPersonPicker(people, query, { query = it }) {
                            focus.clearFocus()
                            person = it
                        }
                    } else {
                        PhotoReviewPass(
                            api,
                            photos,
                            chosen,
                            decisions,
                            { decisions = it },
                            saving,
                            onExpired,
                            onReload,
                            onSaved,
                        )
                    }
                }
                TextButton(onClick = requestClose, enabled = !busy) {
                    Text(stringResource(R.string.cancel))
                }
            }
        }
    }
    if (confirmDiscard) {
        AlertDialog(
            onDismissRequest = { confirmDiscard = false },
            title = { Text(stringResource(R.string.discard_photo_review_title)) },
            text = { Text(stringResource(R.string.discard_photo_review_message)) },
            confirmButton = {
                TextButton(onClick = onClose) {
                    Text(stringResource(R.string.discard_photo_review))
                }
            },
            dismissButton = {
                TextButton(onClick = { confirmDiscard = false }) {
                    Text(stringResource(R.string.continue_photo_review))
                }
            },
        )
    }
}

@Composable
private fun PhotoReviewPass(
    api: ChromantisApi,
    photos: List<TaggedPhoto>,
    person: Person,
    decisions: List<ReviewGesture>,
    onDecisionsChanged: (List<ReviewGesture>) -> Unit,
    saving: MutableState<Boolean>,
    onExpired: () -> Unit,
    onReload: () -> Unit,
    onSaved: () -> Unit,
) {
    var busy by saving
    var error by remember { mutableStateOf<Throwable?>(null) }
    val scope = rememberCoroutineScope()
    val conflict = error?.hasStatus(409) == true
    val index = decisions.size
    val targets = photoReviewTargets(photos, decisions, person.id)
    val current = photos.getOrNull(index)
    Text(
        stringResource(R.string.review_question, person.name),
        style = MaterialTheme.typography.titleMedium,
    )
    if (current != null) {
        key(current.path, current.identity) {
            var ready by remember { mutableStateOf(false) }
            val alreadyTagged = person.id in current.people
            val canAccept = ready && !alreadyTagged
            var advanced by remember(decisions) { mutableStateOf(false) }
            fun advance(decision: ReviewGesture) {
                if (busy || conflict || advanced) return
                if (decision == ReviewGesture.ACCEPT && !canAccept) return
                advanced = true
                onDecisionsChanged(decisions + decision)
            }
            Text(stringResource(R.string.photo_review_progress, index + 1, photos.size))
            SwipeReviewCard(
                enabled = !busy && !conflict,
                canAccept = canAccept,
                onSkip = { advance(ReviewGesture.SKIP) },
                onAccept = { advance(ReviewGesture.ACCEPT) },
                hint =
                    when {
                        alreadyTagged -> R.string.photo_already_tagged
                        canAccept -> R.string.swipe_photo_help
                        else -> R.string.photo_review_preview_required
                    },
                acceptHint = R.string.release_to_mark_photo,
                skipHint = R.string.release_to_skip_photo,
            ) {
                val entry = Entry(current.path.substringAfterLast('/'), current.path)
                Thumbnail(
                    api,
                    entry,
                    onExpired,
                    modifier = Modifier.fillMaxWidth().height(200.dp),
                    contentScale = ContentScale.Fit,
                    identity = current.identity,
                    onReady = { ready = true },
                )
                Text(
                    entry.title,
                    Modifier.padding(8.dp),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TextButton(
                    onClick = { advance(ReviewGesture.SKIP) },
                    enabled = !busy && !conflict,
                ) {
                    Text(stringResource(R.string.skip_photo))
                }
                TextButton(
                    onClick = { advance(ReviewGesture.ACCEPT) },
                    enabled = canAccept && !busy && !conflict,
                ) {
                    Text(stringResource(R.string.mark_photo))
                }
            }
        }
    } else {
        Text(stringResource(R.string.photo_review_finished))
    }
    error?.let {
        val label =
            when {
                conflict -> R.string.photo_tags_conflict
                it.hasStatus(413) -> R.string.photo_tags_batch_too_large
                else -> errorLabel(it)
            }
        Text(stringResource(label), color = MaterialTheme.colorScheme.error)
    }
    if (conflict) {
        Button(onClick = onReload) { Text(stringResource(R.string.reselect_photos)) }
    } else {
        TextButton(
            onClick = { onDecisionsChanged(decisions.dropLast(1)) },
            enabled = decisions.isNotEmpty() && !busy,
        ) {
            Text(stringResource(R.string.undo_photo_decision))
        }
        Button(
            onClick = {
                if (busy || targets.isEmpty()) return@Button
                busy = true
                error = null
                scope.launch {
                    attempt { api.savePhotoTags(targets, person.id, "", remove = false) }
                        .fold(
                            onSuccess = { onSaved() },
                            onFailure = {
                                busy = false
                                if (it.hasStatus(401)) onExpired() else error = it
                            },
                        )
                }
            },
            enabled = targets.isNotEmpty() && !busy,
        ) {
            Text(
                if (busy) stringResource(R.string.saving)
                else
                    pluralStringResource(R.plurals.save_reviewed_photos, targets.size, targets.size)
            )
        }
    }
}
