package org.chromantis.android

import android.content.ContentValues
import android.graphics.Bitmap
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asAndroidBitmap
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
        fun capture(name: String) {
            if (InstrumentationRegistry.getArguments().getString("captureScreenshots") != "true")
                return
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
            val resolver = context.contentResolver
            val uri =
                requireNotNull(resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values))
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
            compose
                .onNodeWithText(label(R.string.code_label))
                .performTextInput(config.getString("ui_code"))
            click(label(R.string.sign_in))
            await("2023")
            capture("folders-light")
            click("2023")
            val client = compose.runOnIdle { api.value!! }
            val album = runBlocking { client.albums("2023", 0).entries.single() }
            await(albumDisplayTitle(album.title))
            compose.waitUntil(15000) {
                compose.onAllNodesWithTag("cover:${album.path}").fetchSemanticsNodes().isNotEmpty()
            }
            capture("albums-light")
            click(albumDisplayTitle(album.title))
            await(label(R.string.review_album))
            capture("gallery-light")
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
            compose.onAllNodesWithText(label(R.string.search)).onLast().performClick()
            await(albumDisplayTitle(album.title))
            compose.onNodeWithText(albumDisplayTitle(album.title)).assertIsDisplayed()
        } finally {
            api.value?.let { runBlocking { it.signOut() } }
            HttpsURLConnection.setDefaultSSLSocketFactory(previous)
        }
    }
}
