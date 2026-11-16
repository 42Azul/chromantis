---
title: Android preview
description: Build the native Kotlin and Compose APK and try it over private HTTPS.
---

Chromantis for Android is a preview for Android 8.0 and later. It connects to your own Chromantis server over private HTTPS and needs a [family access code](../start/private-access.md#invite-a-family-member-without-telegram).

**APK availability:** Build the APK from source using the instructions below. There is no public prebuilt APK at this stage.

## What you can do

- **Folders** (*Carpetas*) lists years and albums and opens a paged gallery. Visible tiles use thumbnails when enabled on the server. Tap a tile to open the original.
- **Organize** (*Clasificar*) shows one album card at a time. Swipe right to accept the visible tag or left to leave the album pending. Both actions have buttons. Open **People, photos and tags** (*Personas, fotos y etiquetas*) to review people by name or alias, see a few photos on demand, or edit tag decisions. Open **Tag this album** (*Etiquetar este álbum*) from a gallery to correct a reviewed album.
- **Search** (*Buscar*) starts with album keywords or a person's name. Send a follow-up such as `antes de 2020` or `con Ana` to narrow the current results. If several albums match a requested name, choose one. The follow-up uses the existing local search rules.

Open **Settings** (*Ajustes*) to choose light, dark, or the Android system appearance. The choice is stored on the device.

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

Back up the keystore and its passwords privately. Android updates must be signed with the same key. For CI or another trusted build host, leave `keystore.properties` absent and provide `CHROMANTIS_KEYSTORE_PATH`, `CHROMANTIS_KEYSTORE_PASSWORD`, `CHROMANTIS_KEY_ALIAS`, and `CHROMANTIS_KEY_PASSWORD` instead. If Gradle cannot find `assembleRelease`, check that all four signing values are set. Without them, the release variant is disabled and the general `assemble` command builds only the debug APK.

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

Install the temporary certificate as a trusted user CA on the disposable emulator. Set the address to `https://10.0.2.2:8443` and use the fixture's printed one-time code. Open 2024, browse the second gallery page, open a photo, and rotate the device. Check that the same photo remains open and that going back returns to the second page. Relaunch the app to check the retained session.

From **Organize**, swipe left on the first card, then use **Start again** (*Volver al principio*) at the end of the queue to revisit it. Use **People, photos and tags**, filter people with `Anita`, select Ana, and save. Open **Search**, search `Ana` and refine with `solo 2024` to find the album.

On a fresh fixture with `--index-only`, swipe right on a suggested tag. The app shows the next suggestion for that album, or advances when all suggestions are decided. Open the tagged album from **Folders** and check the decision in **Tag this album**. Try the buttons and the swipes with the synthetic archive disconnected. Press Ctrl+C in the fixture terminal to remove its temporary SQLite index and photos.
