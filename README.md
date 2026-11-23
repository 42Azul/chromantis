# Chromantis

Turn an existing photo archive into a searchable family library. Chromantis indexes local or FTP folders in SQLite, keeps originals read-only, and offers a browser, a Telegram bot, and an Android preview.

**[Documentation](https://42azul.github.io/chromantis/)** · [Español](https://42azul.github.io/chromantis/es/) · [Installation](docs/src/content/docs/start/install.md) · [Android APK](docs/src/content/docs/use/android.md) · [Family guide](docs/src/content/docs/use/family.md) · [Roadmap](PLANNING.md)

## What you can do

- Browse albums by year, title, place, tags, and curated people.
- Review albums with family members, correct folder-name suggestions, and open photo previews on demand.
- Sign in without Telegram, keep private collections, or share one album with an expiring link.
- Run on a NAS with Python and SQLite. OCR and other model experiments are optional.

## Start here

From a checkout on a NAS with a local archive and a Telegram bot token:

```bash
bash scripts/setup_nas.sh
```

For a browser-only installation, FTP, or a synthetic first run, follow the [installation guide](docs/src/content/docs/start/install.md). See also [Telegram](docs/src/content/docs/use/telegram.md), [Android](docs/src/content/docs/use/android.md), [maintenance](docs/src/content/docs/operate/maintenance.md), the [local API](docs/src/content/docs/reference/api.md), and [optional MCP folder curation](docs/src/content/docs/reference/mcp.md).

## Development

```bash
python -m pip install '.[telegram,thumbnails]'
python -m unittest discover -s tests -v
node tests/test_album_review_ui.cjs
node tests/test_confirmed_photo_ui.cjs
node tests/test_photo_review_ui.cjs
gradle -p android spotlessCheck testDebugUnitTest assembleDebug assembleDebugAndroidTest lintDebug
gradle -p android connectedDebugAndroidTest # requires a running emulator or test device
npm --prefix docs ci
npm --prefix docs run dev
npm --prefix docs run check
```

To exercise the optional MCP stdio transport with Python 3.11 or newer:

```bash
python -m pip install '.[mcp]'
python -m unittest tests.test_folder_curation_mcp -v
```

See [interface direction and design references](DESIGN.md), and [contributing and publishing](docs/src/content/docs/reference/contributing.md) for requirements and the static-site workflow.


### Android CI signing

The [Android workflow](.github/workflows/android.yml) publishes the verified test APK only from
`main`. Generate a dedicated key once and keep a private backup of the keystore and its password.
Run the following from a trusted machine with an authenticated GitHub CLI and Android Build Tools
on PATH. Enter the same password for the PKCS#12 store and key.

```bash
umask 077
keytool -genkeypair -storetype PKCS12 -keystore chromantis-test.keystore \
  -alias chromantis-test -keyalg RSA -keysize 3072 -validity 10000 \
  -dname 'CN=Chromantis Android Test'
base64 -w0 chromantis-test.keystore | gh secret set ANDROID_TEST_KEYSTORE_BASE64
gh secret set ANDROID_TEST_KEYSTORE_PASSWORD
keytool -list -v -keystore chromantis-test.keystore -alias chromantis-test
gh variable set ANDROID_TEST_CERT_SHA256 --body '<lowercase SHA-256 fingerprint without colons>'
gh workflow run android.yml --ref main
```

Copy the certificate fingerprint from `keytool`. CI rejects a mismatched fingerprint before
uploading. Keep using the same keystore for updates. The signing key is dedicated to testing.
