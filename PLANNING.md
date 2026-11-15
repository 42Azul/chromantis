# Chromantis Roadmap

This file tracks delivery status, upcoming MVPs, and the implementation direction of the project. Use it as the roadmap and progress ledger for Chromantis.

`README.md` explains how to run the current system. This document explains what is already shipped, what is ready next, and what is intentionally deferred.

## Status Legend

- `Done`: shipped and reflected in the current codebase
- `Ready Next`: next implementation target, scoped enough to build now
- `Planned Later`: intentionally deferred
- `Open Risks`: unresolved cross-cutting concerns

## Current State

Chromantis currently provides:

- source-agnostic, read-only archive indexing from either FTP or a local root
- deterministic path parsing and deterministic tagging
- SQLite persistence with migration-aware startup
- deterministic search over years, year ranges, titles, tags, and curated people aliases
- a Telegram bot with multi-image replies, persistent browse sessions, mixed-folder disclosure, guided onboarding, per-chat English/Spanish language preferences, plain-text query handling, and explicit `owner`/`admin`/`viewer` auth management
- a shared application/query service used by both Telegram and the local HTTP API, with an optional local model interpreter and a rule-based default
- a local HTTP API for search, indexed image delivery, persistent browsing, query interpretation, people curation, and role-based chat and invite administration
- guided people curation in Telegram and per-chat recent and pinned searches shared by Telegram and the API
- optional image enrichment with model provenance and opt-in search over captions, OCR, and object tags
- incremental indexing with stored sync summaries, a cron recipe, and bounded enrichment retries
- a browser interface for visual search, browsing, people, saved searches, and role-based administration
- browser-based album review with name-only tag suggestions, manual tags, curated people and limited viewer permissions
- local browser-only family sign-in with one-time codes and revocable SQLite sessions
- album aliases, notes, and title and date corrections shared by the browser and Telegram
- optional local thumbnails with a disk budget and an index freshness indicator
- opt-in JPEG capture dates with separate camera, album and file-time provenance

Not implemented yet:

- embeddings, EXIF extraction, or model-based reranking

Current architecture map:

- `source/` and `parsing/`: archive access and deterministic metadata extraction
- `db/`: SQLite schema, migrations, persistence, and audit storage
- `search/`: deterministic retrieval logic
- `app/`: shared product/query logic and rule-based request interpretation
- `api/`: local HTTP surface
- `bot/`: Telegram-specific interaction layer

## Shipped MVPs

### MVP 0 — Archive Foundation

**Status:** `Done`

**Goal:** Build a reliable archive index without changing the original photo source.

**Deliverables:**

- archive scanning from FTP and local roots
- read-only source access and root confinement
- deterministic path parsing and tag derivation
- SQLite indexing and full reindex flow
- scan progress logging and depth-limited traversal

**Acceptance:**

- indexing works from the configured source root
- no archive write operations are used
- scanner, parser, and source safety behavior are covered by tests

### MVP 1 — Search and Retrieval

**Status:** `Done`

**Goal:** Make folders and images retrievable through deterministic search and Telegram delivery.

**Deliverables:**

- folder and image search
- exact year and inclusive year-range queries
- curated people aliases and folder links
- deterministic reasons attached to results
- Telegram media replies, multi-image flows, session continuation, and mixed-folder disclosure

**Acceptance:**

- `/folders`, `/images`, `/random`, `/more`, and `/years` work against the SQLite index
- people aliases and year ranges affect retrieval correctly
- results explain why they matched

### MVP 2 — Product Service Layer

**Status:** `Done`

**Goal:** Move product logic out of Telegram handlers and make it reusable.

**Deliverables:**

- shared application/query service
- local read-only HTTP API
- invite-based auth and stored chat roles
- audit storage for auth and curation actions
- rule-based plain-text interpretation for Telegram

**Acceptance:**

- Telegram and API run on the same shared query layer
- invites can authorize new chats
- plain-language text is rewritten into deterministic search actions
- API behavior and legacy DB migration are covered by tests

### MVP 3 — Stability and Migration Safety

**Status:** `Done`

**Goal:** Keep local deployments stable while the schema evolves.

**Deliverables:**

- migration-safe startup for legacy SQLite databases
- schema regression tests for older local DBs
- explicit contributor guidance to preserve startup compatibility

**Acceptance:**

- `Repository.init_schema()` works on both fresh and legacy DB files
- schema changes include compatibility coverage

### MVP 4A — Explicit Telegram Auth and Admin Management

**Status:** `Done`

**Goal:** Make Telegram auth, roles, and small-deployment admin operations explicit instead of relying on implicit allowlist behavior.

**Deliverables:**

- explicit effective principal resolution for `owner`, `admin`, `viewer`, and unauthenticated chats
- static owner and static viewer compatibility through allowlists without implicit admin fallback
- Telegram invite management:
  - list active invites
  - revoke active invites
  - show invite expiry and usage
- Telegram chat management:
  - list effective authorized chats and auth mode
  - change dynamic chat role
  - revoke dynamic chat access
- expanded audit events for role changes, invite revocation, and actor-aware access revocation

**Acceptance:**

- role checks are consistent across Telegram commands
- role changes and invite revocations are auditable
- existing DBs still migrate without manual intervention

### MVP 4B — Local API Auth/Admin Parity

**Status:** `Done`

**Goal:** Expose the same explicit auth and admin operations through the local API so future clients do not depend on Telegram-only administration.

**Deliverables:**

- expose effective principal and chat-management operations through the local API
- expose invite listing, creation, and revocation through the local API
- keep API behavior aligned with Telegram role rules and audit behavior
- document the stable request and response shapes for a future UI

**Acceptance:**

- role checks are consistent between bot and API
- role changes and invite revocations are auditable
- existing DBs still migrate without manual intervention

### MVP 5 — Query API Maturation

**Status:** `Done`

**Goal:** Turn the local API into a stable query surface for future clients.

**Deliverables:**

- normalize API response envelopes and query parameter conventions
- add endpoints for session-aware continuation:
  - continue current scope
  - same folder
  - same year
  - related images
- add people detail and audited curation endpoints
- add auth/admin endpoints needed by a future UI
- add a plain-text interpretation endpoint on top of the existing rule interpreter
- deliver indexed photo bytes through the configured read-only source

**Acceptance:**

- every current Telegram retrieval flow has an equivalent API path
- archive access remains read-only
- response shapes are stable enough for a later UI client

### MVP 6A — Guided Telegram UX and Bilingual Onboarding

**Status:** `Done`

**Goal:** Make Telegram usable without relying on command memorization and support per-chat English/Spanish guidance.

**Deliverables:**

- per-chat language selection on first `/start`, stored in SQLite
- localized onboarding, help, settings, examples, and button labels for English and Spanish
- stronger guided home flow after `/start` and after login
- clearer browse entry points for years, people, random memory, and search help
- better empty-state and no-result suggestions
- lightweight clarification for low-information plain-text requests
- Spanish request framing support in the rule-based interpreter

**Acceptance:**

- a non-technical user can retrieve images without needing slash commands
- existing command flows still work
- conversation-state behavior stays covered by tests

### MVP 6B — Guided Curation and Saved Search UX

**Status:** `Done`

**Goal:** Finish the remaining non-technical UX work that was intentionally deferred from MVP 6A.

**Deliverables:**

- guided admin curation flows instead of only pipe-based syntax
- guided people management for admins:
  - add person
  - add alias
  - rename person
  - link folder
  - unlink folder
- replace current command-only people and alias management flows with button-driven, step-by-step Telegram UX
- recent searches per chat
- favorite or pinned searches per chat
- richer disambiguation for ambiguous plain-text requests

**Acceptance:**

- common admin curation tasks are possible without memorizing pipe syntax
- people and alias management no longer depend on `|`-based command syntax
- repeated retrieval flows can be resumed from recent or pinned searches
- conversation-state behavior stays covered by tests

### MVP 7 — Query Interpreter Abstraction

**Status:** `Done`

**Goal:** Prepare for richer natural-language handling without making paid APIs mandatory.

**Deliverables:**

- define an interpreter interface in `app/`
- keep the current rule-based interpreter as the default implementation
- add provider slots for:
  - a local small model
  - an external LLM provider later
- add confidence and clarification behavior
- keep retrieval deterministic after interpretation

**Acceptance:**

- interpreter providers are swappable without changing bot or API clients
- low-confidence requests ask for clarification instead of guessing
- default deployment remains local and low-cost

### MVP 8 — Image Enrichment Pipeline

**Status:** `Done`

**Goal:** Add optional image understanding on top of deterministic indexing.

**Deliverables:**

- captions
- OCR text
- object tags
- provenance by model and version
- optional enrichment signals in search

**Acceptance:**

- enrichment is stored separately from source facts and deterministic fields
- deterministic-only mode still works without enrichment

### MVP 9 — Sync and Operations

**Status:** `Done`

**Goal:** Improve long-running operation and maintenance.

**Deliverables:**

- incremental sync or change detection
- scheduled indexing
- operational summaries and health reporting
- optional reprocessing queues for enrichment

**Acceptance:**

- large archives no longer require only full rescans for routine updates
- operational state is visible without reading raw logs

### MVP 10 — Browser UI

**Status:** `Done`

**Goal:** Add a browser/admin interface on top of the same product layer.

**Deliverables:**

- visual search and browsing UI
- admin/configuration UI
- people and invite management UI
- search history and favorites UI

**Acceptance:**

- the UI reuses the existing API rather than reimplementing product logic
- Telegram remains a supported client, not a separate code path

### NAS Bootstrap

**Status:** `Done`

- Create or reuse a private `.env`, install compatible Python when needed, and index the archive from the NAS.
- Enroll the owner through a one-time Telegram challenge and generate a separate browser token.
- Start the API and bot together and document token rotation and the repeat-start command.

### MVP 11A — Family Album Tagging

**Status:** `Done`

- Review albums in the Spanish browser interface, choose people by name or alias, and add or remove album-level links.
- Accept or reject suggestions in a batch, correct individual suggestions, and add manual tags. The rules use only the indexed folder name and expose the evidence.
- Persist decisions in SQLite across rescans of the same path. Leave unsaved albums and unresolved suggestions pending.
- View up to three originals on demand. The remaining review flow works fully from the index, including with the archive offline.
- Give authorized viewers optional browser curation permission without granting administration.

**Acceptance:** Select Ana (or her alias), save and find the album by searching Ana. Reindex and verify that tags, decisions and the person link survive. Cover migration and restricted permissions with synthetic fixtures.

### MVP 11B — Local Family Web Sign-in

**Status:** `Done`

**Goal:** Let a family member curate from a mobile browser on the home network without registering through Telegram.

- The owner issues one-time codes and revokes sessions from the NAS CLI. Only hashes are stored in SQLite.
- Family members redeem a code in the local web app and can return to album review and search with the same browser. The session is scoped to album review, folder search and indexed previews.
- Existing Telegram and browser-token flows use the same indexing, search and curation logic.

**Acceptance:** A family member opens the browser, signs in once and can resume album review after a reload. The owner can revoke the session and the curator cannot access administration.

### MVP 11C — Album Context and Corrections

**Status:** `Done`

**Goal:** Find the same memory even when family members remember it by different names.

- Store aliases, short notes and optional title and date corrections separately from the index.
- Search by the original name, an alias or the corrected title. Search results explain alias and correction matches, and year navigation uses the corrected date.
- Edit and clear details in the existing browser review screen or through Telegram's `/album` command.

**Acceptance:** “Abuela's birthday” finds the same album as its original folder name. A full reindex preserves corrections and the source files stay unchanged.

### MVP 12 — Fast Browsing on the NAS

**Status:** `Done`

**Goal:** Make the archive usable from a phone without a burst of full-size downloads.

- Generate optional 480 px JPEG previews on demand and limit concurrent rendering, input size and cache size.
- Invalidate thumbnails when the indexed source fingerprint changes. Keep warmed previews available during a source outage.
- Use previews for web grids and fetch the authorized original only when the user opens a photo.
- Show the latest successful index date and source errors in the browser.

**Acceptance:** A gallery page loads small previews. Changing a source image invalidates its thumbnail. The original remains downloadable to authorized users.

### MVP 13A — Capture Dates and Provenance

**Status:** `Done`

- Extract JPEG `DateTimeOriginal` on demand in small, resumable batches, without pixel decoding.
- Show camera-reported dates, indexed or corrected album dates, and file modification times separately in the browser and local API.
- Keep GPS outside the capture-date extractor.

**Acceptance:** A photo with an inconsistent folder date and EXIF date exposes both values with sources. An unchanged JPEG does not need to be read again.

## Ready Next

### MVP 13B — Album Places and Timeline

**Status:** `Ready Next`

- Support manually curated locations and make embedded GPS indexing opt-in.
- Build a timeline and expose date- and place-based queries through the API and Telegram.

**Acceptance:** Find a curated album by place and year, see the source of its date, and verify that private GPS metadata stays outside the default index.

## Planned Later

### MVP 14 — Local Semantic Search

**Status:** `Planned Later`

- Add optional local image and text embeddings with model/version provenance and a bounded background queue.
- Combine lexical and semantic candidates while keeping year and person filters enforced across both.
- Build a synthetic evaluation set with realistic queries, and compare recall and latency against lexical search on the NAS.

**Acceptance:** A visual query such as “red bicycle by the sea” can retrieve an unlabeled fixture. Results identify why they matched, and the baseline search works with the model disabled.

### MVP 15 — Guided Recall

**Status:** `Planned Later`

- Let users refine by person, date, or album across turns on Telegram and the web.
- Ask one specific question when competing albums fit the same description.
- Let users build named memory collections from selected photos and albums.

**Acceptance:** “The beach trip with Ana” can be narrowed with “before 2020”, and the user can pin the resulting collection without moving the originals.

### MVP 16 — Private Family Sharing and Recovery

**Status:** `Planned Later`

- Add album-scoped, expiring grants independent of unrestricted archive access.
- Add backup and restore for the database and user curation, plus a documented recovery drill.
- Verify access checks for individual assets, previews, collections, and revoked grants.

**Acceptance:** A guest can open one shared album and its images. Revoking the grant removes access on the next request. A restore onto a fresh instance preserves collections and corrections.

## Open Risks

- SQLite migration compatibility must remain stable as schema grows.
- Auth semantics should become explicit without making small-family deployment heavy.
- Telegram UX complexity must not leak into `app/` or `search/`.
- Future AI interpretation should stay explainable and must not silently replace deterministic retrieval.
- Archive access must remain strictly read-only in both FTP and local modes.

## Maintenance Note

- When a milestone lands, move it from `Ready Next` to `Done`.
- Update the existing MVP entry instead of appending loose notes elsewhere.
- Use this file as the progress ledger when resuming work, proposing features, or deciding what is still missing.
- When a new client or subsystem is added, anchor it to the existing `app/` and `api/` direction instead of creating a parallel roadmap.
