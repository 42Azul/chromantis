package org.chromantis.android

import android.content.Context
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.security.KeyStore
import java.security.cert.CertificateFactory
import java.util.UUID
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManagerFactory
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class FamilyClientIntegrationTest {
    @Test
    fun offlineAlbumCurationSurvivesSessionRestoreAndSignOutRevokesAccess() = runBlocking {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val assets = instrumentation.context.assets
        assumeTrue(
            "Start the synthetic HTTPS fixture first.",
            assets.list("")!!.contains("fixture.json"),
        )
        val config = assets.open("fixture.json").bufferedReader().use { JSONObject(it.readText()) }
        // Trust only the generated fixture certificate in this test process; keep hostname checks.
        val trust = KeyStore.getInstance(KeyStore.getDefaultType()).apply { load(null) }
        val certificate =
            CertificateFactory.getInstance("X.509")
                .generateCertificate(config.getString("certificate").byteInputStream())
        trust.setCertificateEntry("synthetic", certificate)
        val managers =
            TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm()).apply {
                init(trust)
            }
        val tls = SSLContext.getInstance("TLS").apply { init(null, managers.trustManagers, null) }
        val previous = HttpsURLConnection.getDefaultSSLSocketFactory()
        val context = instrumentation.targetContext
        val name = "chromantis_client_test_${UUID.randomUUID()}"
        val settings = context.getSharedPreferences(name, Context.MODE_PRIVATE)
        val store = familySessionStore(settings, name)
        try {
            HttpsURLConnection.setDefaultSSLSocketFactory(tls.socketFactory)
            val origin = config.getString("origin")
            val guest = ChromantisApi(origin)
            expectStatus(401) { guest.years() }
            val signedIn = guest.signIn(config.getString("code"))
            expectStatus(401) { guest.signIn(config.getString("code")) }
            assertTrue(store.save(origin, signedIn.secret!!))
            val client = ChromantisApi(origin, familySessionStore(settings, name).restore(origin))
            assertTrue(client.years().entries.any { it.title == "2024" })
            val album = client.albums("2024", 0).entries.single()
            val first = client.photos(album.path, 0)
            assertEquals(30, first.entries.size)
            val second = client.photos(album.path, first.nextOffset!!)
            assertEquals(3, second.entries.size)
            assertEquals(null, second.nextOffset)
            val label = client.tagCatalog(photos = false, name = "PLÁ", offset = 0).items.single()
            assertEquals(CatalogTag("playa", 1), label)
            assertEquals(album.path, client.albums("", 0, tag = label.label).entries.single().path)
            val photoPath = second.entries.first().path
            client.savePhotoTags(
                client.photoTags(listOf(photoPath)),
                null,
                "Romería",
                remove = false,
            )
            val photoLabel =
                client.tagCatalog(photos = true, name = "ROMÉ", offset = 0).items.single()
            assertEquals(CatalogTag("romeria", 1), photoLabel)
            assertEquals(photoPath, client.taggedPhotos(photoLabel.label, 0).entries.single().path)
            // No archive is mounted: metadata works, opening a photo fails explicitly.
            expectStatus(404) { client.photo(second.entries.first().path) }
            val ana = client.people().single { "Anita" in it.aliases }
            val review = client.review(album.path, 0)!!
            client.saveReview(review, review.people + ana.id, "", emptyMap())
            assertTrue(ana.id in client.review(album.path, 0)!!.people)
            assertEquals(album.path, client.albums("Anita", 0).entries.single().path)
            client.signOut()
            expectStatus(401) { client.years() }
            store.clear()
            assertFalse(settings.contains("session_encrypted"))
        } finally {
            HttpsURLConnection.setDefaultSSLSocketFactory(previous)
            context.deleteSharedPreferences(name)
            KeyStore.getInstance("AndroidKeyStore").apply {
                load(null)
                deleteEntry(name)
            }
        }
    }

    private suspend fun expectStatus(status: Int, action: suspend () -> Unit) {
        val failure =
            try {
                action()
                null
            } catch (error: ChromantisApi.HttpFailure) {
                error
            }
        assertEquals(status, failure?.status)
    }
}
