---
title: Android preview
description: Build the native Kotlin and Compose APK and try it over private HTTPS.
---

Chromantis for Android is a preview for Android 8.0 and later. It connects to your own Chromantis server over private HTTPS and needs a [family access code](../start/private-access.md#invite-a-family-member-without-telegram).

**APK availability:** Build the APK from source using the instructions below. There is no public prebuilt APK at this stage.

## What you can do

**Folders** (*Carpetas*) lists years and albums, searches indexed albums, and opens a paged gallery. It requests thumbnails for visible tiles when the server has them enabled and loads an original after a tap. Family sign-in uses the existing one-time code and revocable session. Open **Tag albums** (*Etiquetar álbumes*) for the pending queue or **Tag this album** (*Etiquetar este álbum*) in a gallery to make a correction. Search for a person by name or alias, select or clear the link, add a person, or decide on tags suggested from folder names. Use **View up to three photos** to request previews. Skipping leaves the album pending.

The full flow on a current physical phone is pending. The native client in `android/` uses Kotlin and Jetpack Compose with Material 3. Archive access, permissions, indexing, and curation remain in the shared service.

## Build and install

Build on a development computer with JDK 17 or 21, Gradle 8.13, Android SDK Platform 36 and Build Tools 36.0.0. Set `ANDROID_HOME` to the SDK directory. From the repository root:

```bash
gradle -p android spotlessCheck testDebugUnitTest assembleDebug lintDebug
adb install -r android/build/outputs/apk/debug/Chromantis-debug.apk
```

The debug APK is signed by the local debug key. Open it with a private HTTPS origin reachable by the device and a family code. If HTTPS is terminated by a local reverse proxy, preserve the original `Host` header for family session writes. Plain HTTP is disabled. The debug build also trusts certificates installed by the Android user for local fixtures. Release builds use the platform trust store. Run `gradle -p android spotlessApply` to format Kotlin with the pinned ktfmt version.

## Sign a private release

For a private release APK, create a signing key once and keep it outside the repository. Copy `android/keystore.properties.example` to `android/keystore.properties`, use the absolute path to that key, and replace every placeholder. The local properties file, `.jks` files, and `.keystore` files are ignored by Git. Build and verify the signed artifact:

```bash
keytool -genkeypair -v -keystore /private/path/to/chromantis-release.jks \
  -alias chromantis -keyalg RSA -keysize 3072 -validity 10000
gradle -p android spotlessCheck testDebugUnitTest assembleRelease lintRelease
apksigner verify --verbose android/build/outputs/apk/release/Chromantis-release.apk
```

Back up the keystore and its passwords privately. Android updates must be signed with the same key. For CI or another trusted build host, leave `keystore.properties` absent and provide `CHROMANTIS_KEYSTORE_PATH`, `CHROMANTIS_KEYSTORE_PASSWORD`, `CHROMANTIS_KEY_ALIAS`, and `CHROMANTIS_KEY_PASSWORD` instead. A release task fails early when no complete signing configuration is available.

## Test with a synthetic archive

For a local emulator smoke test, install the existing thumbnails extra for Pillow. Generate a temporary certificate for the emulator's host alias and run the fixture without the NAS:

```bash
fixture_dir=$(mktemp -d)
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=Chromantis-Fixture \
  -addext 'subjectAltName=IP:10.0.2.2' \
  -keyout "$fixture_dir/key.pem" -out "$fixture_dir/cert.pem"
PYTHONPATH=src python tests/android_fixture.py \
  --cert "$fixture_dir/cert.pem" --key "$fixture_dir/key.pem"
```

Install the temporary certificate as a trusted user CA on the disposable emulator. Set the address to `https://10.0.2.2:8443` and use the fixture's printed one-time code. Open 2024, browse the second gallery page, open a photo, go back, and relaunch the app to check the retained session.

From **Folders**, open **Tag albums**, filter people with `Anita`, select Ana, and save. Return to **Folders** and search `Ana` to find the album. Open its gallery and use **Tag this album** to remove the link or check which suggestion decisions were saved. Repeat with `--index-only` on a fresh fixture to check that navigation, filenames, and album editing still work with the synthetic archive disconnected. Press Ctrl+C in the fixture terminal to remove its temporary SQLite index and synthetic photos.
