# Chromantis

> A searchable visual memory over FTP photo folders, designed to evolve from deterministic indexing into LLM-assisted retrieval through chat.

Chromantis is a deterministic MVP that scans a configured photo archive source, parses metadata from folder paths, stores the result in SQLite, and exposes search-oriented Telegram commands.

For product vision and roadmap, see [PLANNING.md](PLANNING.md).

## Current structure

```text
src/chromantis/
  app/                # shared application/query service and rule-based interpreter
  api/                # local HTTP API on top of the application service
  config.py            # env loading and source-root validation
  db/                  # SQLite schema and repository
  source/              # archive source adapters and generic scanner
  ftp/                 # compatibility wrappers around the generic source layer
  parsing/             # path parsing and deterministic tagging
  search/              # query parsing and local search service
  bot/                 # Telegram command service and adapter
scripts/
  init_db.py           # create the SQLite schema
  reindex_source.py    # scan the configured source and index photos
  reindex_ftp.py       # compatibility wrapper for reindex_source.py
  run_api.py           # start the local HTTP query API
  run_bot.py           # start the Telegram bot
tests/
  fixtures/ftp_tree/   # local fake FTP tree
  test_*.py            # parser, scanner, search, bot, config tests
```

## How it works

Chromantis indexes only the configured `SOURCE_ROOT`. The active source can be either an FTP subtree or a local folder, but the indexed records are always relative to that configured root.
Archive access is read-only in both modes: Chromantis only lists directories and reads file bytes, and local-mode reads are confined to the configured root.

Expected relative path shape:

```text
/YYYY/folder-name/image.jpg
```

Derived metadata:

- `year`
- optional `event_date` when the folder starts with `YYYY-MM-DD`
- normalized folder title and slug
- deterministic tags from folder tokens
- rule tags such as season and `YYYY-MM`

Search is intentionally deterministic: year matching, title keyword matching, tag matching, curated person aliases, and random selection from filtered results.
Traversal is intentionally limited to `SOURCE_ROOT/year/folder/image`; deeper nested directories are ignored.

## Configuration

Copy `.env.example` to `.env` and set:

- `SOURCE_TYPE` as `ftp` or `local`
- `SOURCE_ROOT`
- `FTP_HOST`
- `FTP_PORT`
- `FTP_USER`
- `FTP_PASSWORD`
- `SQLITE_PATH`
- `TELEGRAM_TOKEN` optionally
- `TELEGRAM_CHAT_ALLOWLIST` optionally, comma-separated chat IDs
- `TELEGRAM_ADMIN_CHAT_ALLOWLIST` optionally, comma-separated admin chat IDs
- `TELEGRAM_ACCESS_CODE` optionally, a stable bot login code
- `API_BIND_HOST` optionally, defaults to `127.0.0.1`
- `API_PORT` optionally, defaults to `8787`
- `API_TOKEN` optionally, required for HTTP API access when set
- `LOG_LEVEL` optionally, for example `DEBUG` or `INFO`

Use `SOURCE_TYPE=ftp` with an absolute FTP `SOURCE_ROOT` such as `/photos/archive`.
Use `SOURCE_TYPE=local` with either an absolute local path or a repo-relative path such as `tests/fixtures/ftp_tree/server_root/photos/archive`.
Set `LOG_LEVEL=DEBUG` to see scan, search, and Telegram command logs during execution.

## Quick start

Initialize the SQLite schema:

```bash
python scripts/init_db.py
```

Run a full source reindex:

```bash
python scripts/reindex_source.py
```

Run a more inspectable first index:

```bash
python scripts/reindex_source.py --verbose --progress-every 1 --show-skipped
```

Useful flags:

- `--verbose`: enables per-file debug logs
- `--progress-every N`: prints progress every `N` processed FTP entries
- `--show-skipped`: prints invalid or skipped image paths at the end

Run tests:

```bash
python -m unittest discover -s tests -v
```

Install the optional Telegram adapter dependency:

```bash
pip install ".[telegram]"
```

Start the Telegram bot:

```bash
python scripts/run_bot.py
```

Start the local HTTP API:

```bash
python scripts/run_api.py
```

Recommended first run order:

```bash
python scripts/init_db.py
python scripts/reindex_source.py --verbose --progress-every 1 --show-skipped
python scripts/run_api.py
python scripts/run_bot.py
```

## Current commands

- `/years`
- `/years <YYYY-YYYY>`
- `/folders <query>`
- `/images [count] <query>`
- `/random [count] [query]`
- `/more [count]`
- `/people`
- `/people show <name-or-alias>`
- `/people add <display-name>`
- `/people alias <canonical> | <alias>`
- `/people rename <canonical> | <new-display-name>`
- `/people link <canonical> | <folder-path>`
- `/people unlink <canonical> | <folder-path>`
- `/invite [viewer|admin] [days]`
- `/invite list`
- `/invite revoke <code>`
- `/authorized`
- `/authorized role <chat-id> <viewer|admin|owner>`
- `/authorized revoke <chat-id>`
- `/whoami`
- `/stats`
- `/login <access-code>`
- `/logout`

The bot reads results from SQLite and fetches image bytes from the configured source on demand for photo replies.
If the bot starts with an empty index, it prints a warning at startup and `/stats` will show `0` indexed images.
Search now supports exact years, inclusive ranges like `2019-2021`, and curated people aliases inside `/folders`, `/images`, and `/random`.
Authorized users can also send plain-language text like `show me 3 city photos from 2021`; Chromantis rewrites that into the existing deterministic search flow.
You can ask for multiple photos in one command, and `/more` continues from the current image batch or scope in that chat.
When a photo batch spans several folders, the bot now says so explicitly and offers a `Folders` button so users can continue inside one folder without assuming the whole batch came from the same place.
Image replies include inline buttons for continuing the current search, switching to the same folder or year when that context is singular, getting random similar images, refining the search, and going back.
Active browse state is stored per chat in SQLite, so `/more` and the navigation buttons survive bot restarts.

## Bot security

By default, `run_bot.py` now prints a 6-digit access code at startup. A new Telegram chat must send:

```text
/login 123456
```

to become authorized as a `viewer`. Authorized chats are stored in SQLite and survive bot restarts.
Owners and admins can generate short-lived viewer invites with `/invite viewer`, and owners can generate admin invites with `/invite admin 3`.

If you want a stable code instead of a generated one, set:

```env
TELEGRAM_ACCESS_CODE=123456
```

Chromantis now uses explicit roles:

- `viewer`: search, browse, and plain-text retrieval only
- `admin`: viewer access plus people curation, invite listing, viewer invites, and viewer access revocation
- `owner`: admin access plus admin invites, role changes, and admin revocation

If you prefer fixed viewer chat IDs, keep using `TELEGRAM_CHAT_ALLOWLIST`. Those chats are treated as static viewers, always authorized, and cannot be role-changed or logged out from Telegram.

If you set `TELEGRAM_ADMIN_CHAT_ALLOWLIST`, those chats are treated as static owners. They always stay authorized and cannot be role-changed or logged out from Telegram. If you leave it empty, owner-only actions stay unavailable until a static owner is configured.

Useful admin flows:

- `/invite list`: list active invites with role, expiry, and usage
- `/invite revoke <code>`: revoke an active invite
- `/authorized`: list effective authorized chats and auth modes
- `/authorized role <chat-id> <viewer|admin|owner>`: change a dynamic chat role, owner only
- `/authorized revoke <chat-id>`: revoke a dynamic chat, admin for viewers and owner for admins

## Local API

Chromantis now exposes the same search/browse layer through a small local HTTP API. The API is meant for trusted local use and future UI work, not internet exposure.

Available read-only endpoints:

- `GET /api/v1/health`
- `GET /api/v1/stats`
- `GET /api/v1/years?from=2019&to=2021`
- `GET /api/v1/folders?q=city&limit=10`
- `GET /api/v1/images?q=city&limit=10`
- `GET /api/v1/random?q=city&count=3`
- `GET /api/v1/people`

If `API_TOKEN` is set, send it as `Authorization: Bearer <token>` or `X-API-Token: <token>`.

## Current v1 limits

- Full subtree scan only; no scheduler yet
- No embeddings, captions, EXIF, or OCR
- No model-based natural-language layer beyond the built-in rule interpreter
- Search behavior is simple, explainable, and deterministic

Early strategies:

* exact year filtering
* folder title substring matching
* normalized keyword match
* rule-based tag search
* simple ranking heuristic

Later strategies:

* semantic embedding search
* hybrid lexical + semantic search
* LLM query interpretation
* reranking

## 5. Telegram bot

Main user interface.

Potential commands:

* `/start`
* `/help`
* `/random`
* `/years`
* `/folders 2023`
* `/search christmas 2023`
* `/find cadiz`
* `/reindex`

Natural-language mode examples:

* "show me beach photos from 2022"
* "find the folder for graduation"
* "random dinner photo"

Outputs may include:

* image preview
* folder path
* year
* number of matches
* buttons for pagination or refinement

---

## Data model philosophy

The project should distinguish clearly between:

### Source facts

Things directly observed from FTP:

* path
* filename
* year folder
* timestamps
* file size

### Derived facts

Things inferred deterministically:

* normalized title
* split keywords
* parsed date from folder name
* slug cleanup

### Enriched facts

Things added later via AI or manual curation:

* captions
* objects detected
* OCR text
* people labels
* mood or event guesses
* semantic embeddings

This separation is important so the system remains explainable.

---

## Search modes roadmap

### Phase 1: rule-based retrieval

Search only by:

* year
* folder name
* deterministic tags
* basic filters

### Phase 2: curated enrichment

Allow manual tags or aliases such as:

* "xmas" -> christmas
* "mum" -> mother
* "cádiz" -> cadiz

### Phase 3: image understanding

Use models to derive:

* captions
* objects
* OCR text
* possible location hints

### Phase 4: semantic chatbot retrieval

Combine:

* lexical search
* metadata filters
* embeddings
* LLM-based query expansion
* conversational refinement

---

## Main technical challenges

## 1. Folder naming inconsistency

Folder names may not always follow the same structure.

Examples of problems:

* some folders have exact dates, some only year/month
* some use underscores, others spaces or hyphens
* some titles are vague
* some include duplicates or noise

Mitigation:

* build a robust normalization pipeline
* preserve raw source values
* add parsing confidence
* allow fallback to manual correction

## 2. FTP synchronization

FTP is not always ideal for incremental, reliable indexing.

Potential problems:

* weak metadata
* no event notifications
* slow recursive scans
* partial failures during traversal

Mitigation:

* maintain sync checkpoints
* store last seen timestamps / hashes
* support resumable scans
* design idempotent indexing

## 3. Ambiguous user queries

A user may ask for things using memory-like language, not exact folder names.

Example:

* "that trip with friends"
* "the beach one"
* "something from Christmas at grandma's"

Mitigation:

* start with constrained scope and known tags
* later add aliases, captions, and embeddings
* always return top matches with explanations

## 4. Image-level vs folder-level retrieval

Some requests refer to an event folder, others to a specific image.

Mitigation:

* index both folder entities and image entities
* decide result type based on query intent
* support "show folder" and "show image" separately

## 5. Performance and scale

Large archives can grow quickly.

Mitigation:

* incremental indexing
* lightweight DB first
* background enrichment jobs
* avoid expensive AI processing on every scan

## 6. Explainability

If results come from a chatbot, users need trust.

Mitigation:

* attach reason fields to matches
* show matched tags / year / title
* avoid opaque retrieval in early phases

## 7. Privacy and deployment

Personal image archives can be sensitive.

Mitigation:

* keep data local/self-hosted where possible
* avoid sending images externally unless explicitly enabled
* separate metadata indexing from optional AI calls

---

## Suggested milestones

## Milestone 1 — Static index MVP

Build the first useful version with no AI.

Deliverables:

* FTP scanner
* path parser
* SQLite schema
* indexer CLI
* simple search API / module
* Telegram bot with basic commands

Success criteria:

* can search by year
* can search by folder title keywords
* can return folder path and matching images
* can provide random image from filtered scope

## Milestone 2 — Incremental updates

Make the system practical for real use.

Deliverables:

* change detection
* reindex only changed files/folders
* index stats
* indexing logs
* bot/admin command to trigger sync

Success criteria:

* new folders appear after sync
* deleted files are marked or removed correctly
* indexing remains idempotent

## Milestone 3 — Better search quality

Improve retrieval without full AI complexity.

Deliverables:

* normalized aliases
* manual tags
* synonyms dictionary
* weighted search ranking
* better result formatting in Telegram

Success criteria:

* fuzzy but common user queries work better
* false positives decrease

## Milestone 4 — AI enrichment

Add optional intelligence.

Deliverables:

* image captioning pipeline
* embeddings for folders and/or images
* hybrid search
* reranking layer

Success criteria:

* vague natural-language queries become useful
* retrieval still remains inspectable

---

## Proposed repository structure

```text
chromantis/
├── README.md
├── docs/
│   ├── architecture.md
│   ├── data-model.md
│   ├── roadmap.md
│   └── query-examples.md
├── cmd/
│   ├── indexer/
│   └── bot/
├── internal/
│   ├── ftp/
│   ├── parser/
│   ├── db/
│   ├── search/
│   ├── tagging/
│   ├── sync/
│   └── telegram/
├── scripts/
├── configs/
├── data/
└── tests/
```

This can be adapted depending on language and stack.

---

## Candidate implementation approach

Since the project starts deterministic and operationally simple, a good first stack could be:

* **Language**: Go or Python
* **DB**: SQLite
* **Bot**: Telegram Bot API
* **Indexing**: scheduled CLI sync job
* **Search**: SQL + normalization + ranking code

Why this works well:

* simple to run locally
* easy to debug
* easy to evolve
* fast enough for MVP

If using Codex heavily, this project is a good fit for iterative generation of:

* parsers
* DB models
* migration files
* sync jobs
* Telegram handlers
* ranking logic
* tests
* docs

---

## Query examples

### Folder-oriented

* Find the folder for Cádiz trip
* Show folders from 2021 containing beach
* What Christmas folders do I have?

### Image-oriented

* Show 5 photos from 2023 Christmas
* Give me one random photo from summer 2020
* Find images from family dinners

### Browsing-oriented

* Which years contain birthday folders?
* How many folders do I have per year?
* List all folders from 2019

### Future semantic

* Show me old happy moments
* Find photos of sunsets
* That dinner with grandma

---

## Task backlog

## Foundation

* [ ] Define canonical folder and image schema
* [ ] Choose implementation language
* [ ] Create repository structure
* [ ] Add config loading
* [ ] Add logging

## FTP indexing

* [ ] Implement FTP connection module
* [ ] Recursively scan folders
* [ ] Filter supported image extensions
* [ ] Collect file metadata
* [ ] Persist raw discovered entities

## Parsing and normalization

* [ ] Parse year from root folder
* [ ] Parse event date from folder names when possible
* [ ] Normalize folder titles
* [ ] Extract deterministic tags from names
* [ ] Add confidence/fallback rules for malformed paths

## Database

* [ ] Design SQLite schema
* [ ] Add migrations
* [ ] Store folders and images
* [ ] Store tags and relationships
* [ ] Add indexing timestamps and sync state

## Search

* [ ] Implement year filtering
* [ ] Implement keyword search
* [ ] Implement tag-based retrieval
* [ ] Implement ranking function
* [ ] Return explainable match reasons

## Telegram bot

* [ ] Create bot skeleton
* [ ] Add `/search`
* [ ] Add `/random`
* [ ] Add `/years`
* [ ] Add `/folders`
* [ ] Return images and folder paths nicely

## Sync lifecycle

* [ ] Track new files
* [ ] Track deleted files
* [ ] Track changed folders
* [ ] Add reindex command
* [ ] Add dry-run mode

## Quality

* [ ] Add parser tests
* [ ] Add search ranking tests
* [ ] Add integration test with sample FTP tree
* [ ] Add fixture dataset

## Future AI enrichment

* [ ] Add image caption generation
* [ ] Add embedding generation
* [ ] Add semantic search
* [ ] Add manual feedback loop for better ranking
* [ ] Add hybrid retrieval strategy

---

## Non-goals for v1

To keep the project realistic, v1 should **not** try to solve everything.

Avoid in the first iteration:

* full knowledge graph complexity
* expensive multimodal pipelines
* face recognition
* perfect natural language understanding
* automatic event inference beyond simple rules
* distributed infrastructure

The right first step is a very solid metadata index plus a usable chatbot.

---

## What “knowledge graph” means here

At first, the term can be used loosely.

Chromantis does not need a graph database on day one. A relational DB with structured relationships is enough.

Example relationships already provide graph-like value:

* year -> folders
* folder -> images
* folder -> tags
* image -> tags
* future image -> caption / embedding / entities

If the project later needs richer relationship traversal, a graph model can be introduced. But starting with SQLite/Postgres is probably the correct tradeoff.

---

## Open design questions

* How strict is the actual folder naming convention in practice?
* Are there non-image files that should be ignored or also indexed?
* Should videos be included later?
* Is Telegram only for retrieval, or also for tagging / admin actions?
* Should results prioritize folders or images by default?
* How should random retrieval work: truly random, or random within relevant filtered scope?
* Do we want local-only inference later, or external AI APIs?

---

## Recommended first implementation plan

### Step 1

Build a tiny offline prototype:

* crawl a sample exported tree
* parse metadata
* save to SQLite
* run a few searches in CLI

### Step 2

Wrap the search in a Telegram bot:

* basic commands
* image/folder response formatting

### Step 3

Add incremental sync against FTP.

### Step 4

Add optional AI enrichments only after the deterministic base is solid.

---

## Vision statement

Chromantis aims to become a practical visual memory system: a layer that observes an archive of folders and photos, structures it into searchable knowledge, and lets a user retrieve memories through natural chat instead of manual browsing.

The first version should be boring, robust, and understandable.
The later versions can become smart.

That is the right order.

---

## For Codex

This repository is a good fit for iterative development with Codex.

Good tasks for Codex:

* generate DB schema and migrations
* implement folder parsing rules
* write normalization utilities
* create FTP traversal code
* scaffold Telegram bot handlers
* build search ranking functions
* write tests with sample datasets
* draft architecture docs

Recommended working style:

* keep tasks small and explicit
* preserve deterministic behavior first
* require tests for parser and search logic
* separate source facts from inferred/enriched data
* document assumptions about path structure clearly

---

## License

TBD
