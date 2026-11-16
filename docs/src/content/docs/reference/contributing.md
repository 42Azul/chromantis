---
title: Development and publishing
description: Run project tests, edit Markdown, and publish the portable static documentation.
---

## Run tests

Use Python 3.10+ and synthetic archives for development:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install '.[telegram,thumbnails]'
.venv/bin/python -m unittest discover -s tests -v
```

The Python service lives in `src/chromantis`. Archive adapters and parsing feed the SQLite index. Search and curation live in the shared application layer, with Telegram and HTTP as clients. The Android client uses Kotlin and Jetpack Compose. See [Android build and smoke tests](../use/android.md).

Read the [contributor guidelines](https://github.com/42Azul/chromantis/blob/main/AGENTS.md) and the [roadmap](https://github.com/42Azul/chromantis/blob/main/PLANNING.md). Keep real archive data, chat tokens, and signing keys outside Git.

## Edit the documentation

Create or edit English Markdown under `docs/src/content/docs/`. Give each guide a title and description, and add new guides to the sidebar in `docs/astro.config.mjs`. Link to other Markdown files using relative paths. Astro converts them to site routes, so the same links work on GitHub and on the published site.

From the repository root, use Node.js 24.22+:

```bash
npm --prefix docs ci
npm --prefix docs run dev
npm --prefix docs run check
```

The check builds the site, creates the local search index, and checks internal links and anchors. Open the terminal's preview URL under `/chromantis/`.

## Publish on GitHub Pages

In the repository, choose **Settings → Pages → Build and deployment → Source → GitHub Actions**. Run **Documentation** from the **Actions** tab for the initial deployment. Changes under `docs/` on `main` trigger later builds. The workflow uploads only the built static documentation.

## Move to another static host

```bash
DOCS_SITE=https://docs.example.org DOCS_BASE=/ npm --prefix docs run check
```

Serve `docs/dist/` from the chosen host. Use `DOCS_BASE=/some-path` for a subdirectory. This build needs no server adapter, databases, or account connection. Astro Starlight builds the existing Markdown into static HTML and a local search index.
