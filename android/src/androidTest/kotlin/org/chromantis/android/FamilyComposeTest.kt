package org.chromantis.android

import android.content.ContentValues
import android.graphics.Bitmap
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.util.Log
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.security.KeyStore
import java.security.cert.CertificateFactory
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManagerFactory
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Hosts production composables without opening the activity's saved family preferences. */
@RunWith(AndroidJUnit4::class)
class FamilyComposeTest {
    @get:Rule val compose = createComposeRule()

    private fun capture(name: String) {
        Log.i("ChromantisFixture", "Capture $name")
        if (InstrumentationRegistry.getArguments().getString("captureScreenshots") != "true") return
        if (Build.VERSION.SDK_INT < 29) return
        val values =
            ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, "$name.png")
                put(MediaStore.MediaColumns.MIME_TYPE, "image/png")
                put(
                    MediaStore.MediaColumns.RELATIVE_PATH,
                    "${Environment.DIRECTORY_DOWNLOADS}/chromantis-compose",
                )
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            }
        val resolver = InstrumentationRegistry.getInstrumentation().targetContext.contentResolver
        val uri = requireNotNull(resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values))
        try {
            requireNotNull(resolver.openOutputStream(uri)).use {
                check(
                    compose
                        .onRoot()
                        .captureToImage()
                        .asAndroidBitmap()
                        .compress(Bitmap.CompressFormat.PNG, 100, it)
                )
            }
            values.clear()
            values.put(MediaStore.MediaColumns.IS_PENDING, 0)
            resolver.update(uri, values, null, null)
        } catch (error: Exception) {
            resolver.delete(uri, null, null)
            throw error
        }
    }

    @Test
    fun rendersDarkSignIn() {
        compose.setContent {
            MaterialTheme(colorScheme = darkPalette) {
                Surface(Modifier.fillMaxSize()) {
                    Column(Modifier.padding(16.dp)) { SignIn("https://10.0.2.2:8444", false) {} }
                }
            }
        }
        compose.onNodeWithTag("chromantis-mark").assertIsDisplayed()
        capture("sign-in-dark")
    }

    @Test
    fun signInBrowseCurateAndFindAnaInBothAppearances() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val assets = instrumentation.context.assets
        assumeTrue(assets.list("")!!.contains("fixture.json"))
        val config = assets.open("fixture.json").bufferedReader().use { JSONObject(it.readText()) }
        val trust = KeyStore.getInstance(KeyStore.getDefaultType()).apply { load(null) }
        trust.setCertificateEntry(
            "fixture",
            CertificateFactory.getInstance("X.509")
                .generateCertificate(config.getString("certificate").byteInputStream()),
        )
        val managers =
            TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm()).apply {
                init(trust)
            }
        val tls = SSLContext.getInstance("TLS").apply { init(null, managers.trustManagers, null) }
        val previous = HttpsURLConnection.getDefaultSSLSocketFactory()
        val api = mutableStateOf<ChromantisApi?>(null)
        val appearance = mutableStateOf(Appearance.LIGHT)
        val context = instrumentation.targetContext
        fun label(id: Int) = context.getString(id)
        fun await(text: String) {
            compose.waitUntil(15000) {
                compose.onAllNodesWithText(text).fetchSemanticsNodes().isNotEmpty()
            }
        }
        fun click(text: String) = compose.onNodeWithText(text).performClick()
        try {
            HttpsURLConnection.setDefaultSSLSocketFactory(tls.socketFactory)
            compose.setContent {
                MaterialTheme(
                    colorScheme =
                        if (appearance.value == Appearance.DARK) darkPalette else lightPalette
                ) {
                    Surface(Modifier.fillMaxSize()) {
                        Column(Modifier.padding(16.dp)) {
                            val client = api.value
                            if (client == null)
                                SignIn(config.getString("ui_origin"), false) { api.value = it }
                            else
                                Explorer(
                                    client,
                                    appearance.value,
                                    { appearance.value = it },
                                    null,
                                    {},
                                ) {
                                    api.value = null
                                }
                        }
                    }
                }
            }
            compose.onNodeWithTag("chromantis-mark").assertIsDisplayed()
            capture("sign-in-light")
            compose
                .onNodeWithText(label(R.string.code_label))
                .performScrollTo()
                .performTextInput(config.getString("ui_code"))
            compose.onNodeWithText(label(R.string.sign_in)).performScrollTo().performClick()
            await("2023")
            capture("folders-light")
            val client = compose.runOnIdle { api.value!! }
            val pending = runBlocking { client.review(null, 0)!! }
            compose
                .onNode(
                    hasText(label(R.string.organize)) and
                        SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.Tab)
                )
                .performClick()
            await(albumDisplayTitle(pending.title))
            compose.onNodeWithText(label(R.string.leave_pending)).assertIsDisplayed()
            compose.onNodeWithText(label(R.string.edit_review_details)).assertIsDisplayed()
            capture("classify-light")
            click(label(R.string.folders))
            await("2023")
            click("2023")
            val album = runBlocking { client.albums("2023", 0).entries.single() }
            await(albumDisplayTitle(album.title))
            compose.waitUntil(15000) {
                compose
                    .onAllNodesWithTag("cover:${album.path}", useUnmergedTree = true)
                    .fetchSemanticsNodes()
                    .isNotEmpty()
            }
            capture("albums-light")
            click(albumDisplayTitle(album.title))
            await(label(R.string.review_album))
            val visiblePhotos = runBlocking { client.photos(album.path, 0).entries }
            compose.waitUntil(15000) {
                visiblePhotos.all { photo ->
                    compose
                        .onAllNodesWithTag("thumbnail:${photo.path}", useUnmergedTree = true)
                        .fetchSemanticsNodes()
                        .isNotEmpty()
                }
            }
            capture("gallery-light")
            val tagShortcut = context.getString(R.string.search_album_by_tag, "excursion")
            compose.waitUntil(15000) {
                compose
                    .onAllNodesWithContentDescription(tagShortcut)
                    .fetchSemanticsNodes()
                    .isNotEmpty()
            }
            capture("album-shortcut-light")
            compose.runOnIdle { appearance.value = Appearance.DARK }
            capture("album-shortcut-dark")
            compose.runOnIdle { appearance.value = Appearance.LIGHT }
            compose.onNodeWithContentDescription(tagShortcut).performClick()
            await(context.getString(R.string.exact_tag_results, "excursion"))
            await(albumDisplayTitle(album.title))
            click(albumDisplayTitle(album.title))
            await(label(R.string.select_photos))
            compose.onNodeWithText(label(R.string.review_album)).assertDoesNotExist()
            compose.onNodeWithContentDescription(label(R.string.back)).performClick()
            await(context.getString(R.string.exact_tag_results, "excursion"))
            compose.onNodeWithContentDescription(label(R.string.back)).performClick()
            await(label(R.string.review_album))
            await(label(R.string.select_photos))
            compose
                .onNodeWithText(label(R.string.select_photos))
                .performSemanticsAction(SemanticsActions.OnClick)
            visiblePhotos.forEach { click(it.title) }
            compose.onNodeWithText(label(R.string.share_selection)).assertIsDisplayed()
            click(label(R.string.save_selection))
            await("2 originales guardados")
            compose.onNodeWithText(label(R.string.save_selection)).assertIsNotEnabled()
            click(label(R.string.make_collage))
            compose.waitUntil(15000) {
                compose
                    .onAllNodesWithContentDescription(label(R.string.collage_preview))
                    .fetchSemanticsNodes()
                    .isNotEmpty()
            }
            capture("collage-light")
            compose.runOnIdle { appearance.value = Appearance.DARK }
            capture("collage-dark")
            compose.runOnIdle { appearance.value = Appearance.LIGHT }
            click(label(R.string.save_collage))
            await(label(R.string.collage_saved))
            click(label(R.string.close_collage))
            capture("share-selection-light")
            compose.runOnIdle { appearance.value = Appearance.DARK }
            capture("share-selection-dark")
            compose.runOnIdle { appearance.value = Appearance.LIGHT }
            click(label(R.string.cancel))
            click(visiblePhotos.first().title)
            await(label(R.string.save_original))
            compose.onNodeWithText(label(R.string.share_original)).assertIsDisplayed()
            compose.onNodeWithText(label(R.string.save_original)).assertIsDisplayed()
            capture("original-light")
            compose.runOnIdle { appearance.value = Appearance.DARK }
            capture("original-dark")
            compose.runOnIdle { appearance.value = Appearance.LIGHT }
            click(album.title)
            await(label(R.string.review_album))
            click(label(R.string.review_album))
            await("Ana")
            compose.onNodeWithText("Ana").performScrollTo().performClick()
            capture("review-light")
            compose.onNodeWithText(label(R.string.save_album)).assertIsDisplayed().performClick()
            await(label(R.string.review_album))
            // Return through the folder trail, then use the real search form.
            click(label(R.string.folders))
            await("2023")
            click(label(R.string.settings))
            click(label(R.string.theme_dark))
            click(label(R.string.done))
            capture("folders-dark")
            click(label(R.string.search))
            compose.onNodeWithText(label(R.string.search_hint)).performTextInput("Anita")
            compose.onNodeWithContentDescription(label(R.string.search)).performClick()
            await(albumDisplayTitle(album.title))
            compose.onNodeWithText(albumDisplayTitle(album.title)).assertIsDisplayed()
            capture("search-dark")
            click(albumDisplayTitle(album.title))
            await(label(R.string.select_photos))
            compose.onNodeWithText(label(R.string.review_album)).assertDoesNotExist()
            compose.onNodeWithText(label(R.string.review_photos)).assertDoesNotExist()
            click(label(R.string.select_photos))
            click(visiblePhotos.first().title)
            compose.onNodeWithText(label(R.string.tag_photos)).assertDoesNotExist()
            compose.onNodeWithText(label(R.string.share_selection)).assertIsDisplayed()
            click(label(R.string.cancel))
            compose.onNodeWithContentDescription(label(R.string.back)).performClick()
            await(albumDisplayTitle(album.title))
            val photo = visiblePhotos.first()
            val otherPhoto = visiblePhotos.last()
            runBlocking {
                val ana = client.people().single { "Anita" in it.aliases }
                client.savePhotoTags(
                    client.photoTags(listOf(photo.path, otherPhoto.path)),
                    null,
                    "Romería",
                    remove = false,
                )
                client.savePhotoTags(
                    client.photoTags(listOf(photo.path)),
                    ana.id,
                    "",
                    remove = false,
                )
            }
            Log.i("ChromantisFixture", "Open tag catalog")
            click(label(R.string.search_tags))
            await(label(R.string.tag_name_filter))
            compose.onNodeWithText(label(R.string.tag_name_filter)).performTextInput("PLÁ")
            Log.i("ChromantisFixture", "Apply album tag name filter")
            click(label(R.string.filter_tags))
            await("Playa · 1")
            capture("tags-dark")
            compose.runOnIdle { appearance.value = Appearance.LIGHT }
            capture("tags-light")
            Log.i("ChromantisFixture", "Open exact album results")
            click("Playa · 1")
            await(context.getString(R.string.exact_tag_results, "playa"))
            val beach = runBlocking { client.albums("", 0, tag = "playa") }.entries.single()
            await(albumDisplayTitle(beach.title))
            fun refineTags(text: String) {
                compose.onNodeWithText(label(R.string.refine_hint)).performTextInput(text)
                compose.onNodeWithContentDescription(label(R.string.refine)).performClick()
            }
            refineTags("solo 2024")
            await("Año: 2024")
            refineTags("con Anita")
            await("Persona: Ana")
            await(label(R.string.no_results))
            capture("tag-refinements-light")
            compose.runOnIdle { appearance.value = Appearance.DARK }
            capture("tag-refinements-dark")
            compose.onNodeWithContentDescription("Quitar filtro de Persona: Ana").performClick()
            await(albumDisplayTitle(beach.title))
            compose.onNodeWithText("Año: 2024").assertIsDisplayed()
            compose.onNodeWithContentDescription("Quitar filtro de Año: 2024").performClick()
            await(albumDisplayTitle(beach.title))
            click(label(R.string.back))
            Log.i("ChromantisFixture", "Switch to photo tags")
            click(label(R.string.photo_tag_catalog))
            compose.onNodeWithText(label(R.string.tag_name_filter)).performTextClearance()
            compose.onNodeWithText(label(R.string.tag_name_filter)).performTextInput("ROMÉ")
            click(label(R.string.filter_tags))
            await("Romeria · 2")
            Log.i("ChromantisFixture", "Open exact photo results")
            click("Romeria · 2")
            await(photo.title)
            await(otherPhoto.title)
            compose.onNodeWithText(label(R.string.people_filter)).performTextInput("Anita")
            compose.onNodeWithText(label(R.string.people_filter)).performImeAction()
            await("Persona: Anita")
            await(photo.title)
            compose.onNodeWithText(otherPhoto.title).assertDoesNotExist()
            capture("photo-tag-person-dark")
            compose.runOnIdle { appearance.value = Appearance.LIGHT }
            capture("photo-tag-person-light")
            compose.onNodeWithText(label(R.string.photo_album_year)).performTextInput("2024")
            click(label(R.string.apply_photo_year))
            await("Año: 2024")
            await(label(R.string.no_results))
            capture("photo-tag-year-light")
            compose.runOnIdle { appearance.value = Appearance.DARK }
            capture("photo-tag-year-dark")
            compose.onNodeWithContentDescription("Quitar filtro de Año: 2024").performClick()
            await(photo.title)
            compose.onNodeWithText("Persona: Anita").assertIsDisplayed()
            compose.onNodeWithContentDescription("Quitar filtro de Persona: Anita").performClick()
            await(otherPhoto.title)
            compose.onNodeWithText(label(R.string.people_filter)).performTextInput("Anita")
            compose.onNodeWithText(label(R.string.people_filter)).performImeAction()
            await("Persona: Anita")
            await(photo.title)
            click(photo.title)
            val photoShortcut = context.getString(R.string.search_photo_by_tag, "romeria")
            compose.waitUntil(15000) {
                compose
                    .onAllNodesWithContentDescription(photoShortcut)
                    .fetchSemanticsNodes()
                    .isNotEmpty()
            }
            await(label(R.string.save_original))
            capture("photo-shortcut-dark")
            compose.runOnIdle { appearance.value = Appearance.LIGHT }
            capture("photo-shortcut-light")
            compose.onNodeWithContentDescription(photoShortcut).performClick()
            await(context.getString(R.string.exact_tag_results, "romeria"))
            await(otherPhoto.title)
            compose.onNodeWithContentDescription(label(R.string.back)).performClick()
            await(label(R.string.save_original))
            compose.onNodeWithContentDescription(label(R.string.back)).performClick()
            await("Persona: Anita")
            await(photo.title)
            compose.onNodeWithText(otherPhoto.title).assertDoesNotExist()
            // Exercise a scrolled second page with a filter active.
            val lastBeachPhoto = runBlocking {
                val first = client.photos(beach.path, 0)
                val second = client.photos(beach.path, requireNotNull(first.nextOffset))
                for (page in listOf(first, second)) {
                    client.savePhotoTags(
                        client.photoTags(page.entries.map { it.path }),
                        null,
                        "Paseo",
                        remove = false,
                    )
                }
                second.entries.last()
            }
            click(label(R.string.back))
            compose.onNodeWithText(label(R.string.tag_name_filter)).performTextClearance()
            compose.onNodeWithText(label(R.string.tag_name_filter)).performTextInput("Paseo")
            click(label(R.string.filter_tags))
            await("Paseo · 59")
            click("Paseo · 59")
            await(label(R.string.next))
            compose.onNodeWithText(label(R.string.photo_album_year)).performTextInput("2024")
            click(label(R.string.apply_photo_year))
            await("Año: 2024")
            await(label(R.string.next))
            click(label(R.string.next))
            await(label(R.string.previous))
            compose
                .onNode(hasScrollToIndexAction())
                .performScrollToNode(hasText(lastBeachPhoto.title))
            click(lastBeachPhoto.title)
            await(label(R.string.save_original))
            compose.onNodeWithContentDescription(label(R.string.back)).performClick()
            await(lastBeachPhoto.title)
            compose.onNodeWithText(lastBeachPhoto.title).assertIsDisplayed()
            compose.onNodeWithText("Año: 2024").assertIsDisplayed()
            compose.onNodeWithText(label(R.string.previous)).assertIsDisplayed()
            capture("search-return-light")
            compose.runOnIdle { appearance.value = Appearance.DARK }
            capture("search-return-dark")
            compose.runOnIdle { appearance.value = Appearance.LIGHT }
            click(label(R.string.back))
            click(label(R.string.album_tag_catalog))
            compose.onNodeWithText(label(R.string.tag_name_filter)).performTextClearance()
            compose.onNodeWithText(label(R.string.tag_name_filter)).performTextInput("Merienda")
            click(label(R.string.filter_tags))
            await("Merienda · 40")
            compose.onNodeWithText("Merienda · 40").performSemanticsAction(SemanticsActions.OnClick)
            await(context.getString(R.string.exact_tag_results, "merienda"))
            refineTags("solo 2025")
            await("Año: 2025")
            await(label(R.string.next))
            click(label(R.string.next))
            await(label(R.string.previous))
            val lastSnackAlbum = runBlocking {
                client.albums("2025", ChromantisApi.pageSize, tag = "merienda").entries.last()
            }
            val lastSnackTitle = albumDisplayTitle(lastSnackAlbum.title)
            compose.onNode(hasScrollToIndexAction()).performScrollToNode(hasText(lastSnackTitle))
            click(lastSnackTitle)
            await(lastSnackAlbum.path)
            compose.onNodeWithContentDescription(label(R.string.back)).performClick()
            await(lastSnackTitle)
            compose.onNodeWithText(lastSnackTitle).assertIsDisplayed()
            compose.onNodeWithText("Año: 2025").assertIsDisplayed()
            compose.onNodeWithText(label(R.string.previous)).assertIsDisplayed()
            capture("album-search-return-light")
            compose.runOnIdle { appearance.value = Appearance.DARK }
            capture("album-search-return-dark")
            click(label(R.string.settings))
            click(label(R.string.sign_out))
            await(label(R.string.connect_title))
        } finally {
            api.value?.let { runBlocking { it.signOut() } }
            HttpsURLConnection.setDefaultSSLSocketFactory(previous)
        }
    }
}
