package org.chromantis.android

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
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
import androidx.compose.ui.text.input.ImeAction

@Composable
internal fun ConfirmedPhotoSearch(
    api: ChromantisApi,
    onExpired: () -> Unit,
    onOpen: (Entry) -> Unit,
) {
    var draft by rememberSaveable { mutableStateOf("") }
    var person by rememberSaveable { mutableStateOf("") }
    val focus = LocalFocusManager.current
    fun submit() {
        if (draft.isBlank()) return
        focus.clearFocus()
        person = draft.trim()
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
    if (person.isNotEmpty()) {
        Text(stringResource(R.string.confirmed_photo_results, person))
        key(person) {
            EntryScreen(
                load = { api.confirmedPhotos(person, it) },
                onExpired = onExpired,
                onOpen = onOpen,
                photoApi = api,
            )
        }
    }
}
