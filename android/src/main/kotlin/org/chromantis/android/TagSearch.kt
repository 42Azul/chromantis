package org.chromantis.android

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.FilterChip
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.res.stringResource

@Composable
internal fun TagSearch(
    api: ChromantisApi,
    onExpired: () -> Unit,
    onOpenAlbum: (Entry) -> Unit,
    onOpenPhoto: (Entry) -> Unit,
    bookmark: PhotoSearchBookmark?,
    onSaveBookmark: ((PhotoSearchBookmark) -> Unit)?,
    onExit: () -> Unit,
) {
    var photos by rememberSaveable { mutableStateOf(false) }
    var draft by rememberSaveable { mutableStateOf("") }
    var name by rememberSaveable { mutableStateOf("") }
    var selected by rememberSaveable { mutableStateOf<String?>(null) }
    var reopening by rememberSaveable { mutableStateOf(false) }
    val tag = selected
    val focus = LocalFocusManager.current
    val back = { if (tag == null) onExit() else selected = null }
    BackHandler(onBack = back)
    Column(Modifier.fillMaxSize()) {
        TextButton(onClick = back) { Text(stringResource(R.string.back)) }
        if (tag == null) {
            if (bookmark != null) {
                TextButton(
                    onClick = {
                        photos = true
                        reopening = true
                        selected = bookmark.tag
                    }
                ) {
                    Text(stringResource(R.string.reopen_photo_search, bookmark.tag))
                }
            }
            FilterChip(
                selected = !photos,
                onClick = { photos = false },
                label = { Text(stringResource(R.string.album_tag_catalog)) },
            )
            FilterChip(
                selected = photos,
                onClick = { photos = true },
                label = { Text(stringResource(R.string.photo_tag_catalog)) },
            )
            OutlinedTextField(
                value = draft,
                onValueChange = { if (it.length <= 80) draft = it },
                label = { Text(stringResource(R.string.tag_name_filter)) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            TextButton(
                onClick = {
                    focus.clearFocus()
                    name = draft.trim()
                }
            ) {
                Text(stringResource(R.string.filter_tags))
            }
        }
        Box(Modifier.weight(1f)) {
            key(photos, name, tag) {
                if (tag == null) {
                    EntryScreen(
                        load = { offset ->
                            val page = api.tagCatalog(photos, name, offset)
                            EntryPage(
                                page.items.map { Entry("${it.label} · ${it.count}", it.label) },
                                page.nextOffset,
                            )
                        },
                        onExpired = onExpired,
                        onOpen = {
                            reopening = false
                            selected = it.path
                        },
                    )
                } else if (photos) {
                    Column(Modifier.fillMaxSize()) {
                        ConfirmedPhotoSearch(
                            api,
                            onExpired,
                            exactTag = tag,
                            initialBookmark = bookmark.takeIf { reopening },
                            onSaveBookmark = onSaveBookmark,
                            onOpen = onOpenPhoto,
                        )
                    }
                } else {
                    AlbumSearch(
                        api = api,
                        onExpired = onExpired,
                        onConfirmedPhotos = {},
                        onOpenPhoto = onOpenPhoto,
                        onOpen = onOpenAlbum,
                        tag = tag,
                    )
                }
            }
        }
    }
}
