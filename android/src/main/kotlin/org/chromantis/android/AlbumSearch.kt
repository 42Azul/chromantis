package org.chromantis.android

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

@Composable
internal fun AlbumSearch(api: ChromantisApi, onExpired: () -> Unit, onOpen: (Entry) -> Unit) {
    var draft by rememberSaveable { mutableStateOf("") }
    var query by rememberSaveable { mutableStateOf<String?>(null) }
    var summary by rememberSaveable { mutableStateOf("") }
    var error by remember { mutableStateOf<Int?>(null) }
    var choices by remember { mutableStateOf(emptyList<Entry>()) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val focus = LocalFocusManager.current

    fun refine(text: String, label: String = text) {
        busy = true
        error = null
        scope.launch {
            attempt { api.refineAlbums(query.orEmpty(), text) }
                .onSuccess { result ->
                    choices = result.choices
                    result.query?.let {
                        query = it
                        summary = listOf(summary, label).joinToString(" · ").takeLast(400)
                        draft = ""
                    }
                }
                .onFailure {
                    if (it.hasStatus(401)) onExpired()
                    else {
                        error =
                            if (it.hasStatus(400)) R.string.invalid_refinement else errorLabel(it)
                    }
                }
            busy = false
        }
    }

    fun submit() {
        val text = draft.trim()
        if (text.isEmpty() || busy) return
        focus.clearFocus()
        if (query.isNullOrEmpty()) {
            query = text
            summary = text
            draft = ""
        } else {
            refine(text)
        }
    }

    Text(
        stringResource(
            if (query.isNullOrEmpty()) R.string.start_search_help else R.string.refine_search_help
        ),
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(vertical = 8.dp),
    )
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        OutlinedTextField(
            value = draft,
            onValueChange = { if (it.length <= 200) draft = it },
            label = {
                Text(
                    stringResource(
                        if (query.isNullOrEmpty()) R.string.search_hint else R.string.refine_hint
                    )
                )
            },
            singleLine = true,
            enabled = !busy,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { submit() }),
            modifier = Modifier.weight(1f),
        )
        TextButton(onClick = ::submit, enabled = draft.isNotBlank() && !busy) {
            Text(stringResource(if (query.isNullOrEmpty()) R.string.search else R.string.refine))
        }
    }
    if (busy) Text(stringResource(R.string.loading), Modifier.padding(top = 8.dp))
    error?.let { Text(stringResource(it), color = MaterialTheme.colorScheme.error) }
    if (choices.isNotEmpty()) {
        AlertDialog(
            onDismissRequest = { choices = emptyList() },
            title = { Text(stringResource(R.string.choose_album)) },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState())) {
                    choices.forEach { album ->
                        TextButton(
                            modifier = Modifier.fillMaxWidth(),
                            onClick = {
                                choices = emptyList()
                                refine("álbum ${album.path}", album.title)
                            },
                        ) {
                            Column(Modifier.weight(1f)) {
                                Text(album.title)
                                Text(
                                    album.path,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { choices = emptyList() }) {
                    Text(stringResource(R.string.back))
                }
            },
        )
    }
    val activeQuery = query
    if (activeQuery != null) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(
                summary,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.weight(1f),
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            TextButton(
                onClick = {
                    query = null
                    summary = ""
                    draft = ""
                    choices = emptyList()
                    error = null
                },
                enabled = !busy,
            ) {
                Text(stringResource(R.string.new_search))
            }
        }
        key(activeQuery) {
            EntryScreen(
                load = { offset -> api.albums(activeQuery, offset, includeFilters = true) },
                onExpired = onExpired,
                onOpen = onOpen,
                header = { page ->
                    page.searchFilters?.let { filters ->
                        AlbumFilterChips(filters.active, enabled = !busy) { filter ->
                            query = filter.without
                            summary = filters.text
                            draft = ""
                            choices = emptyList()
                            error = null
                        }
                    }
                },
            )
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun AlbumFilterChips(
    filters: List<AlbumFilter>,
    enabled: Boolean,
    onRemove: (AlbumFilter) -> Unit,
) {
    if (filters.isEmpty()) return
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        filters.forEach { filter ->
            val label =
                when (filter.kind) {
                    "year" -> stringResource(R.string.filter_year, filter.label)
                    "person" -> stringResource(R.string.filter_person, filter.label)
                    "album" -> stringResource(R.string.filter_album, filter.label)
                    else -> filter.label
                }
            val description = stringResource(R.string.remove_search_filter, label)
            AssistChip(
                onClick = { onRemove(filter) },
                label = { Text(label, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                trailingIcon = { Text("×") },
                enabled = enabled,
                modifier = Modifier.semantics { contentDescription = description },
            )
        }
    }
}
