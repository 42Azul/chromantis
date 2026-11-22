---
title: Configuration
description: Configure the source, SQLite, API, optional clients, and bounded enrichment.
---

Start with [the example environment file](https://github.com/42Azul/chromantis/blob/main/.env.example). Keep your local `.env` private. Environment variables take precedence over the file. Restart the API and bot after changing their configuration.

| Setting | Values and purpose |
| --- | --- |
| `SOURCE_TYPE` | `local` or `ftp`. |
| `SOURCE_ROOT` | Directory containing year folders. Use a local absolute or repository-relative path, or an absolute FTP path. |
| `FTP_HOST`, `FTP_PORT`, `FTP_USER`, `FTP_PASSWORD` | Read-only FTP connection settings when using an FTP source. |
| `SQLITE_PATH` | Writable index path outside the archive. |
| `API_BIND_HOST`, `API_PORT` | Defaults to `127.0.0.1:8787`. |
| `API_TRUST_LOCAL_PROXY` | Defaults to `false`. Enable only when an HTTPS proxy on the same machine overwrites `X-Forwarded-Proto`. |
| `API_TOKEN`, `API_CHAT_TOKENS` | Optional shared read-only token and per-chat tokens as a JSON object. |
| `API_CURATOR_CHAT_IDS` | Comma-separated authorized viewer IDs that can curate albums. |
| `TELEGRAM_TOKEN`, `TELEGRAM_ACCESS_CODE` | Bot token and optional fixed viewer access code. |
| `TELEGRAM_CHAT_ALLOWLIST`, `TELEGRAM_ADMIN_CHAT_ALLOWLIST` | Comma-separated static viewer and owner IDs. |
| `THUMBNAIL_CACHE_MIB` | JPEG preview cache budget. Default `0` disables it. |
| `QUERY_INTERPRETER_COMMAND`, `QUERY_INTERPRETER_TIMEOUT` | Optional local model adapter command and timeout in seconds (default 10). |
| `ENRICHMENT_SEARCH` | Set to `true` to match saved OCR, captions, and object tags. Default `false`. |
| `LOG_LEVEL` | Defaults to `INFO`. Use `DEBUG` for more scan and query diagnostics. |

See [private access](../start/private-access.md) for role setup and family sessions, and [local experiments](../reference/experiments.md) for model adapters.

## Missing photo previews

The quick NAS installer installs the Telegram extra. It does not install the optional image renderer or turn on previews. First check the running server's authenticated `GET /api/v1/archive-status`: `item.thumbnails` must be `true`. A folder placeholder alone does not establish a client fault.

To enable previews deliberately on the NAS, install `'.[thumbnails]'` in the same Python environment that runs the API, set `THUMBNAIL_CACHE_MIB=64` in its private `.env`, and restart the API. Keep `SQLITE_PATH` outside the read-only archive: the preview cache is created beside SQLite. Environment variables override `.env`. If the status is still false, check the API log for a missing renderer or an unsafe cache location.

With an authorized local client, request `/api/v1/thumbnail?path=<indexed-photo-path>` for one small indexed JPEG. `404` can mean disabled previews, an unindexed path or a missing source file; `422` means an unsupported or oversized image or an index/source mismatch; `502` means the source could not be reached. Test a second image if only one fails. Keep credentials, paths and response images out of shared reports. This check reads only the explicitly selected photo; it does not start a scan.

Android and browser gallery previews reuse a bounded 4 MiB memory cache for the current client session. Image listings supply an opaque `identity`; reindexing a replaced photo changes it and prevents reuse of the earlier preview. Old servers that omit it are still supported, with a fresh preview request instead of caching. Signing out, signing in again or receiving an unauthorized response clears the cache. The browser also caps it at 64 entries, and stores no preview in persistent browser storage. The protected listing request still runs when reopening a gallery; a revoked session cannot use cached thumbnails to reopen that gallery. Revocation cannot retract pixels already displayed or explicitly downloaded.
