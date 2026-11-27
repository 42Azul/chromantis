package org.chromantis.android

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun AlbumSearch(
    api: ChromantisApi,
    onExpired: () -> Unit,
    onConfirmedPhotos: () -> Unit,
    onOpenPhoto: (Entry) -> Unit,
    onOpen: (Entry) -> Unit,
    tag: String? = null,
    photoSearchBookmarks: List<PhotoSearchBookmark> = emptyList(),
    onSavePhotoSearch: ((PhotoSearchBookmark, Boolean) -> Unit)? = null,
) {
    var draft by rememberSaveable { mutableStateOf("") }
    var query by rememberSaveable { mutableStateOf<String?>(if (tag == null) null else "") }
    var summary by rememberSaveable { mutableStateOf("") }
    var error by remember { mutableStateOf<Int?>(null) }
    var choices by remember { mutableStateOf(emptyList<Entry>()) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val focus = LocalFocusManager.current

    fun start(text: String) {
        focus.clearFocus()
        query = text
        summary = text
        draft = ""
        choices = emptyList()
        error = null
    }

    fun refine(text: String, label: String = text) {
        busy = true
        error = null
        scope.launch {
            attempt { api.refineAlbums(query.orEmpty(), text, tag) }
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
        if (tag != null) focus.clearFocus()
        if (tag == null && query.isNullOrEmpty()) start(text) else refine(text)
    }

    var showTags by rememberSaveable { mutableStateOf(false) }
    if (showTags) {
        TagSearch(api, onExpired, onOpen, onOpenPhoto, photoSearchBookmarks, onSavePhotoSearch) {
            showTags = false
        }
        return
    }

    val activeQuery = query
    Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (tag != null) {
            Text(
                stringResource(R.string.exact_tag_results, tag),
                style = MaterialTheme.typography.titleLarge,
            )
        } else {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(
                        stringResource(R.string.search_title),
                        style = MaterialTheme.typography.headlineMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        stringResource(R.string.search_intro),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (activeQuery != null) {
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
            }
        }
        if (tag == null && activeQuery != null) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                Surface(
                    shape =
                        RoundedCornerShape(
                            topStart = 20.dp,
                            topEnd = 20.dp,
                            bottomEnd = 4.dp,
                            bottomStart = 20.dp,
                        ),
                    color = MaterialTheme.colorScheme.primaryContainer,
                ) {
                    Text(
                        summary,
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onPrimaryContainer,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
                        maxLines = 3,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
        SearchComposer(
            draft = draft,
            onDraft = { if (it.length <= 200) draft = it },
            active = activeQuery != null,
            enabled = !busy,
            onSubmit = ::submit,
        )
        if (tag == null) {
            OutlinedButton(onClick = { showTags = true }, enabled = !busy) {
                Text(stringResource(R.string.search_tags))
            }
        }
        if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        error?.let { Text(stringResource(it), color = MaterialTheme.colorScheme.error) }
        if (activeQuery == null) {
            Text(
                stringResource(R.string.search_try),
                style = MaterialTheme.typography.titleSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                listOf(
                        stringResource(R.string.search_example_person),
                        stringResource(R.string.search_example_place),
                        stringResource(R.string.search_example_date),
                    )
                    .forEach { prompt ->
                        AssistChip(onClick = { start(prompt) }, label = { Text(prompt) })
                    }
            }
            OutlinedButton(
                onClick = onConfirmedPhotos,
                shape = RoundedCornerShape(18.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                LibraryIcon(R.drawable.ic_photo, Modifier.size(18.dp))
                Spacer(Modifier.size(8.dp))
                Text(stringResource(R.string.confirmed_photo_search))
            }
        } else {
            Text(
                stringResource(R.string.search_results_title),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            Box(Modifier.weight(1f)) {
                key(activeQuery) {
                    EntryScreen(
                        folderApi = api,
                        load = { offset ->
                            api.albums(
                                activeQuery,
                                offset,
                                includeFilters = true,
                                tag = tag.orEmpty(),
                            )
                        },
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
    }
    if (choices.isNotEmpty()) {
        AlbumChoiceDialog(
            choices,
            onDismiss = { choices = emptyList() },
            onChoose = { album ->
                choices = emptyList()
                refine("álbum ${album.path}", albumDisplayTitle(album.title))
            },
        )
    }
}

@Composable
private fun SearchComposer(
    draft: String,
    onDraft: (String) -> Unit,
    active: Boolean,
    enabled: Boolean,
    onSubmit: () -> Unit,
) {
    val action = stringResource(if (active) R.string.refine else R.string.search)
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        OutlinedTextField(
            value = draft,
            onValueChange = onDraft,
            label = {
                Text(stringResource(if (active) R.string.refine_hint else R.string.search_hint))
            },
            singleLine = true,
            enabled = enabled,
            shape = RoundedCornerShape(20.dp),
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { onSubmit() }),
            modifier = Modifier.weight(1f),
        )
        Spacer(Modifier.size(8.dp))
        FilledIconButton(
            onClick = onSubmit,
            enabled = draft.isNotBlank() && enabled,
            modifier = Modifier.semantics { contentDescription = action },
        ) {
            LibraryIcon(R.drawable.ic_search, Modifier.size(20.dp))
        }
    }
}

@Composable
private fun AlbumChoiceDialog(
    choices: List<Entry>,
    onDismiss: () -> Unit,
    onChoose: (Entry) -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.choose_album)) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                choices.forEach { album ->
                    TextButton(modifier = Modifier.fillMaxWidth(), onClick = { onChoose(album) }) {
                        Column(Modifier.weight(1f)) {
                            Text(albumDisplayTitle(album.title), fontWeight = FontWeight.SemiBold)
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
        confirmButton = { TextButton(onClick = onDismiss) { Text(stringResource(R.string.back)) } },
    )
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
                trailingIcon = { LibraryIcon(R.drawable.ic_close, Modifier.size(16.dp)) },
                enabled = enabled,
                modifier = Modifier.semantics { contentDescription = description },
            )
        }
    }
}
