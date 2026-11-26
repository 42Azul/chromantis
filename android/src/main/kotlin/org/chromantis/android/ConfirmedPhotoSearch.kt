package org.chromantis.android

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AssistChip
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp

@Composable
internal fun ConfirmedPhotoSearch(
    api: ChromantisApi,
    onExpired: () -> Unit,
    exactTag: String? = null,
    onOpen: (Entry) -> Unit,
) {
    var draft by rememberSaveable { mutableStateOf("") }
    var draftTag by rememberSaveable { mutableStateOf("") }
    var person by rememberSaveable { mutableStateOf("") }
    var tag by rememberSaveable { mutableStateOf("") }
    val focus = LocalFocusManager.current
    fun submit() {
        if (draft.isBlank()) return
        focus.clearFocus()
        person = draft.trim()
        tag = draftTag.trim()
    }
    Text(stringResource(R.string.confirmed_photo_explanation))
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        OutlinedTextField(
            value = draft,
            onValueChange = { if (it.length <= 100) draft = it },
            label = { Text(stringResource(R.string.people_filter)) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { submit() }),
            modifier = Modifier.weight(1f),
        )
        TextButton(onClick = ::submit, enabled = draft.isNotBlank()) {
            Text(stringResource(R.string.search))
        }
    }
    if (exactTag == null) {
        OutlinedTextField(
            value = draftTag,
            onValueChange = { if (it.length <= 40) draftTag = it },
            label = { Text(stringResource(R.string.confirmed_photo_tag)) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { submit() }),
            modifier = Modifier.fillMaxWidth(),
        )
    } else if (person.isNotEmpty()) {
        val label = stringResource(R.string.filter_person, person)
        val description = stringResource(R.string.remove_search_filter, label)
        AssistChip(
            onClick = {
                person = ""
                draft = ""
            },
            label = { Text(label) },
            trailingIcon = { LibraryIcon(R.drawable.ic_close, Modifier.size(16.dp)) },
            modifier = Modifier.semantics { contentDescription = description },
        )
    }
    if (exactTag == null && person.isNotEmpty()) {
        Text(stringResource(R.string.confirmed_photo_results, person))
        if (tag.isNotEmpty()) Text(stringResource(R.string.confirmed_photo_tag_result, tag))
    }
    if (exactTag != null || person.isNotEmpty()) {
        val activeTag = exactTag ?: tag
        key(person, activeTag) {
            EntryScreen(
                load = {
                    if (person.isEmpty()) api.taggedPhotos(activeTag, it)
                    else api.confirmedPhotos(person, it, activeTag)
                },
                onExpired = onExpired,
                onOpen = onOpen,
                photoApi = api,
            )
        }
    }
}
