---
title: Index, previews, and backups
description: Update the catalogue, control thumbnail costs, and recover SQLite safely.
---

## Pick up new folders

After adding photos to the archive, run from the checkout:

```bash
.venv/bin/python scripts/reindex_source.py --incremental --progress-every 500
```

Incremental mode lists the configured subtree, applies changes, and removes missing items only after a successful listing. A late scan cannot overwrite a newer completed index. Run without `--incremental` after changing parsing rules to refresh derived metadata.

The browser shows the latest successful index. `GET /api/v1/sync/runs?limit=10` reports started and finished runs, counts, and errors. For a daily scan at 03:20 in the NAS timezone, adapt the checkout and log paths in this cron entry:

```text
20 3 * * * cd /path/to/chromantis && .venv/bin/python scripts/reindex_source.py --incremental >> /path/to/chromantis-sync.log 2>&1
```

## Load small previews on demand

Install the optional Pillow extra in the same environment as the API:

```bash
.venv/bin/python -m pip install '.[thumbnails]'
```

Set `THUMBNAIL_CACHE_MIB=64` in `.env` and restart the API. The cache sits beside SQLite and stores up to 2,048 JPEG previews within the configured budget. It generates previews up to 480 px on demand and evicts the oldest entries first. Generating a preview requires an original of at most 32 MiB and 30 megapixels.

Cached previews can work while the source is offline. Changed sizes or modification times detected by indexing invalidate the corresponding preview. Set the budget to `0` to turn previews off.

## Read camera capture dates

With the same Pillow extra installed, process a small batch of indexed JPEGs:

```bash
.venv/bin/python scripts/index_capture_dates.py --limit 25 --album "2024/2024-08-04_beach"
```

Omit `--album` for the next batch across the index. The reader inspects up to 512 KiB per JPEG, stores the valid camera-reported day, and skips unchanged files on later runs. It reads no GPS directory and decodes no pixels. Read failures remain eligible for retry.

## Back up SQLite

```bash
mkdir -p backups
.venv/bin/python scripts/database_backup.py create backups/chromantis.sqlite
.venv/bin/python scripts/database_backup.py verify backups/chromantis.sqlite
```

The online backup includes committed WAL changes and prints the size and SHA-256 digest. The backup contains private index and curation data, including access records. Keep a private copy outside the NAS. Back up your original photos and local configuration separately.

## Restore to a new file

```bash
.venv/bin/python scripts/database_backup.py \
  --database data/restored-chromantis.db restore backups/chromantis.sqlite
```

Restore applies current schema migrations and refuses to overwrite an existing database. Stop the API and bot before switching `SQLITE_PATH`, keep the old database, and restart against the restored file. Check a corrected album and a private collection. Reindex if the archive location or contents have changed. Backup, verification, and restore work without the photo source.
