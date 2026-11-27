package org.chromantis.android

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale

/** Display formatting only: original names and indexed identities stay intact. */
internal fun albumDisplayTitle(title: String): String {
    val readable =
        title.replace(Regex("^\\d{4}(?:[-_ ]\\d{2}){2}[-_ ]+"), "").replace('_', ' ').trim()
    return readable.ifEmpty { title }.replaceFirstChar { it.titlecase() }
}

internal fun albumDisplayDate(path: String): String? {
    val date =
        Regex("^(\\d{4})[-_ ](\\d{2})[-_ ](\\d{2})").find(path.substringAfterLast('/'))
            ?: return null
    return runCatching {
            LocalDate.of(
                    date.groupValues[1].toInt(),
                    date.groupValues[2].toInt(),
                    date.groupValues[3].toInt(),
                )
                .format(
                    DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
                        .withLocale(Locale.forLanguageTag("es"))
                )
        }
        .getOrNull()
}

@Composable
internal fun LibraryIcon(id: Int, modifier: Modifier = Modifier.size(24.dp)) {
    Icon(painterResource(id), contentDescription = null, modifier = modifier)
}

@Composable
internal fun LibraryYears(page: EntryPage, onOpen: (Entry) -> Unit, onOrganize: () -> Unit) {
    LazyVerticalGrid(
        columns = GridCells.Adaptive(128.dp),
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(14.dp),
        horizontalArrangement = Arrangement.spacedBy(14.dp),
        contentPadding = PaddingValues(bottom = 20.dp),
    ) {
        item(span = { GridItemSpan(maxLineSpan) }) {
            Column(
                Modifier.padding(top = 12.dp, bottom = 8.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Text(
                    stringResource(R.string.library_title),
                    style = MaterialTheme.typography.headlineLarge,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    stringResource(R.string.library_by_year),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodyLarge,
                )
            }
        }
        itemsIndexed(
            page.entries.sortedByDescending { it.title },
            key = { _, entry -> entry.path },
        ) { index, entry ->
            val tint =
                if (index % 2 == 0) MaterialTheme.colorScheme.primaryContainer
                else MaterialTheme.colorScheme.tertiaryContainer
            Card(
                onClick = { onOpen(entry) },
                shape = RoundedCornerShape(24.dp),
                colors = CardDefaults.cardColors(containerColor = tint),
            ) {
                Column(
                    Modifier.fillMaxWidth().heightIn(min = 156.dp).padding(18.dp),
                    verticalArrangement = Arrangement.SpaceBetween,
                ) {
                    LibraryIcon(R.drawable.ic_folder, Modifier.size(28.dp))
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(
                            entry.title,
                            style = MaterialTheme.typography.headlineLarge,
                            fontWeight = FontWeight.SemiBold,
                        )
                        entry.albumCount?.let { count ->
                            Text(
                                pluralStringResource(R.plurals.album_count, count, count),
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        }
                    }
                }
            }
        }
        item(span = { GridItemSpan(maxLineSpan) }) {
            OutlinedCard(
                onClick = onOrganize,
                shape = RoundedCornerShape(24.dp),
                border = CardDefaults.outlinedCardBorder(),
            ) {
                Row(
                    Modifier.padding(18.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    Box(
                        Modifier.size(48.dp)
                            .background(MaterialTheme.colorScheme.secondaryContainer, CircleShape),
                        contentAlignment = Alignment.Center,
                    ) {
                        LibraryIcon(R.drawable.ic_organize)
                    }
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(
                            stringResource(R.string.library_review),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Text(
                            stringResource(R.string.library_review_help),
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            style = MaterialTheme.typography.bodyMedium,
                        )
                    }
                }
            }
        }
    }
}

@Composable
internal fun AlbumFolderCard(
    entry: Entry,
    api: ChromantisApi?,
    onExpired: () -> Unit,
    onOpen: () -> Unit,
) {
    var cover by remember(api, entry.path) { mutableStateOf<Bitmap?>(null) }
    LaunchedEffect(api, entry.path) {
        if (api != null) {
            attempt { api.albumCover(entry.path) }
                .onSuccess { cover = it }
                .onFailure { if (it.hasStatus(401)) onExpired() }
        }
    }
    Card(
        onClick = onOpen,
        shape = RoundedCornerShape(20.dp),
        colors =
            CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                Modifier.size(76.dp)
                    .clip(RoundedCornerShape(16.dp))
                    .background(MaterialTheme.colorScheme.primaryContainer),
                contentAlignment = Alignment.Center,
            ) {
                val image = cover
                if (image != null)
                    Image(
                        image.asImageBitmap(),
                        contentDescription = null,
                        contentScale = ContentScale.Crop,
                        modifier = Modifier.fillMaxSize().testTag("cover:${entry.path}"),
                    )
                else LibraryIcon(R.drawable.ic_folder, Modifier.size(28.dp))
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                Text(
                    albumDisplayTitle(entry.title),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    entry.eventDate?.let { date ->
                        val source =
                            when (entry.dateSource) {
                                "folder_name" -> stringResource(R.string.album_date_folder)
                                "album_correction" -> stringResource(R.string.album_date_corrected)
                                else -> null
                            }
                        listOfNotNull(date, source).joinToString(" · ")
                    } ?: albumDisplayDate(entry.path) ?: entry.path,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}
