---
title: Install Chromantis
description: Try the sample archive, set up a NAS, or configure a local or FTP source manually.
---

You need Python 3.10 or later, a photo archive, and a writable location for the SQLite index. Chromantis reads photos from the archive and stores metadata and edits separately.

## Try it with sample folders

With Git and Python installed, clone the repository and start the browser locally:

```bash
git clone https://github.com/42Azul/chromantis.git
cd chromantis
export SOURCE_TYPE=local
export SOURCE_ROOT=tests/fixtures/ftp_tree/server_root/photos/archive
export SQLITE_PATH=./data/chromantis-demo.db
python3 scripts/reindex_source.py
python3 scripts/run_api.py
```

Open [http://127.0.0.1:8787/](http://127.0.0.1:8787/) and search for `city 2021`. The fixtures contain filenames for testing the index. Use your own archive to try photo previews. Press Ctrl+C to stop the API. This unauthenticated example is for loopback only.

## Set up a NAS with Telegram

1. Clone the repository on the NAS and enter its directory.
2. Run `bash scripts/setup_nas.sh`.
3. Enter the local directory that contains the year folders, then enter the Telegram bot token at the hidden prompt.
4. Open the printed Telegram link to enroll your chat as owner. Send `/start`, then try `/years`.

The setup script creates a virtual environment, writes a private `.env` with a separate browser token, indexes the archive incrementally, and starts the API and bot in your terminal. On an older NAS it can use `uv` to install Python 3.12 for your account. Set `CHROMANTIS_OWNER_CHAT_ID` before setup if you already know the chat ID.

| To | Run from the checkout |
| --- | --- |
| Start the configured services | `bash scripts/setup_nas.sh --start-only` |
| Configure and index, then exit | `bash scripts/setup_nas.sh --setup-only` |
| Replace the bot token | `bash scripts/setup_nas.sh --rotate-token` |

Open the browser from your computer with an [SSH tunnel](./private-access.md#open-the-nas-from-your-computer).

## Set up the browser manually

Use this path for a browser-only setup, an FTP source, or an existing Python environment.

```bash
git clone https://github.com/42Azul/chromantis.git
cd chromantis
python3 -m venv .venv
cp .env.example .env
chmod 600 .env
```

Set the source and database in `.env`. For a local archive:

```dotenv
SOURCE_TYPE=local
SOURCE_ROOT=/mnt/photos
SQLITE_PATH=./data/chromantis.db
```

For FTP, use `SOURCE_TYPE=ftp`, an absolute FTP path in `SOURCE_ROOT`, and the `FTP_HOST`, `FTP_PORT`, `FTP_USER`, and `FTP_PASSWORD` settings. Use a read-only account. The scanner expects `year/album/photo` under either root and skips deeper directories.

Keep `API_BIND_HOST=127.0.0.1`. To enable browser authentication, generate a token with `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'` and put it in `API_TOKEN`. Use this token for read-only access. For an owner login, configure an individual chat token instead as described in [Private access](./private-access.md#configure-an-owner-token).

```bash
.venv/bin/python scripts/init_db.py
.venv/bin/python scripts/reindex_source.py --progress-every 500
.venv/bin/python scripts/run_api.py
```

Open the browser and check the year list. For Telegram too, install `'.[telegram]'` with `.venv/bin/python -m pip install`, fill in `TELEGRAM_TOKEN`, and run `.venv/bin/python scripts/run_bot.py` in another terminal.

## If the first run stalls

| Symptom | Check |
| --- | --- |
| Zero photos indexed | Point the root at the directory containing year folders. Try a scan with `--verbose --show-skipped` on a small archive. |
| Browser unreachable | Open it on the host running the API, or forward the loopback port through SSH. |
| Sign-in fails | Check the token or issue a fresh one-time family code. Restart the API after editing `.env`. |
| Original or preview unavailable | Check that the source is mounted or the FTP server is reachable. The indexed list and album edits still work from SQLite. |
