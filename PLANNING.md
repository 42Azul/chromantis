# Chromantis Roadmap

This file tracks delivery status, upcoming MVPs, and the implementation direction of the project. Use it as the roadmap and progress ledger for Chromantis.

`README.md` is the project index. The [documentation sources](docs/src/content/docs/) cover installation, usage, maintenance, and development. This document explains what is already shipped, what is ready next, and what is intentionally deferred.

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
- direct photo browsing from Telegram person cards and home or command shortcuts to both search histories
- optional image enrichment with model provenance and opt-in search over captions, OCR, and object tags
- incremental indexing with stored sync summaries, a cron recipe, and bounded enrichment retries
- a browser interface for visual search, browsing, people, saved searches, and role-based administration
- browser-based album review with name-only tag suggestions, manual tags, curated people and limited viewer permissions
- batch acceptance and rejection of repeated name-based album suggestions without photo reads
- local browser-only family sign-in with one-time codes and revocable SQLite sessions
- album aliases, notes, and title and date corrections shared by the browser and Telegram
- optional local thumbnails with a disk budget and an index freshness indicator
- opt-in JPEG capture dates with separate camera, album and file-time provenance
- manually curated album places and a dated timeline shared by the browser, API and Telegram
- revocable, expiring browser links that grant read-only access to one album
- consistent, locally verifiable SQLite backup and fresh-path recovery
- a transport-neutral read-only MCP tool trial scoped by a revocable one-album grant

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

## Ready Next

### MVP 19A — Android Family App (APK)

**Status:** `Ready Next`

**Case:** A family member can open Chromantis from an Android home-screen icon, sign in with a one-time family code and find or review an album over the home Wi-Fi without a Telegram account.

**Scope:** Make **Carpetas** the home screen. Use the familiar Cx File Explorer pattern: browse by year, open a folder, see its path and return to the same place. Show photos in a paged grid with thumbnails loaded when the user opens the grid and reaches the relevant rows. Load an original only when opened. Keep the existing album review as a separate action with explicit photo previews. Reuse the local HTTP API, SQLite index, and revocable family permission. Build a small native Android client in Kotlin and Jetpack Compose, with a Spanish UI and English code and technical documentation, and produce a signed APK for private testing. The archive stays read-only and the web and Telegram remain independent clients.

**Dependencies:** Android SDK and build tools on the development computer, the family-session, album-review, year and paged album-image APIs, and a reachable HTTPS endpoint on the private test network with certificate validation. Check local-network permissions for the chosen target SDK and private installation rules for the test device. The NAS runs the existing service.

**Acceptance:** Build and install the APK on an emulator or test phone with synthetic albums. Sign in once, reopen the app and navigate year → folder → photo, then go back to the same folder position. Link the fixture person Ana to an album, save it, and find the album by searching for Ana. Verify revocation on the next protected request. With the photo source disconnected, folder navigation, filename listing and album tagging still work. Preview errors, an unreachable NAS and a denied local-network permission where applicable show how to recover.

**Progress:** The Kotlin and Compose client includes HTTPS family sign-in, session persistence, year and album navigation, album search, and a paged photo grid. It saves the explorer path when Android recreates the activity. It can open the pending album review queue or correct a specific album. It uses index metadata for listings and review and requests previews on demand. The temporary HTTPS fixture covers synthetic browsing and curation, including an index-only mode. Gradle creates the release variant only with complete private signing configuration from an ignored local file or environment variables. Verified that a general build without keys produces only a debug APK and that the release APK passes independent signature verification. Installation and the complete interaction flow on a current physical phone are still pending.

**References:** [Cx File Explorer](https://play.google.com/store/apps/details?id=com.cxinventor.file.explorer), [Android lazy grids](https://developer.android.com/develop/ui/compose/lists), [APK distribution](https://developer.android.com/studio/publish), [network security](https://developer.android.com/privacy-and-security/security-config), and [local network permissions](https://developer.android.com/privacy-and-security/local-network-permission).

**Interaction design:** Use three equally visible entry points: **Carpetas**, **Clasificar**, and **Buscar**. Keep layouts quiet with neutral surfaces, one accent and clear text labels. **Ajustes** remembers the system, light or dark appearance. Each entry point keeps its own saved screen state. Take the predictable navigation and selection patterns from file managers. Test other controls only when they shorten a family task.

**Quick album review:** **Clasificar** shows a pending album and one folder-name suggestion with its evidence. Right accepts the displayed suggestion, left skips for this pass, and buttons offer both actions. The detailed editor remains available for people, optional photo previews, and corrections. Verify short and cancelled drags, a folder with several suggestions, and a skipped folder that reappears when the curator restarts the queue.

**Explorer shortcuts:** The folder trail links to the year list, the current year and, from an original photo, its gallery. **Continuar en…** on the home tab reopens the last gallery browsed through folders at its last loaded page. The shortcut is stored locally and cleared when the family session ends. Verify on a phone that the shortcut survives a cold start and that the year and album steps return to their existing positions.

## Planned Later

### MVP 19B — Manual Photo Tagging

**Case:** A family member who knows which photos show Ana can record that for those photos and find them later.

**Scope:** Add **Etiquetar fotos** to the gallery. Let the curator select one or more photos and apply manual tags or link existing people, correct changes, or skip. Test a brief optional prompt inside the review mode and keep prompts out of ordinary browsing. Reuse the people directory and existing curation permission. Store explicit photo-level evidence in SQLite separately from indexed tags and album-level links.

**Dependencies:** MVP 19A gallery, existing person IDs and aliases, and a migration with stable indexed photo identity. Preserve decisions for unchanged indexed paths across reindexing and define what happens when a photo is replaced.

**Acceptance:** Link Ana to the album and tag only two of three synthetic photos with Ana. The photo-level filter returns exactly those two while album search still finds the album. Correct one link, reindex and verify the remaining decision and its origin. A non-curator cannot edit. No metadata is written to image files.

**Progress:** The application service and local HTTP API support curator-only photo edits, SQLite provenance, and paged search by confirmed person. Full and incremental scans preserve decisions for unchanged indexed photos. The Android gallery supports explicit selection and long press, with one atomic batch of additions or removals per page. **Buscar → Fotos por persona** uses the confirmed-photo endpoint. The phone interaction test is still pending.

**Photo review trial:** With thumbnails enabled, **Revisar foto a foto** lets a curator choose one existing person and review the current gallery page. The right gesture marks the visible photo and the left gesture skips it for this pass. Buttons offer both actions, and **Deshacer** revisits the last decision. **Guardar** sends a single batch for the newly marked photos. This trial uses people only and requires a visible preview before marking a photo. Keep manual tags in the batch editor. Compare the two flows on the same small synthetic album on a phone, measuring time and incorrect selections.

**Interaction test:** Provide an explicit **Seleccionar** action and a long-press shortcut. Keep the number selected and the **Etiquetar** action visible while browsing a page. Preview proposed people or tags before saving only to the selected photos. After validating the gallery flow, test opening a search result directly in this mode with its album context. Verify that Back cancels selection without writing and that the normal tap still opens a photo.

### MVP 19C — Index and People Tools

**Case:** The owner has added folders to the NAS and wants to update the catalogue and check the result from the app.

**Scope:** Add **Herramientas → Índice** for last run, status and **Buscar carpetas nuevas**, a background incremental scan. Reserve the trigger for an owner credential, share a single scan lock with scheduled scans, and reuse the existing scanner and run history. Give the owner a place to inspect database readiness and reach existing backup and verification tools. Keep initial NAS setup and destructive recovery in the existing CLI. Group the directory, aliases and corrections under **Personas**, with the current role checks.

**Dependencies:** Existing incremental scanner, run summaries, backup commands and owner authorization. The app must never pass arbitrary commands or filesystem locations to the server.

**Acceptance:** Add a synthetic folder, start an incremental scan from the owner UI and confirm only one run starts under concurrent requests. See its status and find the folder without opening any image. A family curator can tag albums, while the same credential is denied an index trigger. A failed scan preserves the last complete index and reports the failure.

**Progress:** The existing browser admin panel can request a background incremental scan and refresh its run history. The API checks the owner role and accepts no scan options. Scheduled and manual runs share the same lock beside SQLite. Synthetic HTTP tests cover role denial, contention with a separate process, successful discovery and failure with the previous index intact. Android owner tools and the physical phone interaction test remain pending.

### MVP 19D — Chat Search and Local Model Comparison

**Case:** A family member can ask «fotos de la playa con Ana antes de 2020» from the **Buscar** tab, inspect the filters and open the result in its folder.

**Scope:** Start with the existing Spanish rule interpreter, query refinement, and deterministic search. Keep the chat read-only and ask for clarification when a year or person is ambiguous. Compare the rules with one small locally run quantized text model through the existing command adapter. Try it on a development computer first, send only the query to the local process, validate structured output, and retain the rules as default and fallback. Keep OCR and image/text search as separate optional experiments from MVP 14.

**Dependencies:** Existing interpreter, refinement and search services. For the comparison only, a pinned GGUF model, model license and a local runtime such as [llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md). Set latency and memory budgets before considering the NAS.

**Acceptance:** On the same synthetic Spanish prompts, compare correct filters and clarification for both modes. Report latency, peak memory and model size. Cover aliases, compound dates, ambiguity, invalid model output and timeout. Enable the model only if it improves retrieval within the stated budget.

**Progress:** Android **Buscar** starts a regular album search and accepts follow-up messages through the existing private refinement API. It shows the active phrases and lets the user choose an album if the name is ambiguous. This first flow needs no model. The rules recognise Spanish album requests and explicit ranges such as “de 2018 a 2020” and “entre 2018 y 2020”. Unconnected years still prompt for clarification. The family browser shows refinements as removable person, year and album filters and refreshes the results with the remaining constraints. The album search API exposes the same controls for Android to adopt. Compare removal with starting over on a phone. The album search API accepts a Spanish request such as “fotos de la playa con Ana antes de 2020”. It resolves a name or alias to a curated album link, applies an exclusive year boundary, and preserves both constraints in follow-ups. A synthetic family API test covers the flow with the archive disconnected.

### MVP 19E — Face Review Trial

**Case:** The owner can prepare a small set of photos for review in **Personas → Caras** and confirm or correct suggested face-to-person links.

**Scope:** Separate detection of face regions, similarity suggestions, and confirmed identities. Test optional local processing of one small selected album, initially on a development computer. Record progress and source/model provenance so a run can resume and skip unchanged photos. Show suggested matches for approval or rejection and allow correction and deletion. Confirmed links refer to the exact photo. Keep face processing off by default and independent of indexing. Keep all derived face data local and define its deletion policy before persistence.

**Dependencies:** MVP 19B photo-level links, a bounded processing and cancellation path, and synthetic face fixtures. Compare [ML Kit face detection](https://developers.google.com/ml-kit/vision/face-detection) for Android-only detection with [OpenCV YuNet and SFace](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html) for a local detection and similarity trial. Verify model licenses, measure CPU, memory, per-photo time and storage, and calibrate on the trial data before adopting a threshold.

**Acceptance:** Process a bounded synthetic batch, interrupt and resume it, review a proposed match and reject an unknown or lookalike without creating a confirmed link. A wrong suggestion can be corrected and derived data can be removed. Reindexing alone never runs the model or alters originals.

### Optional remote MCP transport

**Case:** Query one explicitly granted album from a supported MCP client when that is materially easier than the family web.

**Scope:** Wrap the existing read-only tool core in an official, authenticated transport. Keep grants per album and revocable, expose no original-image tool by default, and leave the adapter disabled when unused.

**Dependencies:** A supported ChatGPT plan or another MCP host, Python 3.11+ for the current official Python SDK, and an explicit choice between public HTTPS and a Secure MCP Tunnel. OAuth or person-bound authentication must be designed before sharing beyond a single owner-controlled trial.

**Validation:** An official MCP client completes initialize, tool discovery, scoped list/search and live revocation against synthetic data; requests for another album, mutation and original bytes fail. Measure idle memory and request latency on representative NAS hardware before deployment.

### Optional visual curation

- Consider a local batch of suggested visual tags for otherwise unlabeled albums if there is a sufficiently varied evaluation set with Spanish paraphrases and wrong-attribute examples.
- Reuse the optional enrichment adapter and evaluate on a separate set before choosing a model or deploying it. Measure CPU and memory on the intended machine and check that the suggestions can be corrected.

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
