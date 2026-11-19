package org.chromantis.android

import android.content.SharedPreferences
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.io.IOException
import java.security.KeyStore
import java.util.Base64
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Stores only an authenticated envelope; the NAS origin is authenticated with the session. */
internal class FamilySessionStore(
    private val read: (String) -> String?,
    private val write: (Map<String, String?>) -> Unit,
    private val key: () -> SecretKey,
) {
    fun restore(origin: String): String? {
        return try {
            val encrypted = read("session_encrypted")
            if (encrypted != null) {
                val fields = encrypted.split('.')
                require(fields.size == 3 && fields[0] == "1")
                val iv = Base64.getDecoder().decode(fields[1])
                require(iv.size == 12)
                val cipher = Cipher.getInstance("AES/GCM/NoPadding")
                cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, iv))
                cipher.updateAAD(origin.toByteArray(Charsets.UTF_8))
                val secret =
                    cipher.doFinal(Base64.getDecoder().decode(fields[2])).toString(Charsets.UTF_8)
                require(validSession.matches(secret))
                // Never fall back to a plaintext value alongside a damaged envelope.
                if (read("session") != null) write(mapOf("session" to null))
                secret
            } else {
                val legacy = read("session") ?: return null
                if (save(origin, legacy)) legacy else null
            }
        } catch (_: Exception) {
            clear()
            null
        }
    }

    fun save(origin: String, secret: String): Boolean =
        try {
            require(validSession.matches(secret))
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.ENCRYPT_MODE, key())
            cipher.updateAAD(origin.toByteArray(Charsets.UTF_8))
            val ciphertext = cipher.doFinal(secret.toByteArray(Charsets.UTF_8))
            require(cipher.iv.size == 12)
            val encoder = Base64.getEncoder()
            val envelope =
                "1.${encoder.encodeToString(cipher.iv)}.${encoder.encodeToString(ciphertext)}"
            write(mapOf("origin" to origin, "session_encrypted" to envelope, "session" to null))
            true
        } catch (_: Exception) {
            clear()
            false
        }

    fun clear() {
        runCatching {
            write(mapOf("session" to null, "session_encrypted" to null, "resume_album" to null))
        }
    }

    private companion object {
        val validSession = Regex("[A-Za-z0-9_-]{43}")
    }
}

internal fun familySessionStore(settings: SharedPreferences) =
    FamilySessionStore(
        read = { settings.getString(it, null) },
        write = { values ->
            val editor = settings.edit()
            values.forEach { (name, value) ->
                if (value == null) editor.remove(name) else editor.putString(name, value)
            }
            if (!editor.commit()) throw IOException("Could not persist family session.")
        },
        key = ::deviceSessionKey,
    )

private fun deviceSessionKey(): SecretKey {
    val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
    (store.getKey("chromantis_family_session_v1", null) as? SecretKey)?.let {
        return it
    }
    return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").run {
        init(
            KeyGenParameterSpec.Builder(
                    "chromantis_family_session_v1",
                    KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
                )
                .setKeySize(256)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build()
        )
        generateKey()
    }
}
