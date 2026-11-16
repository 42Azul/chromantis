package org.chromantis.android

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import java.text.Normalizer
import java.util.Locale
import kotlinx.coroutines.launch

@Composable
internal fun AlbumReview(
    api: ChromantisApi,
    path: String?,
    onExpired: () -> Unit,
    onClose: () -> Unit,
) {
    var after by rememberSaveable { mutableLongStateOf(0) }
    var reload by remember { mutableIntStateOf(0) }
    var saveNotice by rememberSaveable { mutableIntStateOf(0) }
    var editingAlbum by rememberSaveable { mutableLongStateOf(0) }
    if (saveNotice != 0) Text(stringResource(saveNotice), color = MaterialTheme.colorScheme.primary)
    key(after, reload) {
        LoadContent(onExpired, load = { api.review(path, after) }) { album ->
            if (album == null) {
                Text(stringResource(R.string.no_pending_albums))
                if (after > 0)
                    TextButton(
                        onClick = {
                            after = 0
                            saveNotice = 0
                        }
                    ) {
                        Text(stringResource(R.string.restart_review))
                    }
            } else {
                val skip = {
                    saveNotice = 0
                    editingAlbum = 0
                    if (path == null) after = album.id else onClose()
                }
                if (path == null && editingAlbum != album.id) {
                    QuickAlbumReview(
                        api,
                        album,
                        onExpired,
                        onReload = {
                            saveNotice = 0
                            reload++
                        },
                        onSkip = skip,
                        onEdit = { editingAlbum = album.id },
                        onAccepted = {
                            saveNotice = R.string.tag_saved
                            reload++
                        },
                    )
                } else {
                    LoadContent(onExpired, load = { api.people() }) { people ->
                        ReviewForm(
                            api,
                            album,
                            people,
                            onExpired,
                            onReload = { reload++ },
                            onSkip = skip,
                            onSaved = {
                                if (path == null) {
                                    saveNotice = R.string.album_saved
                                    editingAlbum = 0
                                    after = album.id
                                } else {
                                    onClose()
                                }
                            },
                            onQuickReview = if (path == null) ({ editingAlbum = 0 }) else null,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun ReviewForm(
    api: ChromantisApi,
    album: ReviewAlbum,
    people: List<Person>,
    onExpired: () -> Unit,
    onReload: () -> Unit,
    onSkip: () -> Unit,
    onSaved: () -> Unit,
    onQuickReview: (() -> Unit)?,
) {
    var chosen by remember { mutableStateOf(album.people) }
    var filter by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }
    var showPhotos by remember { mutableStateOf(false) }
    val decisions = remember { mutableStateMapOf<String, String?>() }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<Throwable?>(null) }
    val scope = rememberCoroutineScope()
    val focus = LocalFocusManager.current
    var openPhoto by remember { mutableStateOf<Entry?>(null) }
    Column(
        Modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(album.title, style = MaterialTheme.typography.titleLarge)
        album.date?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
        if (
            onQuickReview != null &&
                !busy &&
                chosen == album.people &&
                name.isBlank() &&
                decisions.isEmpty()
        ) {
            TextButton(onClick = onQuickReview) { Text(stringResource(R.string.quick_review)) }
        }
        if (!showPhotos)
            TextButton(onClick = { showPhotos = true }) {
                Text(stringResource(R.string.show_review_photos))
            }
        if (showPhotos)
            LoadContent(onExpired, load = { api.reviewPhotos(album.path) }) { photos ->
                if (photos.entries.isEmpty()) Text(stringResource(R.string.no_results))
                else
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        photos.entries.forEach { photo ->
                            Column(Modifier.weight(1f).clickable { openPhoto = photo }) {
                                if (photos.hasThumbnails) Thumbnail(api, photo, onExpired)
                                Text(photo.title, style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
            }
        Text(stringResource(R.string.people_in_album), style = MaterialTheme.typography.titleMedium)
        Text(stringResource(R.string.album_people_explanation))
        OutlinedTextField(
            value = filter,
            onValueChange = { filter = it },
            singleLine = true,
            label = { Text(stringResource(R.string.people_filter)) },
            modifier = Modifier.fillMaxWidth(),
        )
        val needle = searchableName(filter.trim())
        val matching =
            people.filter { person ->
                searchableName(person.name).contains(needle) ||
                    person.aliases.any { searchableName(it).contains(needle) }
            }
        val visible =
            if (needle.isEmpty())
                matching.filter { it.id in chosen } + matching.filter { it.id !in chosen }.take(12)
            else matching.take(30)
        visible.forEach { person ->
            val checked = person.id in chosen
            Row(
                Modifier.fillMaxWidth()
                    .toggleable(
                        value = checked,
                        enabled = !busy,
                        role = Role.Checkbox,
                        onValueChange = { selected ->
                            chosen = if (selected) chosen + person.id else chosen - person.id
                        },
                    )
                    .padding(vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Checkbox(checked, onCheckedChange = null, enabled = !busy)
                Column {
                    Text(person.name)
                    if (person.aliases.isNotEmpty()) {
                        Text(
                            person.aliases.joinToString(", "),
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
            }
        }
        if (visible.isEmpty() && needle.isNotEmpty()) Text(stringResource(R.string.no_results))
        if (visible.size < matching.size) Text(stringResource(R.string.narrow_people))
        OutlinedTextField(
            value = name,
            onValueChange = { if (it.length <= 100) name = it },
            singleLine = true,
            label = { Text(stringResource(R.string.new_person_hint)) },
            enabled = !busy,
            modifier = Modifier.fillMaxWidth(),
        )
        if (album.suggestions.isNotEmpty()) {
            Text(
                stringResource(R.string.suggested_tags),
                style = MaterialTheme.typography.titleMedium,
            )
            album.suggestions.forEach { suggestion ->
                val selected =
                    if (decisions.containsKey(suggestion.key)) decisions[suggestion.key]
                    else suggestion.tag.takeIf { suggestion.state != "pending" }
                val pending =
                    suggestion.state == "pending" && !decisions.containsKey(suggestion.key)
                Text(
                    stringResource(
                        R.string.suggestion_evidence,
                        suggestion.label,
                        suggestion.evidence,
                    )
                )
                if (selected != null && selected != suggestion.key) {
                    Text(stringResource(R.string.corrected_tag, selected))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(
                        selected = selected == suggestion.key,
                        onClick = { decisions[suggestion.key] = suggestion.key },
                        label = { Text(stringResource(R.string.accept_tag)) },
                        enabled = !busy,
                    )
                    FilterChip(
                        selected = !pending && selected == null,
                        onClick = { decisions[suggestion.key] = null },
                        label = { Text(stringResource(R.string.reject_tag)) },
                        enabled = !busy,
                    )
                }
            }
        }
        val conflict = error?.hasStatus(409) == true
        error?.let {
            val label =
                when {
                    conflict -> R.string.review_conflict
                    it.hasStatus(400) -> R.string.review_invalid
                    else -> errorLabel(it)
                }
            Text(stringResource(label), color = MaterialTheme.colorScheme.error)
        }
        if (conflict)
            TextButton(onClick = onReload) { Text(stringResource(R.string.reload_review)) }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = {
                    focus.clearFocus()
                    busy = true
                    error = null
                    val changes = decisions.toMap()
                    scope.launch {
                        attempt { api.saveReview(album, chosen, name, changes) }
                            .fold(
                                onSuccess = { onSaved() },
                                onFailure = {
                                    if (it.hasStatus(401)) onExpired()
                                    else {
                                        error = it
                                        busy = false
                                    }
                                },
                            )
                    }
                },
                enabled = !busy && !conflict,
            ) {
                Text(
                    stringResource(
                        when {
                            busy -> R.string.saving
                            onQuickReview != null -> R.string.save_and_next
                            else -> R.string.save_album
                        }
                    )
                )
            }
            TextButton(onClick = onSkip, enabled = !busy) {
                Text(stringResource(R.string.skip_album))
            }
        }
    }
    openPhoto?.let { photo ->
        AlertDialog(
            onDismissRequest = { openPhoto = null },
            title = { Text(photo.title) },
            text = { OriginalPhoto(api, photo.path, photo.title, onExpired) },
            confirmButton = {
                TextButton(onClick = { openPhoto = null }) { Text(stringResource(R.string.back)) }
            },
        )
    }
}

private val combiningMarks = Regex("\\p{M}+")

private fun searchableName(value: String): String =
    Normalizer.normalize(value, Normalizer.Form.NFD)
        .replace(combiningMarks, "")
        .lowercase(Locale.ROOT)
