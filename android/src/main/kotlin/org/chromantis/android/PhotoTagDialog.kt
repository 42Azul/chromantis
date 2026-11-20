package org.chromantis.android

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

@Composable
internal fun PhotoTagDialog(
    api: ChromantisApi,
    paths: List<String>,
    onExpired: () -> Unit,
    onClose: () -> Unit,
    onReselect: () -> Unit,
    onSaved: () -> Unit,
) {
    var selection by remember { mutableStateOf<Pair<List<TaggedPhoto>, List<Person>>?>(null) }
    var person by remember { mutableStateOf<Person?>(null) }
    var query by remember { mutableStateOf("") }
    var tag by remember { mutableStateOf("") }
    var remove by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<Throwable?>(null) }
    val scope = rememberCoroutineScope()
    val conflict = error?.hasStatus(409) == true
    AlertDialog(
        modifier = Modifier.testTag("photo-tag-dialog"),
        onDismissRequest = { if (!busy) onClose() },
        title = { Text(stringResource(R.string.tag_photos)) },
        text = {
            Column(
                Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(pluralStringResource(R.plurals.selected_photo_count, paths.size, paths.size))
                LoadContent(onExpired, load = { api.photoTags(paths) to api.people() }) { loaded ->
                    SideEffect { selection = loaded }
                    val (photos, people) = loaded
                    Text(stringResource(R.string.photo_tags_explanation))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FilterChip(
                            selected = !remove,
                            onClick = { remove = false },
                            label = { Text(stringResource(R.string.add_photo_tag)) },
                            enabled = !busy && !conflict,
                        )
                        FilterChip(
                            selected = remove,
                            onClick = { remove = true },
                            label = { Text(stringResource(R.string.remove_photo_tag)) },
                            enabled = !busy && !conflict,
                        )
                    }
                    if (person == null) {
                        PhotoPersonPicker(people, query, { query = it }, !busy && !conflict) {
                            person = it
                        }
                    } else {
                        val chosen = requireNotNull(person)
                        val count = photos.count { chosen.id in it.people }
                        FilterChip(
                            selected = true,
                            onClick = { person = null },
                            label = {
                                Text(
                                    pluralStringResource(
                                        R.plurals.tagged_photo_person,
                                        photos.size,
                                        chosen.name,
                                        count,
                                        photos.size,
                                    )
                                )
                            },
                            enabled = !busy && !conflict,
                        )
                    }
                    OutlinedTextField(
                        value = tag,
                        onValueChange = { if (it.length <= 40) tag = it },
                        label = { Text(stringResource(R.string.manual_photo_tag)) },
                        singleLine = true,
                        enabled = !busy && !conflict,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    val commonTags = photos.flatMap { it.tags }.distinct().sorted().take(6)
                    if (commonTags.isNotEmpty()) {
                        Text(
                            stringResource(
                                R.string.existing_photo_tags,
                                commonTags.joinToString(", "),
                            ),
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
                error?.let {
                    val label =
                        when {
                            conflict -> R.string.photo_tags_conflict
                            it.hasStatus(413) || it.hasStatus(414) ->
                                R.string.photo_tags_batch_too_large
                            it.hasStatus(400) -> R.string.photo_tags_invalid
                            else -> errorLabel(it)
                        }
                    Text(stringResource(label), color = MaterialTheme.colorScheme.error)
                }
            }
        },
        confirmButton = {
            if (conflict) {
                Button(onClick = onReselect) { Text(stringResource(R.string.reselect_photos)) }
            } else {
                Button(
                    onClick = {
                        val photos = selection?.first ?: return@Button
                        if (busy) return@Button
                        busy = true
                        error = null
                        val personId = person?.id
                        val enteredTag = tag
                        val removing = remove
                        scope.launch {
                            attempt { api.savePhotoTags(photos, personId, enteredTag, removing) }
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
                    enabled = !busy && selection != null && (person != null || tag.isNotBlank()),
                    modifier = Modifier.testTag("save-photo-tags"),
                ) {
                    Text(
                        stringResource(
                            when {
                                busy -> R.string.saving
                                remove -> R.string.remove_photo_tag
                                else -> R.string.add_photo_tag
                            }
                        )
                    )
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onClose, enabled = !busy) { Text(stringResource(R.string.cancel)) }
        },
    )
}

@Composable
internal fun PhotoPersonPicker(
    people: List<Person>,
    query: String,
    onQuery: (String) -> Unit,
    enabled: Boolean = true,
    onSelect: (Person) -> Unit,
) {
    OutlinedTextField(
        value = query,
        onValueChange = onQuery,
        singleLine = true,
        label = { Text(stringResource(R.string.people_filter)) },
        enabled = enabled,
        modifier = Modifier.fillMaxWidth(),
    )
    val needle = searchableName(query.trim())
    val matches =
        people.filter { person ->
            searchableName(person.name).contains(needle) ||
                person.aliases.any { searchableName(it).contains(needle) }
        }
    matches.take(6).forEach { person ->
        TextButton(onClick = { onSelect(person) }, enabled = enabled) {
            Text(
                if (person.aliases.isEmpty()) person.name
                else "${person.name} · ${person.aliases.joinToString(", ")}"
            )
        }
    }
    if (matches.isEmpty()) Text(stringResource(R.string.no_results))
    if (matches.size > 6) Text(stringResource(R.string.narrow_people))
}
