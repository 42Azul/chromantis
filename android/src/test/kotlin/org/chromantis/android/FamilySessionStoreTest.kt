package org.chromantis.android

import java.io.IOException
import javax.crypto.KeyGenerator
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class FamilySessionStoreTest {
    private val origin = "https://nas.example"
    private val secret = "x".repeat(43)
    private val values = mutableMapOf<String, String>()
    private val deviceKey = KeyGenerator.getInstance("AES").apply { init(256) }.generateKey()

    private fun store(key: () -> javax.crypto.SecretKey = { deviceKey }) =
        FamilySessionStore(
            read = { values[it] },
            write = { changes ->
                changes.forEach { (name, value) ->
                    if (value == null) values.remove(name) else values[name] = value
                }
            },
            key = key,
        )

    @Test
    fun encryptedSessionSurvivesRestartAndUsesFreshNonces() {
        assertTrue(store().save(origin, secret))
        val first = values.getValue("session_encrypted")
        assertFalse(first.contains(secret))
        assertNull(values["session"])
        assertEquals(secret, store().restore(origin))
        assertTrue(store().save(origin, secret))
        assertNotEquals(first, values["session_encrypted"])
    }

    @Test
    fun legacySessionIsMigratedWithoutLosingNonSecretPreferences() {
        values["session"] = secret
        values["appearance"] = "DARK"
        values["resume_album"] = "synthetic-album"
        assertEquals(secret, store().restore(origin))
        assertNull(values["session"])
        assertNotNull(values["session_encrypted"])
        assertEquals("DARK", values["appearance"])
        assertEquals("synthetic-album", values["resume_album"])
    }

    @Test
    fun tamperedEnvelopeCannotFallBackToLegacySession() {
        store().save(origin, secret)
        val fields = values.getValue("session_encrypted").split('.').toMutableList()
        val bytes = java.util.Base64.getDecoder().decode(fields[2])
        bytes[0] = (bytes[0].toInt() xor 1).toByte()
        fields[2] = java.util.Base64.getEncoder().encodeToString(bytes)
        values["session_encrypted"] = fields.joinToString(".")
        values["session"] = secret
        values["resume_album"] = "synthetic-album"
        assertNull(store().restore(origin))
        assertNull(values["session"])
        assertNull(values["session_encrypted"])
        assertNull(values["resume_album"])
    }

    @Test
    fun wrongOriginOrLostDeviceKeyCannotRestoreTheSession() {
        store().save(origin, secret)
        assertNull(store().restore("https://other-nas.example"))
        store().save(origin, secret)
        assertNull(store { throw IOException("Synthetic key failure") }.restore(origin))
        assertNull(values["session_encrypted"])
        store().save(origin, secret)
        val replacementKey = KeyGenerator.getInstance("AES").apply { init(256) }.generateKey()
        assertNull(store { replacementKey }.restore(origin))
    }

    @Test
    fun malformedOrUnknownEnvelopeClearsBothCredentialFormats() {
        for (envelope in listOf("", "2.ignored.ignored", "1.invalid.invalid", "1.YQ==.YQ==")) {
            values["session_encrypted"] = envelope
            values["session"] = secret
            assertNull(store().restore(origin))
            assertNull(values["session"])
            assertNull(values["session_encrypted"])
        }
    }

    @Test
    fun failedMigrationNeverUsesPlaintextFallback() {
        values["session"] = secret
        assertNull(store { throw IOException("Synthetic key failure") }.restore(origin))
        assertNull(values["session"])
        assertFalse(store { throw IOException("Synthetic key failure") }.save(origin, secret))
        assertNull(values["session"])
    }

    @Test
    fun failedWriteDoesNotReportAPersistedSession() {
        val failing =
            FamilySessionStore(
                read = { null },
                write = { throw IOException("Synthetic write failure") },
                key = { deviceKey },
            )
        assertFalse(failing.save(origin, secret))
    }

    @Test
    fun signOutRemovesSessionAndAlbumResumeButKeepsAppearance() {
        store().save(origin, secret)
        values["resume_album"] = "synthetic-album"
        values["appearance"] = "DARK"
        store().clear()
        assertNull(store().restore(origin))
        assertNull(values["resume_album"])
        assertEquals("DARK", values["appearance"])
    }
}
