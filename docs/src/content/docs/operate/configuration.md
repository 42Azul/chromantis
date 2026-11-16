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
| `API_TOKEN`, `API_CHAT_TOKENS` | Optional shared read-only token and per-chat tokens as a JSON object. |
| `API_CURATOR_CHAT_IDS` | Comma-separated authorized viewer IDs that can curate albums. |
| `TELEGRAM_TOKEN`, `TELEGRAM_ACCESS_CODE` | Bot token and optional fixed viewer access code. |
| `TELEGRAM_CHAT_ALLOWLIST`, `TELEGRAM_ADMIN_CHAT_ALLOWLIST` | Comma-separated static viewer and owner IDs. |
| `THUMBNAIL_CACHE_MIB` | JPEG preview cache budget. Default `0` disables it. |
| `QUERY_INTERPRETER_COMMAND`, `QUERY_INTERPRETER_TIMEOUT` | Optional local model adapter command and timeout in seconds (default 10). |
| `ENRICHMENT_SEARCH` | Set to `true` to match saved OCR, captions, and object tags. Default `false`. |
| `LOG_LEVEL` | Defaults to `INFO`. Use `DEBUG` for more scan and query diagnostics. |

See [private access](../start/private-access.md) for role setup and family sessions, and [local experiments](../reference/experiments.md) for model adapters.
