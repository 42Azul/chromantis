# Chromantis

Turn an existing photo archive into a searchable family library. Chromantis indexes local or FTP folders in SQLite, keeps originals read-only, and offers a browser, a Telegram bot, and an Android preview.

**[Documentation](https://42azul.github.io/chromantis/)** · [Español](https://42azul.github.io/chromantis/es/) · [Installation](docs/src/content/docs/start/install.md) · [Family guide](docs/src/content/docs/use/family.md) · [Roadmap](PLANNING.md)

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

For a browser-only installation, FTP, or a synthetic first run, follow the [installation guide](docs/src/content/docs/start/install.md). See also [Telegram](docs/src/content/docs/use/telegram.md), [Android](docs/src/content/docs/use/android.md), [maintenance](docs/src/content/docs/operate/maintenance.md), and the [local API](docs/src/content/docs/reference/api.md).

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

See [contributing and publishing](docs/src/content/docs/reference/contributing.md) for requirements and the static-site workflow.
