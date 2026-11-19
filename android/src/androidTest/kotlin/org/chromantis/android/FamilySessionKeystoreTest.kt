package org.chromantis.android

import android.content.Context
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.security.KeyStore
import java.util.UUID
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Exercises the platform provider, never the production session preferences or key alias. */
@RunWith(AndroidJUnit4::class)
class FamilySessionKeystoreTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val testName = "chromantis_test_${UUID.randomUUID()}"
    private val settings = context.getSharedPreferences(testName, Context.MODE_PRIVATE)
    private val origin = "https://nas.example"
    private val secret = "synthetic_session_".padEnd(43, 'x')

    private fun store() = familySessionStore(settings, testName)

    private fun keys() = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    @After
    fun removeOnlyTestData() {
        context.deleteSharedPreferences(testName)
        keys().deleteEntry(testName)
    }

    @Test
    fun savedSessionSurvivesRecreationWithoutExportableKeyOrPlaintext() {
        assertTrue(store().save(origin, secret))
        assertEquals(secret, store().restore(origin))
        assertFalse(settings.contains("session"))
        assertNotNull(settings.getString("session_encrypted", null))
        val xml = File(context.applicationInfo.dataDir, "shared_prefs/$testName.xml").readText()
        assertFalse(xml.contains(secret))
        assertNull(keys().getKey(testName, null).encoded)
    }

    @Test
    fun legacySessionMigratesAndKeepsUnrelatedPreferences() {
        assertTrue(
            settings
                .edit()
                .putString("session", secret)
                .putString("theme", "dark")
                .putString("resume_album", "synthetic/2024")
                .commit()
        )
        assertEquals(secret, store().restore(origin))
        assertFalse(settings.contains("session"))
        assertNotNull(settings.getString("session_encrypted", null))
        assertEquals("dark", settings.getString("theme", null))
        assertEquals("synthetic/2024", settings.getString("resume_album", null))
        assertEquals(secret, store().restore(origin))
    }

    @Test
    fun differentOriginRejectsSavedSessionAndClearsShortcut() {
        assertTrue(store().save(origin, secret))
        assertTrue(settings.edit().putString("resume_album", "synthetic/2024").commit())
        assertNull(store().restore("https://other.example"))
        assertFalse(settings.contains("session_encrypted"))
        assertFalse(settings.contains("resume_album"))
    }

    @Test
    fun missingPlatformKeyRequiresNewSessionAndAllowsRecovery() {
        assertTrue(store().save(origin, secret))
        assertTrue(settings.edit().putString("resume_album", "synthetic/2024").commit())
        keys().deleteEntry(testName)
        assertNull(store().restore(origin))
        assertFalse(settings.contains("session_encrypted"))
        assertFalse(settings.contains("session"))
        assertFalse(settings.contains("resume_album"))
        val replacement = "replacement_session_".padEnd(43, 'y')
        assertTrue(store().save(origin, replacement))
        assertEquals(replacement, store().restore(origin))
    }
}
