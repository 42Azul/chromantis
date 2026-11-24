# Chromantis Roadmap

This file tracks delivery status, upcoming MVPs, and the implementation direction of the project. Use it as the roadmap and progress ledger for Chromantis.

`README.md` is the project index. The [documentation sources](docs/src/content/docs/) cover installation, usage, maintenance, and development. This document explains what is already shipped, what is ready next, and what is intentionally deferred.

## Status Legend

- `Done`: shipped and reflected in the current codebase
- `In Progress`: implemented in part, with explicit remaining delivery or validation work
- `Ready Next`: next implementation target, scoped enough to build now
- `Planned Later`: intentionally deferred
- `Open Risks`: unresolved cross-cutting concerns

## Latest Requests and Delivery Order

Reviewed against `main` and the family product requests on 2026-11-22. Keep the existing milestones below as the delivery ledger; this table makes their priority and remaining work explicit.

| Request | Current delivery | Next concrete outcome |
| --- | --- | --- |
| Phone test: absent previews, saving/sharing, missing `2003(2)` and date formats | Reported in the 2026-11-22 roadmap update; not yet verified as fixed | Follow the four phone-test tasks below in their stated order, across Android and browser |
| A friendly, visual app with coherent icons and light/dark appearance | Android library, album review, classification, search and sign-in have reviewed synthetic captures; the browser has appearance settings | Resolve the phone preview/export reports first, using MVP 20A's design criteria; then redesign the family web review and search surfaces |
| Classify as well as browse; optional swipe review | Album suggestion cards and per-photo review with explicit buttons and undo exist | Compare batch selection and photo review on the same synthetic album; test cancelled gestures and correction before extending the pattern |
| Strong authentication, free by default, little maintenance | Local one-time invitations, revocable limited sessions, HTTPS checks and Android Keystore persistence exist | MVP 20B reviews the complete trust boundary and recovery flow; an optional passkey prototype follows only with a stable trusted HTTPS origin |
| A useful APK, not just screenshots | CI builds and verifies an installable debug APK and checksum; launcher recreation and fresh launch are tested | Finish the combined person/tag interaction test; keep physical-phone, private-LAN and device-key checks as an explicit release gate |
| Short English README and portable bilingual documentation | Static Astro/Starlight documentation and English/Spanish guides are shipped | Update both languages and synthetic examples in the same feature change; keep installation, Android and browser guides easy to reach |
| People, index tools, chat and later local models | MVP 19C and the rules-first portion of 19D are partly implemented | Continue their scoped work after the family UX/auth increments; measure optional model trials before adopting any NAS workload |
| Operator-reviewed MCP curation and places/map | The local stdio curation trial is shipped for synthetic albums; curated place labels are already searchable | Evaluate hosted proposals only with approved data, and build the private place list before choosing a map provider; keep these behind the phone-test follow-up |

**Execution order:** the phone-test follow-up below takes precedence: previews, save/share, missing branch/date parsing, then the physical-phone checklist. Preserve the in-flight MVP 19B test work, but do not let screenshot-only work displace reported phone failures. Apply MVP 20A's design and MVP 20B's security criteria while delivering those fixes; broader web redesign and passkeys follow afterward. Native owner tools, local model comparison, face processing and remote MCP remain later work. A physical-device release gate does not block runnable synthetic service/browser improvements.

### Android browsing, search, and curation

- Keep **Folders** grounded in the archive hierarchy. Preserve the active breadcrumb, page and
  scroll position on return. Evaluate folder-only name filtering and explicit name/date ordering
  over the complete folder listing, including paged results.
- Keep **Search** for retrieval by album, confirmed person or tag, with visible filters, clear
  result types and a return path that keeps the query. A gallery opened from Search can be viewed,
  saved and shared, without surfacing tagging or review actions.
- Keep album and photo tagging under **Organize** and explicit actions from **Folders**. Add a
  direct album picker to Organize so existing albums can be curated without entering Search.
  Validate both a single-photo edit and batch selection with undo on a synthetic phone-sized view.

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
- direct photo browsing from Telegram person cards and home or command shortcuts to both search histories
- optional image enrichment with model provenance and opt-in search over captions, OCR, and object tags
- incremental indexing with stored sync summaries, a cron recipe, and bounded enrichment retries
- a browser interface for visual search, browsing, people, saved searches, and role-based administration
- browser-based album review with name-only tag suggestions, manual tags, curated people and limited viewer permissions
- batch acceptance and rejection of repeated name-based album suggestions without photo reads
- the batch API also accepts a replacement tag per album in the same transaction. The synthetic regression covers mixed decisions with the archive offline and verifies they survive a full reindex. The browser batch controls still offer acceptance and rejection.
- local browser-only family sign-in with one-time codes and revocable SQLite sessions
- album aliases, notes, and title and date corrections shared by the browser and Telegram
- optional local thumbnails with a disk budget and an index freshness indicator
- opt-in JPEG capture dates with separate camera, album and file-time provenance
- manually curated album places and a dated timeline shared by the browser, API and Telegram
- revocable, expiring browser links that grant read-only access to one album
- consistent, locally verifiable SQLite backup and fresh-path recovery
- a transport-neutral read-only MCP tool trial scoped by a revocable one-album grant
- optional OpenCode MCP folder curation over stdio, with live whole-library or selected-album browsing and opt-in SQLite edits

Not implemented yet:

- production semantic embeddings or model-based reranking (MVP 14 remains an optional experiment)
- automatic face identification (manual person links are implemented)

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
- the Telegram adapter dispatches actual people and history button updates in integration tests
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

- Review albums in the Spanish browser interface, choose people by name or alias, and add or remove album-level links. When a family member opens an album from search or the timeline, return to the same filtered results after editing.
- Explain image matches from those links as album-level evidence, never as per-photo identification.
- Accept or reject suggestions in a batch, correct individual suggestions, and add manual tags. The rules use only the indexed folder name and expose the evidence.
- Persist decisions in SQLite across rescans of the same path. Leave unsaved albums and unresolved suggestions pending.
- Open the album gallery on demand and browse one small page at a time. The gallery lists indexed filenames with the archive offline, and the remaining review flow works fully from the index.
- Give authorized viewers optional browser curation permission without granting administration.

**Acceptance:** Select Ana (or her alias), save and find the album by searching Ana. Reindex and verify that tags, decisions and the person link survive. Cover migration and restricted permissions with synthetic fixtures.

### MVP 11B — Local Family Web Sign-in

**Status:** `Done`

**Goal:** Let a family member curate from a mobile browser on the home network without registering through Telegram.

- The owner issues one-time codes and revokes sessions from the NAS CLI. Only hashes are stored in SQLite.
- Family members redeem a code in the local web app and can return to album review and search with the same browser. The session is scoped to album review, folder search and indexed previews.
- Existing Telegram and browser-token flows use the same indexing, search and curation logic.
- Network requests require HTTPS and configured API credentials. Plain HTTP remains available through loopback for the SSH tunnel and local development. Family writes require the exact scheme and host, and HTTPS sessions use secure cookies.

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

### MVP 13B — Album Places and Timeline

**Status:** `Done`

- Store an optional place in the existing album context and reuse its edit permissions.
- Browse by date and place from the family web, local API and Telegram. Show where each date came from.
- Use curated labels for place matching and keep GPS outside the album index.

**Acceptance:** Find a curated album by place and year, see the source of its date, and verify that private GPS metadata stays outside the default index.

### MVP 14A — Search Baseline and Bounded OCR

**Status:** `Done`

- Benchmark four metadata, four written-text, four visual and one negative query on nine synthetic images. Report exact matches, recall and latency.
- Compare deterministic search and the existing local OCR adapter. OCR recovers all four written-text cases, including year and linked-person restrictions. The visual cases still have no matches.
- Allow manual enrichment runs restricted to one album with the existing resumable index.

### MVP 14B — Local Visual Search Trial

**Status:** `Done`

- Compare a fixed bilingual tag vocabulary through the existing adapter and a similarity fallback using the same quantized CLIP model, with a pinned revision and verified files.
- Record build time, query latency and storage. Tags found the four original visual cases but missed a new paraphrase. Similarity found the paraphrase and one original case, and returned false positives for the wrong colour and setting.
- Verify year and linked-person restrictions together and retain the existing metadata behavior.

**Acceptance:** A visual query such as “red bicycle by the sea” can retrieve an unlabeled fixture. Results identify why they matched, and the baseline search works with the model disabled.

### MVP 15A — Guided Recall

**Status:** `Done`

- Narrow the preceding album or photo search by year, a linked person, or an exact album.
- Ask which album the user meant if multiple names match within the active filters.
- Reuse the web search form, Telegram's saved-search history and the existing retrieval service.

**Acceptance:** “Playa con Ana” can be narrowed with “antes de 2020”. The refined search can be pinned through the existing history.

### MVP 15B — Named Memory Collections

**Status:** `Done`

- Save selected photos and albums from the browser in private, owner-specific collections.
- Keep only references to indexed paths and their source roots. Retain missing entries across reindexing so the owner can inspect or remove them.
- Keep creation, display, entry removal and deletion behind the existing owner permissions.

**Acceptance:** Name a collection, reopen it later, remove one entry and verify that the originals are still in the same place.

### MVP 16A — Private Album Invitations

**Status:** `Done`

- Add revocable, expiring links that grant read-only access to one album from the browser.
- Verify the grant on each album, photo and thumbnail request and test that guests cannot use broader search, collections or curation routes.

**Acceptance:** A guest can open one shared album and its images. Revoking the grant removes access on the next request.

### MVP 16B — Backup and Recovery

**Status:** `Done`

- Add backup and restore for the database and user curation, plus a documented recovery drill.

**Acceptance:** A restore onto a fresh instance preserves collections and corrections.

### MVP 17A — Mobile Album Presentation

**Status:** `Done`

**Case:** A family guest should understand and browse a shared album comfortably on a phone, without gaining broader archive access or downloading every original.

- Reuse the existing album context and private invitation grant to show title, date, place and note in a compact shared-album header.
- Add a responsive cover and thumbnail-first gallery with an explicit action for each original. Do not introduce a new image store, frontend framework or external service.
- Keep every metadata, thumbnail and original request behind the existing per-album grant.

**Dependencies:** Existing album context, local thumbnail cache and MVP 16A grants only.

**Acceptance:** At a 360 px viewport, a guest can understand the album, browse previews and open one original; revocation still blocks the next metadata, preview and original request.

### MVP 17B — Batch Album Review

**Status:** `Done`

**Case:** After an index adds many albums, a curator should resolve repeated name-based suggestions without opening every album or loading photos.

- Add a compact pending-album queue that can select several albums and accept or reject one shared suggested tag across the selection.
- Stream pending indexed names until the queue is full so albums without suggestions cannot hide later actionable albums.
- Reuse the existing suggestion evidence and decision tables. Keep corrections and ambiguous albums in the current single-album review flow.
- Operate only on indexed names and SQLite; do not request thumbnails or originals during the batch action.
- Offer group actions to fill undecided rows and show how many decisions will be submitted. Keep existing row choices and require an explicit save.
- Preserve unsaved selections in other groups after a save and when returning from an individual album review. Restore a selection only if the refreshed queue still offers it with the expected album revision. If the refresh fails, keep the selections available through a read-only retry.

**Dependencies:** Existing deterministic vocabulary, album review permissions and decision persistence only.

**Acceptance:** Select three pending albums, accept a shared suggestion for two and reject it for one, then reindex and verify that all three decisions persist without any archive byte reads.

### MVP 18A — Scoped Read-only MCP Trial

**Status:** `Done`

**Case:** Fernando should be able to query selected family albums from an MCP-capable assistant without granting it access to the whole archive or making MCP necessary for normal use.

- Verify current MCP client and authentication capabilities against official documentation before choosing a transport.
- Prototype with synthetic metadata only and reuse the application service behind a read-only album-scoped principal. Do not send real photos, family metadata or credentials to an external provider.
- Keep the adapter optional and disabled by default. The browser, Telegram and indexing workflows must remain fully functional without it.

**Dependencies:** Existing application query service and album-level permission semantics. Any new SDK or network transport requires a separate cost, privacy and NAS-resource decision.

**Acceptance:** A synthetic scoped identity can list and search one granted album but cannot inspect another album, mutate curation or retrieve unrestricted originals; disabling the adapter leaves the existing test suite unchanged.

The trial confirmed that the authorization boundary can stay in the application layer without a transport or SDK. The tool core returns no archive paths or original URLs and checks expiry or revocation on every call. Current official documentation says ChatGPT needs public HTTPS or a Secure MCP Tunnel rather than a direct local process, so no endpoint or tunnel was enabled.

### Folder Curation MCP — Local Transport and Review

**Status:** `Done` for the synthetic stdio trial. The NAS and hosted-model evaluation are opt-in follow-ups.

- Browse selected albums or opt into paging the whole live SQLite index, optionally filtered by indexed year or missing place. Expose folder-name evidence, current metadata, known tag evidence, linked people and unambiguous matches to existing people. No photos, photo filenames, album-share tokens, or raw SQL.
- Propose a display title, full folder-derived date, named place, album tags and existing person links. Leave ambiguous dates and people unresolved. Never replace curated titles, dates, places or reviewed tag decisions.
- Stage proposals in private files without writing SQLite. Apply a selected batch from a terminal or opt into exposing the MCP write tool, with the host deciding whether to require approval. Reject stale or superseded proposals, apply atomically and record the write channel. Keep the web API, Android app and original files unchanged.
- Synthetic transport tests use the official MCP client, a private scope file and a disconnected archive. OpenCode 2.3.2 also connected to the synthetic server after explicit registration in the running service. The [operator guide](docs/src/content/docs/reference/mcp.md) covers NAS-side album selection, SSH setup, and applying proposals. The place-only test verifies an approved label is searchable without adding a general tag or building the future map.

## Active MVPs

### Phone-test follow-up — pick in this order

These are the next automation picks from the physical Android test against the NAS. Apply the browser changes alongside the APK where specified. Finish these tasks before expanding native owner tools or model-assisted curation.

#### 1. Reliable album covers and gallery thumbnails (Android and browser)

- First check that the deployed API has thumbnails enabled and can generate one for a representative indexed photo. Trace missing previews from the archive and API through both clients; separate deployment issues from client bugs. Android already requests visible album covers, so verify that path before replacing it.
- Show one cover per visible album in **Carpetas**: choose a random eligible indexed photo, keep the choice stable while browsing and on reload, and choose a replacement if it disappears or cannot be previewed. Inside the album, load low-resolution thumbnails for visible photos as the user scrolls. Request full-size originals only on explicit open, save or share.
- Reuse the existing NAS preview endpoint and disk budget. Add bounded, private thumbnail reuse on Android and in the browser. Invalidate previews when the source changes; scope reuse to the server and signed-in session. Clear or isolate previews at sign-out or origin change, and make sure revoked access cannot be bypassed by reopening cached private images. Never put family previews in a shared cache.
- **Acceptance:** On the phone and browser, album cards show covers and opening an album shows low-resolution thumbnails without downloading originals. Revisiting the same gallery avoids unnecessary thumbnail requests. A replaced photo refreshes its preview, and missing previews show a placeholder without blocking navigation.

**First increment:** Inspection found that the quick NAS setup installs only the Telegram extra and leaves `THUMBNAIL_CACHE_MIB=0` unless configured separately. This is a reproducible configuration pitfall, not a confirmed diagnosis of the running NAS. The bilingual configuration guide now explains how to check the authenticated thumbnail flag, enable the existing renderer deliberately and distinguish individual-image failures. Photo listings expose the existing SQLite revision identity without source reads. Android uses that identity for its existing 4 MiB cache and clears it after sign-out or an unauthorized response; old-server listings without identities bypass reuse. The browser adds a 4 MiB/64-entry memory-only thumbnail cache, clears it on sign-in/out or unauthorized responses, and discards late responses from an ended session. No schema or dependency is added. Stable randomized album covers, replacement after an unpreviewable cover, and the actual NAS/phone acceptance checks remain pending.

**Verification:** All 214 service tests (including the newly shipped local MCP transport), three Node UI suites and the bilingual documentation build pass on the updated main base; 737 internal links are checked across 25 pages. The cache regressions cover replacement identity, unchanged and disconnected indexing, memory/entry limits, old servers, logout, late responses and unauthorized fetches. [Android branch CI](https://github.com/42Azul/chromantis/actions/runs/45057774246) passes formatting, APK compilation, lint, 31 JVM tests and eight Android 16/API 36 instrumented tests, with no failures, errors or skips. Its nine synthetic PNG exports include the visually inspected light gallery and dark library. The Android/cache implementation is unchanged by the subsequent merge of the independent MCP work. No NAS configuration or deployment was changed.

**Cover API increment:** The private API now serves a JPEG cover using the existing thumbnail budget. It ranks up to 12 indexed entries by a stable path hash and tries up to three candidates. A missing or unpreviewable candidate can fall back to another, and a source outage stops the attempt. Client integration and phone validation remain pending.

Cover selection excludes photos whose indexed size exceeds the renderer limit before choosing its 12 candidates. A regression with 12 oversized entries before a small photo verifies that the cover is still returned and only the small photo is opened. Entries with unknown size still use the existing bounded reader.

**Android integration:** Album cards request the stable cover through the existing preview concurrency limit, with the original thumbnail flow as a compatibility fallback. [Android verification](https://github.com/42Azul/chromantis/actions/runs/45091864982) passed 31 JVM and eight emulator tests. Synthetic light and dark screenshots were reviewed. Physical-phone and NAS validation remain pending.

**Browser integration:** Visible album cards load stable covers in the search and year views. A synthetic HTTPS Chromium smoke test (`tests/browser_album_covers.cjs`) verifies that the year grid requests no covers, opening a year loads exactly one decoded cover, switching themes reuses it, and the flow downloads no originals. The light and dark captures were reviewed at a 390 px viewport. The deployed NAS and physical-device acceptance checks remain open.

#### 2. Save and share one photo or a selection (Android and browser)

- Add visible **Guardar/Descargar** and **Compartir** actions to the photo viewer and gallery selection toolbar. Keep selection for export distinct from tagging. Support a single photo, a multi-photo selection, and an explicit **Descargar álbum** action for saving everything, not just the currently loaded page.
- On Android, save originals to the phone gallery and use the Android share sheet for one or more photos so WhatsApp can receive them when installed. In the browser, download a single original or a ZIP for a selection or album. Use file sharing where the browser supports it and offer download as the fallback; don't assume every desktop or browser can hand files to WhatsApp directly.
- Keep downloads behind existing photo permissions. Bound batch work and temporary storage; confirm large exports and show progress, cancellation and partial failures. Don't upload anything until the user chooses a share target and confirms there.
- **Acceptance:** Save one photo to the Android gallery, share one and then several photos through WhatsApp on a physical phone, and download a selection and a multi-page synthetic album from the browser. Output contains only the intended originals, and a failed transfer can be retried without silently duplicating the successful ones.

**Selection export API:** A private POST route returns a ZIP of explicitly selected indexed originals. It deduplicates paths, caps each export at 20 entries and 16 MiB of input, and allows one export at a time per API process. It returns an error if the archive is unavailable or a file is missing. Synthetic HTTP tests cover authentication, exact ZIP contents and failure handling. The family web gallery now offers **Descargar selección** for checked photos on the current page. It keeps the selection on failure and cancels the browser request when leaving the selection or gallery. The synthetic Chromium smoke test verifies the exact requested paths and the resulting ZIP download at mobile width in both themes. **Descargar álbum** resolves every indexed photo in the album through the same export route and applies the same 20-photo/16 MiB ceiling. Oversized albums return an explicit error and can be downloaded by selections. Chromium downloaded all nine originals of a synthetic album while only the first six were visible, and both themes were reviewed at mobile width. The synthetic family HTTPS test verifies that a 33-photo album hits the limit and that a two-photo selection can be retried after reconnecting the archive, with byte-for-byte original contents. Browser file sharing and large-album exports remain pending. Android save and share are implemented as described below, with physical checks still open.

**Android single-photo save:** The original viewer can save the authenticated original bytes to `Pictures/Chromantis` on Android 10 and newer. It uses the client's existing 32 MiB read cap and MediaStore's pending flag, with no broad storage permission. Verification includes an instrumented byte-for-byte MediaStore check and light/dark viewer captures. Physical-device validation, Android 8–9 saving, multiple photos and the share sheet remain open.

**Android single-photo share:** **Compartir** opens Android's share sheet with one authenticated original, using the existing 32 MiB client cap. A private cache retains at most one prepared photo, and the receiving app gets a temporary read grant. The emulator checks intent permissions, original bytes and replacement of the prior cached export. The physical WhatsApp check remains open.

**Android selection share:** The gallery selection toolbar prepares up to ten originals with one 32 MiB aggregate budget and opens the Android share sheet only after successful preparation. The selection stays available on failure or cancellation. Requests are sequential and use the existing authenticated image route. The previous private export is replaced. The physical-device WhatsApp check remains open.

**Android selection save:** Android 10 and newer can save the selection to the phone gallery using the same ten-photo and 32 MiB transfer limits. Originals are committed individually. The current selection displays the completed count and retries only unfinished photos. Cancellation stops before the next write, and a write already in progress finishes. Physical-device validation remains open.

#### 3. Recover the second 2003 folder and recognize dates in album names

- Reproduce the reported missing `2003(2)` while `2003(1)` appears. The source adapters and path parser already accept both exact names; trace the exact folder spelling, directory depth, scan skips, indexed paths and year-list pagination before changing the parser. Both branches should appear under year **2003**, with distinct paths even if they contain albums with the same name.
- Gather a few sanitized examples of missed date-bearing names and extend deterministic parsing for the confirmed formats. Before the compact-date increment, indexing recognized a leading `YYYY-MM-DD` followed by `_`, `-`, or the end of the name. Reject invalid dates and leave ambiguous dates unguessed. Keep folder-derived dates separate from manual corrections, JPEG capture dates and file modification times.
- **Acceptance:** Synthetic local and FTP fixtures show both branches under 2003 in the API, browser and Android. Representative album names show the correct folder-derived dates. Document and test how to refresh existing affected rows without discarding manual corrections or other curation: today's incremental scan skips unchanged files, so use a full reindex unless a targeted metadata refresh is added.

**Split-year regression:** A synthetic FTP listing now exercises both MLSD and the NLST fallback through a scan, SQLite and the API. Year 2003 contains 31 albums, and opening the second page returns `2003(2)/album_00` even though page one has an identically titled album from `2003(1)`. The first page carries the extra result used by both clients to offer pagination. Exact branch names also worked in a local source check. The real NAS discrepancy remains unconfirmed. Follow the [maintenance guide](docs/src/content/docs/operate/maintenance.md) to distinguish a listing or scan issue from an index or client issue before changing the parser.

**Compact dates:** The existing FTP fixture uses `20210101 - Reyes`. Indexing now accepts leading `YYYYMMDD - Title` or a bare `YYYYMMDD` when the date is valid and agrees with the indexed year, including split-year branches. A full-scan regression refreshes the derived date in an existing SQLite index and preserves the manual date and title. The rule has been verified with synthetic names. Other formats still need representative examples.

#### 4. Run the physical-phone release checklist

Use the [Android guide recording sheet](docs/src/content/docs/use/android.md#physical-phone-release-checks) for one APK and device. The [Spanish guide](docs/src/content/docs/es/use/android.md#comprobaciones-en-un-teléfono-físico) carries the same checks. The synthetic HTTPS fixture supports `--split-year` and verifies that both same-title albums open as separate galleries across the page boundary. The HTTPS test also checks that a cached thumbnail remains available, and that uncached thumbnails and covers load again after the synthetic archive is restored using the same session. Physical results are pending.

- A first NAS phone test produced the reports above; it did not complete the release checklist. After the fixes, record the APK build, Android version and device model, and verify one-time sign-in, session recovery after a cold start and process death, gallery position, revocation on the next protected request, and recovery after Wi-Fi or NAS loss. Check local-network permission denial and recovery where the OS requires that permission.
- Rerun the cover, export and year-browsing acceptance checks on the same build. Use synthetic albums for repeatable checks and keep household addresses, folder names, invite codes and photos out of shared evidence.
- **Acceptance:** The checklist records pass, fail or not applicable for each scenario. Failures have a reproduction and owner; do not mark MVP 19A done while any required check is failing or unverified.

### MVP 19A — Android Family App (APK)

**Status:** `In Progress` — emulator flow and test APK delivered; physical-phone release checks pending

**Case:** A family member can open Chromantis from an Android home-screen icon, sign in with a one-time family code and find or review an album over the home Wi-Fi without a Telegram account.

**Scope:** Make **Carpetas** the home screen. Use the familiar Cx File Explorer pattern: browse by year, open a folder, see its path and return to the same place. Show photos in a paged grid with thumbnails loaded when the user opens the grid and reaches the relevant rows. Load an original only when opened. Keep the existing album review as a separate action with explicit photo previews. Reuse the local HTTP API, SQLite index, and revocable family permission. Build a small native Android client in Kotlin and Jetpack Compose, with a Spanish UI and English code and technical documentation, and produce a signed APK for private testing. The archive stays read-only and the web and Telegram remain independent clients.

**Dependencies:** Android SDK and build tools on the development computer, the family-session, album-review, year and paged album-image APIs, and a reachable HTTPS endpoint on the private test network with certificate validation. Check local-network permissions for the chosen target SDK and private installation rules for the test device. The NAS runs the existing service.

**Acceptance:** Build and install the APK on an emulator or test phone with synthetic albums. Sign in once, reopen the app and navigate year → folder → photo, then go back to the same folder position. Link the fixture person Ana to an album, save it, and find the album by searching for Ana. Verify revocation on the next protected request. With the photo source disconnected, folder navigation, filename listing and album tagging still work. Preview errors, an unreachable NAS and a denied local-network permission where applicable show how to recover.

**Progress:** The Kotlin and Compose client includes HTTPS family sign-in, session persistence, year and album navigation, album search, and a paged photo grid. It saves the explorer path when Android recreates the activity. It can open the pending album review queue or correct a specific album. It uses index metadata for listings and review and requests previews on demand. The temporary HTTPS fixture covers synthetic browsing and curation. A loopback test verifies the one-time code, secure session cookie, gallery pagination, search after tagging with the archive disconnected, and revocation on the next request. Gradle creates the release variant only with complete private signing configuration from an ignored local file or environment variables. Verified that a general build without keys produces only a debug APK and that the release APK passes independent signature verification. An initial physical-phone test against the NAS informed the follow-up above; the complete release checklist is still pending.

**References:** [Cx File Explorer](https://play.google.com/store/apps/details?id=com.cxinventor.file.explorer), [Android lazy grids](https://developer.android.com/develop/ui/compose/lists), [APK distribution](https://developer.android.com/studio/publish), [network security](https://developer.android.com/privacy-and-security/security-config), and [local network permissions](https://developer.android.com/privacy-and-security/local-network-permission).

**Interaction design:** Use three equally visible entry points: **Carpetas**, **Clasificar**, and **Buscar**. Keep layouts quiet with neutral surfaces, one accent and clear text labels. **Ajustes** remembers the system, light or dark appearance. Each entry point keeps its own saved screen state. Take the predictable navigation and selection patterns from file managers. Test other controls only when they shorten a family task. The browser sidebar also offers system, light and dark appearance before and after sign-in, stored locally in that browser.

**Family visual design:** The Android library now uses a year grid with indexed counts, rounded navigation controls at the bottom, and readable album cards. Entering an album list loads one cover for each visible card through the existing bounded thumbnail client; the home year grid stays metadata-only. Album titles and date captions are formatted for display without altering indexed paths. Manual review groups selectable people with initials and aliases and keeps Save and conflict feedback outside the scrolling form. The warm light and dark palettes share the same hierarchy. [DESIGN.md](DESIGN.md) records the reviewed Android, Ente, Immich and design-tool references and the intended direction. A separate connected synthetic fixture exercises visible covers while the existing client regression retains its disconnected archive. Verified in [branch CI](https://github.com/42Azul/chromantis/actions/runs/44486813440): 30 JVM tests and six Android 16/API 36 instrumented tests pass without failures, errors or skipped tests, together with formatting, APK compilation, lint and five validated PNG exports. All five light/dark and curation screenshots were visually reviewed. The Compose test requires Save to be visible without scrolling and waits for actual cover and gallery bitmaps. Next visual work should bring the same hierarchy to the quick-review deck and chat search, while launcher lifecycle and physical-phone checks remain explicit parallel validation work.

**Quick classification design:** The Android **Clasificar** workspace now presents one folder as a focused, rounded card with a readable title and date, a quiet suggestion panel, and the exact folder-name evidence. Swipe remains optional: accept, leave pending and open the full people/photo/tag editor are explicit controls. The card uses index metadata only and opens no preview. The shared swipe surface now has restrained motion and the same shape and elevation in album and per-photo review. A 320×640 regression requires all three actions to remain visible, after the first version exposed an overflow in that viewport. Verified in [branch CI](https://github.com/42Azul/chromantis/actions/runs/44510741303): formatting, APK compilation and lint pass; all 30 JVM and six Android 16/API 36 instrumented tests pass with no failures, errors or skipped tests; six synthetic PNG exports validate the updated walkthrough. The classification capture was visually reviewed before publication. The next visual target is the conversational search surface, followed by the documented launcher lifecycle and physical-phone checks.

**Session protection:** Saved family sessions use AES-GCM with a non-exportable Android Keystore key and authenticate the NAS origin as additional data. Startup migrates legacy plaintext sessions; damaged envelopes or unavailable keys require a new family code, with no plaintext fallback. A failed save keeps only the active in-memory session and shows a warning. Sign-out and server revocation clear the envelope and album shortcut. Backup and device-transfer exclusions remain in place. JVM tests exercise real AES-GCM with synthetic keys, migration, tampering, origin binding, failed persistence and key loss. Verified: all 28 Android unit tests and 200 service tests pass, the debug APK and its signature verify, and lint reports no errors (three existing warnings). Hardware-backed behavior depends on the device; Keystore creation, migration and recovery still need the documented physical-device drill before extending native owner access. See [Android Keystore](https://developer.android.com/privacy-and-security/keystore).

**Platform session verification:** Four Android instrumentation tests use the actual Android Keystore provider with random test-only aliases and preferences. They cover encrypted persistence and non-exportability, legacy migration, origin mismatch, and key-deletion recovery without touching production keys, the NAS or release signing. A public-repository-only Linux workflow checks formatting, JVM tests, debug APKs and lint before running the instrumented suite on an API 36 emulator. Verified on [branch CI](https://github.com/42Azul/chromantis/actions/runs/44464949064): all 28 JVM tests and four instrumented tests pass on Android 16/API 36, with no failures, errors or skipped tests. Formatting, debug app and test APK compilation, and lint also pass. Both documentation languages build with 690 checked links across 25 pages. A physical-device check and the full family interaction flow remain required before native owner access.

**Native HTTPS integration:** A test-APK-only fixture runs the Kotlin client against the real Python service with the synthetic photo source disconnected. It exercises one-time sign-in, Keystore session restoration, metadata paging, the Ana album link and alias search, and rejection after sign-out. The fixture binds to loopback; only the instrumentation process trusts its generated certificate, retaining hostname verification. Test assets and preferences are isolated from production data. Verified on [branch CI](https://github.com/42Azul/chromantis/actions/runs/44469806637): 28 JVM tests and five Android 16/API 36 instrumented tests pass with no failures, errors or skipped tests; formatting, debug APKs and lint pass too. The existing Python HTTPS fixture regression and the helper startup/termination check pass. English and Spanish documentation builds with 696 checked links across 25 pages. The Compose control flow is covered by the walkthrough below; launcher lifecycle and physical-phone checks remain pending.

**Compose walkthrough:** An instrumented test hosts the production sign-in and explorer composables without opening saved family preferences. It presses sign-in, year and album navigation, selects Ana, saves, switches appearance and finds the album by alias. A separate synthetic one-time code and the untouched 2023 album keep it independent of the HTTP client test. Optional screenshot capture uses synthetic pixels only, on a disposable API 29+ emulator; CI validates PNG headers and exports library, cover, gallery and curation screens after app cleanup. English and Spanish guides explain the folder list, album links and appearance with these captures. Verified in [CI, attempt 2](https://github.com/42Azul/chromantis/actions/runs/44477803272/attempts/2): all 28 JVM and six Android 16/API 36 instrumented tests pass without failures or skipped tests, together with formatting, debug APK compilation, lint and PNG export. The three captured screens were visually inspected before inclusion in the guides.

**Launcher lifecycle:** A separate instrumented test opens the exported `ExplorerActivity` rather than hosting its composables. It signs in with a dedicated one-time code, confirms that production preferences contain only the encrypted session, visits a gallery, recreates the activity, closes it and starts a fresh activity. **Continuar en…** restores the gallery and sign-out removes both the encrypted session and shortcut. The two visual tests use separate fixture invitations, the archive is disconnected, and the fixture cleans up its generated asset. Verified in [branch CI](https://github.com/42Azul/chromantis/actions/runs/44532324264): formatting, APK compilation and lint pass; all 30 JVM and seven Android 16/API 36 instrumented tests pass with no failures, errors or skipped tests. This covers activity recreation and a fresh launch, not process death, manufacturer-specific local-network behavior or hardware-backed Keystore on a physical phone; those checks remain the next release gate.

**Test APK handoff:** Successful Android push runs now verify the debug APK signature and checksum after the full test suite, then retain only the APK and `SHA256SUMS.txt` for seven days. The bilingual Android guide explains how to download, verify and install it, and distinguishes this disposable debug build from a privately signed release. No NAS address, invitation, family metadata, photos or release key is included. Verified in [branch CI](https://github.com/42Azul/chromantis/actions/runs/44534989034): formatting, APK compilation and lint pass; all 30 JVM and seven Android 16/API 36 instrumented tests pass with no failures, errors or skipped tests. The published artifact was downloaded again and its checksum passed. Installing it on a current physical phone and completing the family flow remain the next release gate.

**Family sign-in design:** Android now introduces the private archive as a short two-step flow: the household HTTPS address followed by the owner's one-time family code. The compact screen explains that photos remain at home and that the returning session is protected on the device; the existing implementation keeps the saved secret encrypted with Android Keystore and revocable by the owner. The code field submits from the keyboard, the form remains scrollable on small phones, and no OAuth provider, external account or new dependency is required. The synthetic walkthrough captures the screen independently in light and dark appearance, signs in, and still signs out at the end. Verified in [branch CI](https://github.com/42Azul/chromantis/actions/runs/44634117119): formatting, APK compilation and lint pass; all 30 JVM and eight Android 16/API 36 instrumented tests pass with no failures, errors or skipped tests; nine synthetic PNG exports cover the complete walkthrough. The sign-in captures were visually inspected before publication. Physical-phone installation, private-LAN behavior and hardware-backed Keystore remain the release gate.

**Quick album review:** **Clasificar** shows a pending album and one folder-name suggestion with its evidence. Right accepts the displayed suggestion, left skips for this pass, and buttons offer both actions. The detailed editor remains available for people, optional photo previews, and corrections. Verify short and cancelled drags, a folder with several suggestions, and a skipped folder that reappears when the curator restarts the queue.

**Explorer shortcuts:** The folder trail links to the year list, the current year and, from an original photo, its gallery. **Continuar en…** on the home tab reopens the last gallery browsed through folders at its last loaded page. The shortcut is stored locally and cleared when the family session ends. Verify on a phone that the shortcut survives a cold start and that the year and album steps return to their existing positions. The family browser also lists indexed years with album and photo counts, opens paged albums for a year, and returns from an album editor to that page without archive reads.

### MVP 19B — Manual Photo Tagging

**Status:** `In Progress` — service and both clients delivered; combined native interaction and phone comparison pending

**Case:** A family member who knows which photos show Ana can record that for those photos and find them later.

**Scope:** Add **Etiquetar fotos** to the gallery. Let the curator select one or more photos and apply manual tags or link existing people, correct changes, or skip. Test a brief optional prompt inside the review mode and keep prompts out of ordinary browsing. Reuse the people directory and existing curation permission. Store explicit photo-level evidence in SQLite separately from indexed tags and album-level links.

**Dependencies:** MVP 19A gallery, existing person IDs and aliases, and a migration with stable indexed photo identity. Preserve decisions for unchanged indexed paths across reindexing and define what happens when a photo is replaced.

**Acceptance:** Link Ana to the album and tag only two of three synthetic photos with Ana. The photo-level filter returns exactly those two while album search still finds the album. Correct one link, reindex and verify the remaining decision and its origin. A non-curator cannot edit. No metadata is written to image files.

**Progress:** The application service and local HTTP API support curator-only photo edits, SQLite provenance, and paged search by confirmed person. Full and incremental scans preserve decisions for unchanged indexed photos. The Android gallery supports explicit selection and long press, with one atomic batch of additions or removals per page. **Buscar → Fotos por persona** uses the confirmed-photo endpoint. The family browser also lists confirmed photos by name or alias, with paged results and originals opened on demand. Curators can add or remove people on an individual photo from those results or any page of the album gallery, using the existing photo identity and permissions. The family gallery can also add or remove the same people and manual tags on several selected photos from one page, in one atomic save. The individual photo editor supports manual tags too. Family photo-search results reuse the gallery selection controls and batch editor for a bounded page, including photos from different albums. Select-this-page and cancel are explicit; mixed-album batches show full paths. Saving preserves the search filters and paging, falling back when a page becomes empty. All 201 service tests and three Node UI suites pass. Synthetic UI and HTTP regressions cover exact selection, stale page events, cross-album atomic edits, and a disconnected archive without photo reads. Visual review remains pending here: terminal Chromium cannot create its process-singleton socket, and the browser surface cannot access the loopback fixture. The family browser has a paged exact manual-tag search backed by the existing SQLite table. Correcting a tag refreshes the same search. A confirmed-person search can be narrowed by an exact manual tag on that same photo, preserving both constraints across pages and album navigation. Android offers the same optional tag in Photos by person and restarts result paging when either submitted filter changes. The debug APK builds, formatting passes, and all 17 Android unit tests pass; the combined-filter phone drill is documented in both languages. A photo result can open its album editor and return to the same search page, with or without saving album changes. Browsing and photo edits leave the album draft in place. A changed identity requires a reload before making another edit. The synthetic HTTPS family session verifies batch edits, combined alias and manual-tag search, and correction with the archive disconnected. The Android phone interaction test is still pending.

**Photo review trial:** Android and the family browser offer the trial on the current gallery page. With thumbnails enabled, **Revisar foto a foto** lets a curator choose one existing person and review the current gallery page. The right gesture marks the visible photo and the left gesture skips it for this pass. Buttons offer both actions, and **Deshacer** revisits the last decision. **Guardar** sends a single batch for the newly marked photos. This trial uses people only and requires a visible preview before marking a photo. The bilingual browser guide illustrates the current gallery, batch editor and review with screenshots from synthetic fixtures. Keep manual tags in the batch editor. Compare the two flows on the same small synthetic album on a phone, measuring time and incorrect selections.

**Interaction test:** Provide an explicit **Seleccionar** action and a long-press shortcut. Keep the number selected and the **Etiquetar** action visible while browsing a page. Preview proposed people or tags before saving only to the selected photos. After validating the gallery flow, test opening a search result directly in this mode with its album context. Verify that Back cancels selection without writing and that the normal tap still opens a photo.

### MVP 19C — Index and People Tools

**Status:** `In Progress` — browser scan trigger and native read-only index status delivered; native people tools and owner access remain

**Case:** The owner has added folders to the NAS and wants to update the catalogue and check the result from the app.

**Scope:** Add **Herramientas → Índice** for last run, status and **Buscar carpetas nuevas**, a background incremental scan. Reserve the trigger for an owner credential, share a single scan lock with scheduled scans, and reuse the existing scanner and run history. Give the owner a place to inspect database readiness and reach existing backup and verification tools. Keep initial NAS setup and destructive recovery in the existing CLI. Group the directory, aliases and corrections under **Personas**, with the current role checks.

**Dependencies:** Existing incremental scanner, run summaries, backup commands and owner authorization. The app must never pass arbitrary commands or filesystem locations to the server.

**Acceptance:** Add a synthetic folder, start an incremental scan from the owner UI and confirm only one run starts under concurrent requests. See its status and find the folder without opening any image. A family curator can tag albums, while the same credential is denied an index trigger. A failed scan preserves the last complete index and reports the failure.

**Progress:** The existing browser admin panel can request a background incremental scan and refresh its run history. The API checks the owner role and accepts no scan options. Scheduled and manual runs share the same lock beside SQLite. Synthetic HTTP tests cover role denial, contention with a separate process, successful discovery and failure with the previous index intact. Android Settings now opens a read-only index status screen using the existing family-authorized archive-status endpoint. It shows the current scan state and last successful date, refreshes only on demand, and reuses session-expiry and connection recovery. No archive access or background polling is needed. A synthetic HTTP test covers a disconnected archive, a failed scan retaining the previous success date, and session revocation; Android parsing tests cover empty history and unknown states. The debug APK builds, all 20 Android unit tests pass, and lint reports no errors (three existing warnings). Native scan triggers with a separate owner credential and the physical phone interaction test remain pending.

### MVP 19D — Chat Search and Local Model Comparison

**Status:** `In Progress` — rules-first chat delivered; bounded model comparison deferred until the family flow is validated

**Case:** A family member can ask «fotos de la playa con Ana antes de 2020» from the **Buscar** tab, inspect the filters and open the result in its folder.

**Scope:** Start with the existing Spanish rule interpreter, query refinement, and deterministic search. Keep the chat read-only and ask for clarification when a year or person is ambiguous. Compare the rules with one small locally run quantized text model through the existing command adapter. Try it on a development computer first, send only the query to the local process, validate structured output, and retain the rules as default and fallback. Keep OCR and image/text search as separate optional experiments from MVP 14.

**Dependencies:** Existing interpreter, refinement and search services. For the comparison only, a pinned GGUF model, model license and a local runtime such as [llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md). Set latency and memory budgets before considering the NAS.

**Acceptance:** On the same synthetic Spanish prompts, compare correct filters and clarification for both modes. Report latency, peak memory and model size. Cover aliases, compound dates, ambiguity, invalid model output and timeout. Enable the model only if it improves retrieval within the stated budget.

**Progress:** Android **Buscar** starts a regular album search and accepts follow-up messages through the existing private refinement API. It shows the active phrases and lets the user choose an album if the name is ambiguous. This first flow needs no model. The rules recognise Spanish album requests and explicit ranges such as “de 2018 a 2020” and “entre 2018 y 2020”. Unconnected years still prompt for clarification. The family browser shows refinements as removable person, year and album filters and refreshes the results with the remaining constraints. Android uses the same album search response to show removable filters and reruns the remaining query from the first page. Android still supports servers that omit filter metadata. Compare removal with starting over on a phone. The album search API accepts a Spanish request such as “fotos de la playa con Ana antes de 2020”. It resolves a name or alias to a curated album link, applies an exclusive year boundary, and preserves both constraints in follow-ups. A synthetic family API test covers the flow with the archive disconnected. Album requests and follow-ups now accept lists of existing people or aliases joined by commas, Spanish y/e or English and. They compose the existing person filters with AND, preserve exact aliases containing separators, deduplicate IDs, and reject a list containing unknown names without changing the previous search. API, search, and Telegram regressions cover these rules with a disconnected archive. All 203 service tests and three Node UI suites pass.

**Conversational search design:** Android **Buscar** now opens as a calm prompt surface with grounded examples instead of an empty utility form. A submitted request remains visible as a message, the same composer accepts one refinement at a time, and removable deterministic filters stay beside the visual album results. **Fotos por persona** remains a separate exact photo-level action, so the interface does not blur confirmed links with album search or imply that a model ran. The result area reuses the existing album cards, thumbnail client and navigation. Verified in [branch CI](https://github.com/42Azul/chromantis/actions/runs/44521306283): formatting, APK compilation and lint pass; all 30 JVM and six Android 16/API 36 instrumented tests pass with no failures, errors or skipped tests; seven synthetic PNG exports validate the walkthrough. The 320×640 dark search capture was visually reviewed before publication. The next product validation is the documented launcher lifecycle and full flow on a physical phone; only after comparing this rules-first UX should a bounded local model trial be considered.

## Ready Next

### MVP 20A — Family Web Design and Accessibility

**Status:** `Ready Next`

**Case:** Fernando's father can identify the next pending album, choose Ana, save and find the album again from a phone or home computer, with a clear and welcoming interface.

**Scope:** Bring the existing family browser review and search to the visual hierarchy recorded in [DESIGN.md](DESIGN.md): readable album title/date, quiet grouping, coherent labelled icons, clear selected people and one visible primary action. Reuse current routes, drafts, permissions and thumbnails. Keep preview loading explicit in album review. Improve one complete task before adding more screens. Preserve light, dark and system appearance and make the family navigation usable without knowing technical terms.

**Dependencies:** Existing browser, album/person APIs and synthetic UI fixture only. Use the reviewed design references; no new frontend framework, paid design service, remote fonts or runtime CDN.

**Browser album viewer:** Keep **Buscar álbumes** focused on finding and opening albums. Open search results in a browsing view and enter the existing editor through an explicit **Etiquetar álbum** action for curators. Preserve the search query, filters and page on return. Reuse gallery, thumbnail and export controls. The synthetic HTTPS Chromium flow verifies that opening a result does not load the editor or photos, returning after an intentional edit restores the year results, and searching for Ana finds the edited album. The viewing gallery retains selection and album downloads.

**Keyboard and large text:** Opening the editor from a search result moves focus to the person search once the editor loads, provided focus is still on the return button. The synthetic Chromium run uses Tab and Enter to enter the editor, select Ana by alias and save. It checks focus on the restored results, finds the edited album by name, and checks for horizontal overflow at 200% text size at mobile and desktop widths.

**Offline save recovery:** With the synthetic archive disconnected and thumbnails disabled, Chromium verifies that a failed save leaves Ana selected, puts the error beside the save button and allows retrying the same changes. Retrying persists the link and search finds the album by Ana. The test rejects all media requests and external traffic. Both themes were reviewed at 360 px.

**Validation:** At 360 px and desktop widths, complete open album → select Ana or her alias → save → find by Ana. Inspect synthetic light/dark captures, keyboard focus, touch targets, large text, empty/error states and the visible save action. Confirm that ordinary navigation and name-only review require no originals or external requests. Record the remaining physical-phone usability check separately.

### MVP 20B — Family Authentication Review and Passkey Trial

**Status:** `Ready Next` for the existing-auth review; passkey implementation is gated on origin and recovery validation

**Case:** Family members return easily with limited access, and the owner can revoke a lost device without running an external identity service.

**Scope:** First review the current invitation → session → protected request → revocation path across the browser and Android. Document what protects against code guessing, replay, cross-site writes, session theft and privilege escalation; add regression coverage for any demonstrated gap. Keep HTTPS, bounded invitations, hashed server secrets and limited curation as the free default. Do not describe any option as absolutely secure. Keep owner credentials outside the family app until its separate access design and device checks are complete.

**Existing access review:** The code uses 32 random bytes for each invitation and session, stores only their digests, and exchanges the invitation for a new secret in one conditional SQLite update. The existing suite includes a two-thread redemption test, expiry, revocation and same-origin write checks. The bilingual access guide now records the lost-device recovery order and distinguishes archive-wide family curation from single-album sharing. A synthetic HTTP regression now verifies CLI revocation and replacement: the lost credential and its invitation stay invalid, the replacement retains family permissions, and another household session remains active. Physical-device recovery and the passkey trial remain open.

**Optional next increment:** Use an existing invitation to enroll a passkey through a maintained WebAuthn library, with required user verification, one configured RP ID/origin, short-lived single-use challenges, per-credential revocation and recovery by a new owner invitation. Store public credentials and permissions in the existing SQLite database. Do not implement signature or attestation verification by hand. Compare device-local and synced credential recovery; do not promise offline sign-in on every authenticator.

**Dependencies and decision:** A stable DNS name, trusted HTTPS and compatible authenticators are required for the passkey trial. W3C specifies secure contexts and explicit origin/RP binding. Google's web OAuth redirect rules reject raw IP hosts except loopback, so a typical LAN-IP NAS is not a drop-in Google web login. Our current choice is to validate the local approach first; Google/OIDC remains an opt-in alternative only if an identified household need justifies provider configuration and internet dependence. Official [WebAuthn Level 3](https://www.w3.org/TR/webauthn-3/) and [Google web redirect requirements](https://developers.google.com/identity/protocols/oauth2/web-server#uri-validation) were checked on 2026-11-22. No provider is enabled by this roadmap.

**Validation:** Existing auth tests reject expired/reused invitations, revoked sessions, cross-origin writes and curator administration; verify concurrent redemption and recovery. For a later synthetic passkey prototype, reject wrong origin/RP, wrong challenge, missing user verification, replay and revoked credentials. Try two household device/browser combinations with internet disconnected after enrollment, report any authenticator dependency, and measure recovery steps and NAS request/idle cost. The web remains usable with passkeys disabled.

## Planned Later

### Owner-only missing-album diagnostics

**Case:** When an album is absent after a scan, the owner can tell whether it was skipped, not indexed, or indexed but missing from a browse page.

**Scope:** Start with a read-only CLI check for one owner-supplied, archive-relative path. Reuse the source adapters, parser and index queries to distinguish an unavailable source, depth or parsing skips, and indexed albums. Report inconclusive results explicitly when the available scan data cannot explain a skip. Do not fetch photos, trigger a scan, or expose paths through family-facing endpoints.

**Index-only increment:** The operator can check an exact album path and its photo count through `scripts/diagnose_album.py`. The command opens the existing SQLite file read-only, needs no archive connection and reports absence without assigning a cause. A synthetic scan of two same-title albums in separate year branches verifies both lookups after disconnecting the archive. Pass `--check-source` to list only that album’s direct entries over local storage or FTP (MLSD or NLST fallback). The diagnostic counts supported photos and subfolders without retrieving images. An unavailable or unlistable folder is reported as inconclusive. The production NAS branch remains unverified.

**Validation:** Synthetic local and FTP fixtures distinguish a skipped branch from an indexed album on a later page and an unreachable source. The command leaves the archive and curation unchanged.

### MVP 19E — Face Review Trial

**Status:** `Planned Later`

**Case:** The owner can prepare a small set of photos for review in **Personas → Caras** and confirm or correct suggested face-to-person links.

**Scope:** Separate detection of face regions, similarity suggestions, and confirmed identities. Test optional local processing of one small selected album, initially on a development computer. Record progress and source/model provenance so a run can resume and skip unchanged photos. Show suggested matches for approval or rejection and allow correction and deletion. Confirmed links refer to the exact photo. Keep face processing off by default and independent of indexing. Keep all derived face data local and define its deletion policy before persistence.

**Dependencies:** MVP 19B photo-level links, a bounded processing and cancellation path, and synthetic face fixtures. Compare [ML Kit face detection](https://developers.google.com/ml-kit/vision/face-detection) for Android-only detection with [OpenCV YuNet and SFace](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html) for a local detection and similarity trial. Verify model licenses, measure CPU, memory, per-photo time and storage, and calibrate on the trial data before adopting a threshold.

**Acceptance:** Process a bounded synthetic batch, interrupt and resume it, review a proposed match and reject an unknown or lookalike without creating a confirmed link. A wrong suggestion can be corrected and derived data can be removed. Reindexing alone never runs the model or alters originals.

### Optional remote MCP transport and hosted-model evaluation

**Case:** Evaluate how accurately a hosted model proposes folder curation, then decide whether OpenCode over local stdio (including over SSH) is sufficient or a separate remote connector is justified.

**Scope:** Trial [OpenCode V2](https://opencode.ai/docs/mcp-servers) with GPT‑6.2 Sol using the shipped stdio tools on synthetic folders. A direct remote connector would be separate work: use authenticated, revocable, narrowly scoped access, keep it proposal-only by default, and leave the adapter disabled when unused.

**Dependencies:** OpenCode must be able to reach the chosen transport; the existing Chromantis HTTPS endpoint is not an MCP endpoint. Verify what tool output goes to the configured model provider. Real family metadata stays out of a hosted model unless the owner explicitly approves the specific data. Trial visual tagging with synthetic images or local inference first; use only explicitly selected, small previews if an owner approves a hosted image trial. Never grant the model unrestricted archive access or send originals by default.

**Validation:** Compare synthetic model proposals with known correct dates, acceptable titles, ambiguous people and existing tag rules. Before shipping any remote connector, verify discovery and live revocation and reject out-of-scope albums, database writes and original bytes. Measure idle memory and request latency on representative NAS hardware before deployment.

### Optional visual curation

- Try a second pass only for albums whose folder names provide little evidence. Start with synthetic images and local inference. Pick a small, representative sample of low-resolution previews from one operator-selected album; use it to propose reviewable scene, activity or object tags, not exact dates or identities.
- Compare folder-only results with folder plus visual evidence on a separate evaluation set. Measure useful tags, unsupported guesses, CPU and memory. Keep visual provenance distinct from folder-name evidence and require approval before applying a suggestion. Don't send family images to a hosted model without explicit approval of the specific preview sample.

### Browse albums by place and map

**Case:** A family member opens **Lugares** in the Android library, chooses a place, and browses its albums across years. A map offers another way into the same list.

**Scope:** Build the place list first using the existing curated album labels and permissions. MCP may propose a label explicitly named in the folder, but must not guess coordinates. Let a curator confirm an optional map point at city, town, or region precision, and reuse it across albums that share that place. Keep unresolved or text-only places searchable without putting them on the map.

**Privacy:** Do not request the phone's location or extract photo GPS for this feature. Keep album-to-place links and confirmed coordinates private. Before selecting a map or geocoding provider, check what requests disclose to third parties, and keep the place list usable without that provider.

**Acceptance:** Two albums labeled Madrid in different years appear under one confirmed marker and in the place list. An ambiguous name stays off the map until a curator resolves it. Opening a place and returning from an album restores the previous map or list position.

### Optional EXIF GPS

- Revisit only if manual places leave a specific retrieval gap, such as finding unlabelled photos from a known trip.
- Reuse the bounded local JPEG header reader in a separate opt-in workflow. Define how the owner controls visibility and clears retained coordinates before storing any.
- Validate activation and deletion on synthetic coordinates. Default extraction, browsing and search must continue to leave GPS out.

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
