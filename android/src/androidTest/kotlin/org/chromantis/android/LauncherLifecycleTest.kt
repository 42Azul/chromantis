package org.chromantis.android

import android.content.Context
import android.content.Intent
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.security.KeyStore
import java.security.cert.CertificateFactory
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManagerFactory
import org.json.JSONObject
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Exercises the exported launcher activity and its production preferences. */
@RunWith(AndroidJUnit4::class)
class LauncherLifecycleTest {
    @get:Rule val compose = createEmptyComposeRule()

    @Test
    fun launcherRestoresEncryptedSessionAndAlbumAfterRecreationAndFreshLaunch() {
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
        val context = instrumentation.targetContext
        val settings = context.getSharedPreferences("family_session", Context.MODE_PRIVATE)
        val keyAlias = "chromantis_family_session_v1"
        var scenario: ActivityScenario<ExplorerActivity>? = null
        fun label(id: Int) = context.getString(id)
        fun await(text: String) {
            compose.waitUntil(15000) {
                compose.onAllNodesWithText(text).fetchSemanticsNodes().isNotEmpty()
            }
        }
        fun click(text: String) = compose.onNodeWithText(text).performClick()
        fun clearLocalSession() {
            settings.edit().clear().commit()
            KeyStore.getInstance("AndroidKeyStore").apply {
                load(null)
                deleteEntry(keyAlias)
            }
        }
        try {
            clearLocalSession()
            settings.edit().putString("origin", config.getString("ui_origin")).commit()
            HttpsURLConnection.setDefaultSSLSocketFactory(tls.socketFactory)
            scenario = ActivityScenario.launch(Intent(context, ExplorerActivity::class.java))
            compose
                .onNodeWithText(label(R.string.code_label))
                .performScrollTo()
                .performTextInput(config.getString("launcher_code"))
            compose.onNodeWithText(label(R.string.sign_in)).performScrollTo().performClick()
            await("2023")
            compose.waitUntil(15000) { settings.contains("session_encrypted") }
            assertFalse(settings.contains("session"))

            click("2023")
            await("Excursion")
            click("Excursion")
            await(label(R.string.review_album))
            compose.waitUntil(15000) { settings.getString("resume_album", null) != null }

            requireNotNull(scenario).recreate()
            compose.onNodeWithText(label(R.string.review_album)).assertIsDisplayed()

            requireNotNull(scenario).close()
            scenario = null
            scenario = ActivityScenario.launch(Intent(context, ExplorerActivity::class.java))
            val resume = context.getString(R.string.resume_album, "Excursion")
            await(resume)
            click(resume)
            compose.onNodeWithText(label(R.string.review_album)).assertIsDisplayed()

            click(label(R.string.folders))
            await("2023")
            click(label(R.string.settings))
            click(label(R.string.sign_out))
            await(label(R.string.connect_title))
            assertFalse(settings.contains("session_encrypted"))
            assertFalse(settings.contains("session"))
            assertNotNull(settings.getString("origin", null))
        } finally {
            scenario?.close()
            HttpsURLConnection.setDefaultSSLSocketFactory(previous)
            clearLocalSession()
        }
    }
}
