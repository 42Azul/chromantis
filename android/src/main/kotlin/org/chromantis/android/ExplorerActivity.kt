package org.chromantis.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilledTonalIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.listSaver
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.edit
import androidx.core.view.WindowCompat
import javax.net.ssl.SSLException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

class ExplorerActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val settings = getSharedPreferences("family_session", MODE_PRIVATE)
        val address = settings.getString("origin", "").orEmpty()
        val hadSavedSession = settings.contains("session") || settings.contains("session_encrypted")
        val sessionStore = familySessionStore(settings)
        val secret = sessionStore.restore(address)
        val savedSession = secret?.let { runCatching { ChromantisApi(address, it) }.getOrNull() }
        setContent {
            var appearance by remember {
                mutableStateOf(Appearance.fromPreference(settings.getString("appearance", null)))
            }
            val dark = appearance.isDark(isSystemInDarkTheme())
            SideEffect {
                WindowCompat.getInsetsController(window, window.decorView).apply {
                    isAppearanceLightStatusBars = !dark
                    isAppearanceLightNavigationBars = !dark
                }
            }
            MaterialTheme(colorScheme = if (dark) darkPalette else lightPalette) {
                Surface(modifier = Modifier.fillMaxSize()) {
                    var api by remember { mutableStateOf(savedSession) }
                    var expired by remember { mutableStateOf(false) }
                    var sessionSaved by remember { mutableStateOf(true) }
                    var restoreFailed by remember {
                        mutableStateOf(hadSavedSession && savedSession == null)
                    }
                    var resumeAlbum by remember {
                        mutableStateOf(
                            if (savedSession == null) null
                            else AlbumResume.decode(settings.getString("resume_album", null))
                        )
                    }
                    Column(Modifier.systemBarsPadding().imePadding().padding(horizontal = 16.dp)) {
                        val active = api
                        if (active == null) {
                            if (restoreFailed) Text(stringResource(R.string.session_restore_failed))
                            SignIn(settings.getString("origin", address).orEmpty(), expired) {
                                restoreFailed = false
                                sessionSaved =
                                    it.secret?.let { secret ->
                                        sessionStore.save(it.origin, secret)
                                    } == true
                                settings.edit { remove("resume_album") }
                                api = it
                            }
                        } else {
                            if (!sessionSaved) Text(stringResource(R.string.session_not_saved))
                            key(active.origin) {
                                Explorer(
                                    active,
                                    appearance,
                                    { mode ->
                                        appearance = mode
                                        settings.edit { putString("appearance", mode.name) }
                                    },
                                    resumeAlbum = resumeAlbum,
                                    onAlbumVisited = { resume ->
                                        if (resume != resumeAlbum) {
                                            resumeAlbum = resume
                                            settings.edit {
                                                putString("resume_album", resume.encode())
                                            }
                                        }
                                    },
                                ) { sessionExpired ->
                                    sessionStore.clear()
                                    settings.edit { remove("resume_album") }
                                    resumeAlbum = null
                                    expired = sessionExpired
                                    api = null
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

internal enum class Level {
    YEARS,
    ASK,
    ALBUMS,
    SEARCH,
    CONFIRMED,
    INDEX,
    PHOTOS,
    ORIGINAL,
    REVIEW,
}

internal data class Page(val level: Level, val title: String, val path: String? = null)

internal val explorerPagesSaver =
    listSaver<List<Page>, String>(
        save = { pages -> pages.flatMap { listOf(it.level.name, it.title, it.path.orEmpty()) } },
        restore = { fields ->
            fields.chunked(3).map { (level, title, path) ->
                Page(Level.valueOf(level), title, path.ifEmpty { null })
            }
        },
    )

@Composable
internal fun Explorer(
    api: ChromantisApi,
    appearance: Appearance,
    onAppearance: (Appearance) -> Unit,
    resumeAlbum: AlbumResume?,
    onAlbumVisited: (AlbumResume) -> Unit,
    endSession: (Boolean) -> Unit,
) {
    val folders = stringResource(R.string.folders)
    val organize = stringResource(R.string.organize)
    val search = stringResource(R.string.search)
    val confirmedTitle = stringResource(R.string.confirmed_photo_search)
    val indexTitle = stringResource(R.string.index_title)
    val reviewTitle = stringResource(R.string.review_albums)
    val workspaces =
        listOf(Page(Level.YEARS, folders), Page(Level.REVIEW, organize), Page(Level.ASK, search))
    var pages by
        rememberSaveable(stateSaver = explorerPagesSaver) {
            mutableStateOf(listOf(Page(Level.YEARS, folders)))
        }
    val savedScreens = rememberSaveableStateHolder()
    var galleryStartOffset by rememberSaveable { mutableIntStateOf(0) }
    val page = pages.last()
    val depth = pages.lastIndex
    val workspace = pages.first()
    val screenKey = "${workspace.level.name}:$depth"
    val scope = rememberCoroutineScope()
    val focus = LocalFocusManager.current
    val connect: () -> Unit = connect@{
        val endpoint =
            try {
                ChromantisApi(origin)
            } catch (_: IllegalArgumentException) {
                error = R.string.invalid_address
                return@connect
            }
        focus.clearFocus()
        busy = true
        error = null
        scope.launch {
            attempt { endpoint.signIn(code.trim()) }
                .fold(
                    onSuccess = onConnected,
                    onFailure = {
                        error =
                            if (it.hasStatus(401)) R.string.invalid_code else errorLabel(it)
                        busy = false
                    },
                )
        }
    }
    var signingOut by remember { mutableStateOf(false) }
    var signOutError by remember { mutableStateOf<Throwable?>(null) }
    var showSettings by rememberSaveable { mutableStateOf(false) }
    fun goToAncestor(index: Int) {
        for (removed in depth downTo index + 1) {
            savedScreens.removeState("${workspace.level.name}:$removed")
        }
        pages = pages.take(index + 1)
    }
    fun goBack() {
        if (depth > 0) goToAncestor(depth - 1) else pages = listOf(workspaces.first())
    }
    val expire = { endSession(true) }
    BackHandler(enabled = depth > 0 || workspace.level != Level.YEARS) { goBack() }
    val destinations: @Composable () -> Unit = {
        val icons = listOf(R.drawable.ic_library, R.drawable.ic_organize, R.drawable.ic_search)
        NavigationBar(
            containerColor = MaterialTheme.colorScheme.surfaceContainer,
            windowInsets = WindowInsets(0, 0, 0, 0),
            modifier = Modifier.clip(RoundedCornerShape(26.dp)),
        ) {
            workspaces.forEachIndexed { index, tab ->
                NavigationBarItem(
                    selected = workspace.level == tab.level,
                    onClick = {
                        focus.clearFocus()
                        pages = listOf(tab)
                    },
                    icon = { LibraryIcon(icons[index]) },
                    label = { Text(tab.title) },
                )
            }
        }
    }
    Column(Modifier.fillMaxSize()) {
        if (depth == 0) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(
                    stringResource(R.string.app_name),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f),
                )
                TextButton(onClick = { showSettings = true }, enabled = !signingOut) {
                    LibraryIcon(R.drawable.ic_settings, Modifier.size(18.dp))
                    Spacer(Modifier.size(6.dp))
                    Text(stringResource(R.string.settings))
                }
            }
            if (signingOut) Text(stringResource(R.string.closing_session))
            signOutError?.let { Text(stringResource(errorLabel(it))) }
        } else {
            val ancestors = folderAncestors(pages)
            if (ancestors.isEmpty()) {
                Heading(page.title, ::goBack)
            } else {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    ancestors.forEachIndexed { index, ancestor ->
                        TextButton(
                            onClick = { goToAncestor(index) },
                            modifier = Modifier.weight(1f, fill = false),
                        ) {
                            Text(ancestor.title, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                    }
                }
                Heading(page.title)
            }
        }
        if (showSettings) {
            SettingsDialog(
                appearance,
                onAppearance,
                onClose = { showSettings = false },
                onIndex = {
                    showSettings = false
                    pages = pages + Page(Level.INDEX, indexTitle)
                },
                onSignOut = {
                    showSettings = false
                    signingOut = true
                    signOutError = null
                    scope.launch {
                        attempt { api.signOut() }
                            .fold(
                                onSuccess = { endSession(false) },
                                onFailure = {
                                    signOutError = it
                                    signingOut = false
                                },
                            )
                    }
                },
            )
        }
        Column(Modifier.weight(1f)) {
            savedScreens.SaveableStateProvider(screenKey) {
                when (page.level) {
                    Level.INDEX -> IndexStatusScreen(api, expire)
                    Level.ASK -> {
                        AlbumSearch(
                            api,
                            expire,
                            onConfirmedPhotos = {
                                focus.clearFocus()
                                pages = pages + Page(Level.CONFIRMED, confirmedTitle)
                            },
                            onOpen = {
                                galleryStartOffset = 0
                                pages = pages + Page(Level.PHOTOS, it.title, it.path)
                            },
                        )
                    }
                    Level.CONFIRMED ->
                        ConfirmedPhotoSearch(api, expire) {
                            pages = pages + Page(Level.ORIGINAL, it.title, it.path)
                        }
                    Level.YEARS -> {
                        if (resumeAlbum != null) {
                            TextButton(
                                onClick = {
                                    galleryStartOffset = resumeAlbum.offset
                                    pages =
                                        listOf(
                                            workspaces.first(),
                                            resumeAlbum.year,
                                            resumeAlbum.album,
                                        )
                                }
                            ) {
                                Text(
                                    stringResource(
                                        R.string.resume_album,
                                        albumDisplayTitle(resumeAlbum.album.title),
                                    )
                                )
                            }
                        }
                        LoadContent(expire, load = { api.years() }) { years ->
                            LibraryYears(
                                years,
                                onOpen = { pages = pages + Page(Level.ALBUMS, it.title, it.path) },
                                onOrganize = { pages = listOf(workspaces[1]) },
                            )
                        }
                    }
                    Level.ALBUMS,
                    Level.SEARCH -> {
                        EntryScreen(
                            folderApi = api,
                            load = { offset ->
                                if (page.level == Level.YEARS) api.years()
                                else api.albums(page.path.orEmpty(), offset)
                            },
                            onExpired = expire,
                            onOpen = { entry ->
                                val level =
                                    if (page.level == Level.YEARS) Level.ALBUMS else Level.PHOTOS
                                galleryStartOffset = 0
                                pages = pages + Page(level, entry.title, entry.path)
                            },
                        )
                    }
                    Level.PHOTOS -> {
                        Text(page.path.orEmpty(), style = MaterialTheme.typography.bodySmall)
                        TextButton(
                            onClick = { pages = pages + Page(Level.REVIEW, reviewTitle, page.path) }
                        ) {
                            Text(stringResource(R.string.review_album))
                        }
                        EntryScreen(
                            load = { api.photos(requireNotNull(page.path), it) },
                            onExpired = expire,
                            onOpen = { pages = pages + Page(Level.ORIGINAL, it.title, it.path) },
                            photoApi = api,
                            allowPhotoEdits = true,
                            initialOffset = galleryStartOffset,
                            onPageLoaded = { offset ->
                                albumResume(pages, offset)?.let(onAlbumVisited)
                            },
                        )
                    }
                    Level.ORIGINAL ->
                        OriginalPhoto(api, requireNotNull(page.path), page.title, expire)
                    Level.REVIEW -> AlbumReview(api, page.path, expire, ::goBack)
                }
            }
        }
        if (depth == 0) destinations()
    }
}

@Composable
private fun Heading(title: String, back: (() -> Unit)? = null) {
    Row(Modifier.padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        if (back != null) {
            FilledTonalIconButton(onClick = back, modifier = Modifier.size(40.dp)) {
                Icon(
                    painterResource(R.drawable.ic_back),
                    contentDescription = stringResource(R.string.back),
                )
            }
            Spacer(Modifier.size(12.dp))
        }
        Text(
            albumDisplayTitle(title),
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.SemiBold,
        )
    }
}

@Composable
internal fun SignIn(address: String, expired: Boolean, onConnected: (ChromantisApi) -> Unit) {
    var origin by rememberSaveable { mutableStateOf(address) }
    var code by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<Int?>(if (expired) R.string.expired_session else null) }
    val scope = rememberCoroutineScope()
    val focus = LocalFocusManager.current
    Column(
        Modifier.fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(top = 20.dp, bottom = 20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Image(
                painterResource(R.drawable.ic_chromantis),
                contentDescription = null,
                modifier = Modifier.size(56.dp).clip(RoundedCornerShape(16.dp)),
            )
            Column(Modifier.padding(start = 16.dp)) {
                Text(
                    stringResource(R.string.app_name),
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.primary,
                )
                Text(
                    stringResource(R.string.connect_title),
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.SemiBold,
                )
            }
        }
        Text(
            stringResource(R.string.connect_intro),
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Card(
            colors =
                CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceContainer
                ),
            shape = RoundedCornerShape(24.dp),
        ) {
            Column(
                Modifier.fillMaxWidth().padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    stringResource(R.string.address_step),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                OutlinedTextField(
                    value = origin,
                    onValueChange = { origin = it },
                    label = { Text(stringResource(R.string.address_label)) },
                    placeholder = { Text(stringResource(R.string.address_hint)) },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                    singleLine = true,
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth(),
                )
                Text(
                    stringResource(R.string.code_step),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.padding(top = 4.dp),
                )
                Text(
                    stringResource(R.string.code_help),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                OutlinedTextField(
                    value = code,
                    onValueChange = { code = it },
                    label = { Text(stringResource(R.string.code_label)) },
                    placeholder = { Text(stringResource(R.string.code_hint)) },
                    keyboardOptions =
                        KeyboardOptions(
                            keyboardType = KeyboardType.Password,
                            imeAction = ImeAction.Done,
                        ),
                    keyboardActions = KeyboardActions(onDone = { if (!busy) connect() }),
                    visualTransformation = PasswordVisualTransformation(),
                    singleLine = true,
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth(),
                )
                error?.let { Text(stringResource(it), color = MaterialTheme.colorScheme.error) }
                Button(
                    onClick = connect,
                    enabled = code.isNotBlank() && !busy,
                    modifier = Modifier.fillMaxWidth().height(52.dp),
                ) {
                    Text(stringResource(if (busy) R.string.connecting else R.string.sign_in))
                }
            }
        }
        Surface(
            color = MaterialTheme.colorScheme.primaryContainer,
            contentColor = MaterialTheme.colorScheme.onPrimaryContainer,
            shape = RoundedCornerShape(18.dp),
        ) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(
                    stringResource(R.string.session_protected_title),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    stringResource(R.string.session_protected_help),
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
    }
}

@Composable
internal fun EntryScreen(
    load: suspend (Int) -> EntryPage,
    onExpired: () -> Unit,
    onOpen: (Entry) -> Unit,
    photoApi: ChromantisApi? = null,
    folderApi: ChromantisApi? = null,
    allowPhotoEdits: Boolean = false,
    initialOffset: Int = 0,
    onPageLoaded: ((Int) -> Unit)? = null,
    header: @Composable (EntryPage) -> Unit = {},
) {
    var offset by rememberSaveable { mutableIntStateOf(initialOffset) }
    var reload by remember { mutableIntStateOf(0) }
    key(offset, reload) {
        LoadContent(onExpired, load = { load(offset) }) { page ->
            if (onPageLoaded != null) {
                LaunchedEffect(page) {
                    if (page.entries.isEmpty() && offset > 0) offset = 0
                    else if (page.entries.isNotEmpty()) onPageLoaded(offset)
                }
            }
            var selected by rememberSaveable { mutableStateOf<List<String>?>(null) }
            var edit by remember { mutableStateOf(false) }
            var review by remember { mutableStateOf(false) }
            var saved by rememberSaveable { mutableStateOf(false) }
            val selection = selected
            BackHandler(selection != null && !edit) { selected = null }
            Column(Modifier.fillMaxSize()) {
                header(page)
                if (page.entries.isEmpty()) Text(stringResource(R.string.no_results))
                if (saved) {
                    Text(stringResource(R.string.photo_tags_saved))
                }
                if (allowPhotoEdits && page.entries.isNotEmpty()) {
                    if (selection == null) {
                        TextButton(
                            onClick = {
                                saved = false
                                selected = arrayListOf()
                            }
                        ) {
                            Text(stringResource(R.string.select_photos))
                        }
                        if (page.hasThumbnails) {
                            TextButton(onClick = { review = true }) {
                                Text(stringResource(R.string.review_photos))
                            }
                        }
                    } else {
                        Text(
                            pluralStringResource(
                                R.plurals.selected_photo_count,
                                selection.size,
                                selection.size,
                            )
                        )
                        Row {
                            Button(onClick = { edit = true }, enabled = selection.isNotEmpty()) {
                                Text(stringResource(R.string.tag_photos))
                            }
                            TextButton(onClick = { selected = null }) {
                                Text(stringResource(R.string.cancel))
                            }
                        }
                    }
                }
                if (photoApi != null) {
                    LazyVerticalGrid(
                        columns = GridCells.Adaptive(110.dp),
                        modifier = Modifier.weight(1f),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        items(page.entries, key = { it.path }) { entry ->
                            val checked = selection?.contains(entry.path) == true
                            val tile =
                                if (selection != null) {
                                    Modifier.toggleable(checked, role = Role.Checkbox) { select ->
                                        val current = selected.orEmpty()
                                        selected =
                                            if (select && entry.path !in current)
                                                current + entry.path
                                            else if (!select) current - entry.path else current
                                    }
                                } else if (allowPhotoEdits) {
                                    Modifier.combinedClickable(
                                        onClick = { onOpen(entry) },
                                        onLongClickLabel = stringResource(R.string.select_photos),
                                        onLongClick = {
                                            saved = false
                                            selected = arrayListOf(entry.path)
                                        },
                                    )
                                } else {
                                    Modifier.clickable { onOpen(entry) }
                                }
                            Column(
                                tile.padding(4.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                if (selection != null) Checkbox(checked, onCheckedChange = null)
                                if (page.hasThumbnails) Thumbnail(photoApi, entry, onExpired)
                                Text(
                                    entry.title,
                                    style = MaterialTheme.typography.bodySmall,
                                    maxLines = 2,
                                    overflow = TextOverflow.Ellipsis,
                                )
                            }
                        }
                    }
                } else {
                    LazyColumn(
                        Modifier.weight(1f),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        items(page.entries, key = { it.path }) { entry ->
                            AlbumFolderCard(entry, folderApi, onExpired) { onOpen(entry) }
                        }
                    }
                }
                if (selection == null && (offset > 0 || page.nextOffset != null)) {
                    Row {
                        if (offset > 0)
                            TextButton(onClick = { offset -= ChromantisApi.pageSize }) {
                                Text(stringResource(R.string.previous))
                            }
                        page.nextOffset?.let { next ->
                            TextButton(onClick = { offset = next }) {
                                Text(stringResource(R.string.next))
                            }
                        }
                    }
                }
            }
            if (edit && !selection.isNullOrEmpty() && photoApi != null) {
                PhotoTagDialog(
                    photoApi,
                    selection,
                    onExpired,
                    onClose = { edit = false },
                    onReselect = {
                        edit = false
                        selected = null
                        reload++
                    },
                    onSaved = {
                        edit = false
                        selected = null
                        saved = true
                    },
                )
            }
            if (review && photoApi != null) {
                PhotoSwipeReview(
                    api = photoApi,
                    entries = page.entries,
                    onExpired = onExpired,
                    onClose = { review = false },
                    onReload = { reload++ },
                    onSaved = {
                        review = false
                        saved = true
                    },
                )
            }
        }
    }
}

@Composable
internal fun Thumbnail(
    api: ChromantisApi,
    entry: Entry,
    onExpired: () -> Unit,
    modifier: Modifier = Modifier.fillMaxWidth().height(100.dp).clip(RoundedCornerShape(16.dp)),
    contentScale: ContentScale = ContentScale.Crop,
    identity: String? = null,
    onReady: () -> Unit = {},
) {
    var result by
        remember(api, entry.path, identity) {
            mutableStateOf<Result<android.graphics.Bitmap>?>(null)
        }
    LaunchedEffect(api, entry.path, identity) {
        val loaded = attempt { api.thumbnail(entry.path, identity) }
        result = loaded
        if (loaded.isSuccess) onReady()
        else if (loaded.exceptionOrNull()?.hasStatus(401) == true) onExpired()
    }
    Surface(modifier = modifier, color = MaterialTheme.colorScheme.surfaceVariant) {
        val bitmap = result?.getOrNull()
        if (bitmap != null)
            Image(
                bitmap.asImageBitmap(),
                null,
                contentScale = contentScale,
                modifier = Modifier.testTag("thumbnail:${entry.path}"),
            )
        else if (result?.isFailure == true) {
            Box(contentAlignment = Alignment.Center) {
                Text(stringResource(R.string.thumbnail_unavailable), Modifier.padding(4.dp))
            }
        }
    }
}

@Composable
internal fun OriginalPhoto(api: ChromantisApi, path: String, title: String, onExpired: () -> Unit) {
    LoadContent(onExpired, load = { api.photo(path) }) {
        Image(it.asImageBitmap(), title, Modifier.fillMaxWidth(), contentScale = ContentScale.Fit)
    }
}

@Composable
internal fun <T> LoadContent(
    onExpired: () -> Unit,
    load: suspend () -> T,
    content: @Composable (T) -> Unit,
) {
    var revision by remember { mutableIntStateOf(0) }
    var result by remember(revision) { mutableStateOf<Result<T>?>(null) }
    LaunchedEffect(revision) {
        val loaded = attempt { load() }
        if (loaded.exceptionOrNull()?.hasStatus(401) == true) onExpired() else result = loaded
    }
    val loaded = result
    if (loaded == null) Text(stringResource(R.string.loading))
    else
        loaded.fold(
            onSuccess = { content(it) },
            onFailure = {
                Text(stringResource(errorLabel(it)))
                TextButton(onClick = { revision++ }) { Text(stringResource(R.string.retry)) }
            },
        )
}

internal suspend fun <T> attempt(action: suspend () -> T): Result<T> =
    try {
        Result.success(action())
    } catch (error: CancellationException) {
        throw error
    } catch (error: Exception) {
        Result.failure(error)
    }

internal fun Throwable.hasStatus(status: Int) =
    this is ChromantisApi.HttpFailure && this.status == status

internal fun errorLabel(error: Throwable) =
    when {
        error is SSLException -> R.string.untrusted_certificate
        error.hasStatus(404) || error.hasStatus(422) -> R.string.content_unavailable
        error.hasStatus(403) -> R.string.operation_forbidden
        else -> R.string.request_failed
    }
