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
  database_backup.py   # create, verify, and restore SQLite backups
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
- `API_TOKEN` optionally, a shared read-only API token
- `API_CHAT_TOKENS` optionally, a JSON object mapping Telegram chat IDs to individual API tokens
- `API_CURATOR_CHAT_IDS` optionally, comma-separated authorized viewer chat IDs allowed to review albums in the browser
- `QUERY_INTERPRETER_COMMAND` optionally, a local executable and arguments for query interpretation
- `QUERY_INTERPRETER_TIMEOUT` optionally, adapter timeout in seconds, default `10`
- `ENRICHMENT_SEARCH` optionally, set to `true` to match optional image captions, OCR, and object tags
- `LOG_LEVEL` optionally, for example `DEBUG` or `INFO`

Use `SOURCE_TYPE=ftp` with an absolute FTP `SOURCE_ROOT` such as `/photos/archive`.
Use `SOURCE_TYPE=local` with either an absolute local path or a repo-relative path such as `tests/fixtures/ftp_tree/server_root/photos/archive`.
Set `LOG_LEVEL=DEBUG` to see scan, search, and Telegram command logs during execution.

## NAS setup

From a checkout on the NAS, run:

```bash
bash scripts/setup_nas.sh
```

For a new deployment, the script asks for the local archive root when `CHROMANTIS_PHOTOS` is unset. The root is the directory that contains the per-year folders. It asks for the bot token with hidden input, verifies the bot, then prints a Telegram deep link to enroll your private chat. If you already know your chat ID, pass `CHROMANTIS_OWNER_CHAT_ID` to skip enrollment. It stores the bot token and a separate, generated browser token in `.env` with mode `0600`. The API binds to loopback by default.

The script uses Python 3.10 or newer. On older NAS systems, it uses `uv` to install Python 3.12 for the current account. An existing compatible environment and configured archive are reused. Setup performs an incremental index and starts the API and bot together in the terminal.

```bash
# Use existing configuration and skip installation and indexing.
bash scripts/setup_nas.sh --start-only

# Set up and index without starting the services.
bash scripts/setup_nas.sh --setup-only

# Replace the Telegram token and restart from the same checkout.
bash scripts/setup_nas.sh --rotate-token
```

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

Install the Telegram adapter and run the test suite:

```bash
python -m pip install ".[telegram]"
python -m unittest discover -s tests -v
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
- `/recent`
- `/pinned`
- `/invite [viewer|admin] [days]`
- `/invite list`
- `/invite revoke <code>`
- `/authorized`
- `/authorized role <chat-id> <viewer|admin|owner>`
- `/authorized revoke <chat-id>`
- `/whoami`
- `/stats`
- `/settings`
- `/login <access-code>`
- `/logout`

The bot reads results from SQLite and fetches image bytes from the configured source on demand for photo replies.
If the bot starts with an empty index, it prints a warning at startup and `/stats` will show `0` indexed images.
Search now supports exact years, inclusive ranges like `2019-2021`, and curated people aliases inside `/folders`, `/images`, and `/random`.
Authorized users can also send plain-language text like `show me 3 city photos from 2021`; Chromantis rewrites that into the existing deterministic search flow.
The bot now asks for a preferred language on first `/start`, stores that preference per chat in SQLite, and localizes onboarding, help, examples, button labels, and settings in English or Spanish.
The first response after language selection or successful login is intentionally instructional: it explains what the bot can search, how to get better matches, and shows concrete example requests for non-technical users.
The rule-based interpreter now understands common Spanish request framing as well, so users can ask in English or Spanish while still relying on archive words, years, and curated people names for actual retrieval.
You can ask for multiple photos in one command, and `/more` continues from the current image batch or scope in that chat.
When a photo batch spans several folders, the bot now says so explicitly and offers a `Folders` button so users can continue inside one folder without assuming the whole batch came from the same place.
Image replies include inline buttons for continuing the current search, switching to the same folder or year when that context is singular, getting random similar images, refining the search, and going back.
Active browse state is stored per chat in SQLite, so `/more` and the navigation buttons survive bot restarts.

Open **People** to browse person details. **Photos from linked albums** starts a photo search limited to that person's linked albums. Admins and owners can add people, change names, add aliases, and link or unlink folders from the person’s buttons. Linking prompts for a folder name, year, or keyword and shows the matching folders. The `/people` commands remain available.

Open **Recent searches** or use `/recent` to rerun or pin a query. Open **Pinned searches** or use `/pinned` to revisit or unpin favorites. Both buttons are on the Telegram home menu. Searches are private to the chat and stored in SQLite. Natural-language prompts with multiple separate years ask for one year or an inclusive range.

## Bot security

By default, `run_bot.py` now prints a 6-digit access code at startup. A new Telegram chat must send:

```text
/login 123456
```

to become authorized as a `viewer`. Authorized chats are stored in SQLite and survive bot restarts.
Owners and admins can generate short-lived viewer invites with `/invite viewer`, and owners can generate admin invites with `/invite admin 3`. Active admin invite codes are visible only to owners.

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

For normal users, the easiest flow is now:

1. Send `/start`
2. Choose `English` or `Español`
3. If needed, send `/login <access-code>`
4. Follow the onboarding examples or use the buttons
5. Use `/settings` later if you want to change the language for that chat

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

Use `Authorization: Bearer <token>` or `X-API-Token: <token>`. If either token setting is configured, the API requires a token except on `/api/v1/health`. `API_TOKEN` keeps its existing read-only access to search. Chat tokens use the current Telegram role and stop working while their chat is unauthorized.

To configure an owner token, set `TELEGRAM_ADMIN_CHAT_ALLOWLIST` to the owner chat ID and put a separate token for that ID in `API_CHAT_TOKENS`. Generate one token per chat with `python -c 'import secrets; print(secrets.token_urlsafe(32))'` and restart the API after changing the configuration.

```dotenv
TELEGRAM_ADMIN_CHAT_ALLOWLIST=123456789
API_CHAT_TOKENS={"123456789":"replace-with-generated-token"}
```

| Method and path | JSON input | Success response | Access |
| --- | --- | --- | --- |
| `GET /api/v1/auth/me` | | `{"item": principal}` | Any authorized chat token |
| `GET /api/v1/admin/chats` | | `{"items": [principal]}` | Admin or owner |
| `PATCH /api/v1/admin/chats/{chat_id}` | `{"role":"viewer"}` | `{"item": principal}` | Owner, dynamic chats |
| `DELETE /api/v1/admin/chats/{chat_id}` | | `{"revoked":true}` | Admin for viewers, owner for any dynamic chat |
| `GET /api/v1/admin/invites` | | `{"items": [invite]}` | Admin for active viewer invites, owner for all active invites |
| `POST /api/v1/admin/invites` | `{"role":"viewer","ttl_days":7}` | `201 {"item": invite}` | Admin for viewer invitations, owner for admin invitations |
| `DELETE /api/v1/admin/invites/{code}` | | `{"item": invite}` | Admin for viewer invitations, owner for admin invitations |

A principal contains `chat_id`, `role`, `username`, `first_name`, and `auth_mode` (`static_owner`, `static_viewer`, or `dynamic`). An invite contains `code`, `role`, `created_by_chat_id`, `max_uses`, `used_count`, `expires_at`, `revoked_at`, and `created_at`. New invites have one use. TTL defaults to seven days and accepts 1–30 days. Errors contain `error`, with `code` for role and state errors. Role changes, chat revocations, and invite changes are recorded with the acting chat ID.

### Query and browse API

| Method and path | Request | Success response |
| --- | --- | --- |
| `GET /api/v1/people/{id}` | Numeric ID from the people list | `{"item": person}` |
| `POST /api/v1/interpret` | `{"text":"show me 3 beach photos from 2021"}` | `{"item":{"action":"images","query":"beach 2021","count":3,"needs_clarification":false}}` |
| `GET /api/v1/image` | URL-encoded `?path=<indexed-image-path>` | Original image bytes |
| `GET /api/v1/browse` | Chat token | Active browse batch |
| `POST /api/v1/browse` | Chat token and `{"action":"search","q":"beach 2021","count":3}` | Updated browse batch |
| `GET /api/v1/searches` | Chat token, optional `pinned=true`, `limit`, and `offset` | `{"items": [search]}` |
| `PATCH /api/v1/searches/{id}` | Chat token and `{"pinned":true}` | `{"item": search}` |

A person detail has `id`, `display_name`, `aliases`, and `folder_paths`. Browse batches have `items`, `scope`, `q`, `count`, `folders`, `years`, and `can_go_back`. Each image result includes its indexed path, title, year, folder, and match reason. Stats also expose a single-object `item` envelope alongside their original top-level fields. List endpoints return an `items` array.

Browse actions are `search`, `random`, `more`, `open_folder`, `open_year`, `same_folder`, `same_year`, `related`, and `back`. `q` is optional for `search` and `random`. An optional `count` accepts 1–50. When a batch spans several folders or years, supply `folder` and/or `year` to select the context for `same_folder`, `same_year`, or `related`. A missing context returns 409. Use `open_folder` with `folder` or `open_year` with `year` to start a fresh batch in that context. Exhausted continuations return an empty `items` array and keep the last available batch. Sessions persist in SQLite per chat and are independent of Telegram browse history. Recent and pinned searches are shared across API and Telegram for the same chat. A search entry contains `id`, `kind`, `query`, `count`, `searched_at`, and `pinned`.

Admins and owners can curate people with these routes. Each successful write returns the updated person as `{"item": person}`.

| Method and path | Data |
| --- | --- |
| `POST /api/v1/admin/people` | `{"display_name":"Ana"}` |
| `PATCH /api/v1/admin/people/{id}` | `{"display_name":"Anita"}` |
| `POST /api/v1/admin/people/{id}/aliases` | `{"alias":"Anni"}` |
| `POST /api/v1/admin/people/{id}/folders` | `{"path":"2021/2021-08-15_city_trip"}` |
| `DELETE /api/v1/admin/people/{id}/folders` | URL-encoded `?path=<folder-path>` |

### Optional model interpreter

The API and Telegram use the rule interpreter by default. To use a local model, configure an adapter command in `.env`, such as `QUERY_INTERPRETER_COMMAND=/opt/chromantis/bin/model-adapter`, and restart both clients. The executable receives one UTF-8 JSON object on stdin and must write one JSON object to stdout. Keep diagnostics on stderr.

| Direction | Example |
| --- | --- |
| Stdin | `{"text":"Find a couple of city photos from 2021"}` |
| Stdout | `{"action":"images","query":"city 2021","count":2,"confidence":0.9}` |

Actions are `images`, `folders`, `random`, and `years`. Counts are 1–10 and confidence is 0–1. Confidence below 0.65 requests clarification. A timeout, an executable failure, or an invalid response falls back to the rules. The adapter receives the request text. The existing search engine applies the resulting query to the index.

An in-process adapter can implement `QueryInterpreter.interpret(text)` and be passed into `ApplicationService`. This is the extension point for future providers.

### Optional image enrichment

Run enrichment after indexing. The CLI reads only indexed photos from the configured archive and writes model output to a separate SQLite table with model, version, source metadata, and processing time. It skips photos already processed for that version, retries unsuccessful attempts after unprocessed photos, and ignores stale results when the indexed source metadata changes.

The included OCR adapter requires Tesseract and the selected language data on the machine. Start with a small batch.

```bash
python scripts/enrich_images.py \
  --command "python scripts/tesseract_enricher.py --language eng" \
  --model tesseract-eng --version "$(tesseract --version | head -n 1)" --limit 25
```

Add `--album "2024/2024-08-04_playa"` to restrict the batch to one exact indexed album path. Running the same command later resumes pending photos for that album and model version.

For captions or object tags, configure an image-model adapter with `--command`. Each invocation receives one original image on stdin as bytes and writes one UTF-8 JSON object to stdout. Return empty strings or an empty list for fields your model does not provide.

```json
{"caption":"A bicycle beside a blue wall","ocr_text":"BIKE SHOP","object_tags":["bicycle","wall"]}
```

Set `ENRICHMENT_SEARCH=true` and restart the API and bot to include these fields in image and random-image searches. Matches explain which terms used enrichment, and year and curated-person filters still apply. The default deployment continues to search indexed metadata without running a model.

#### Evaluate search with synthetic photos

With the optional Pillow extra installed, the following command builds a temporary archive and SQLite database, runs 13 labelled queries on nine synthetic images, and reports exact matches and recall in the top five, per-query misses, and median/p95 search latency. Add `--ocr` for a side-by-side comparison with the installed Tesseract and its English data. The command uses the generated archive and temporary database regardless of the local configuration.

```bash
python scripts/evaluate_search.py --ocr
```

In the initial comparison with Tesseract 5.5.0, the OCR build took about 1.8 seconds for nine images on the test machine. Exact results at five were:

| Query type | Indexed metadata | Metadata and OCR |
| --- | ---: | ---: |
| Album, person, place or date | 4/4 | 4/4 |
| Written text | 0/4 | 4/4 |
| Objects or scenes | 0/4 | 0/4 |
| Absent object | 1/1 | 1/1 |

The text cases include repeated signs in different albums and years. The timed search queries use the fields already indexed in SQLite. The build time measures running OCR, and the fixtures are small synthetic illustrations.

#### Local visual search trial

Run this experiment on a development computer with Pillow, NumPy, ONNX Runtime and Tokenizers. Place `tokenizer.json`, `onnx/vision_model_quantized.onnx` and `onnx/text_model_quantized.onnx` from the pinned model revision in one local directory, using the filenames without the `onnx/` prefix. The script verifies the checksums before loading. [Model files](https://huggingface.co/Xenova/clip-vit-base-patch32/tree/6ef1ebc8b0766a7a8d11b146462c99cdf74dd22d)

```bash
python scripts/evaluate_visual_search.py /path/to/local/model
```

The script compares ordinary search, tags from a small bilingual vocabulary, and similarity between images and query text. It uses the existing synthetic fixtures, adds a paraphrase, checks an explicit person and year together, and tests an incorrect colour and setting. It creates its own temporary index. The tag vocabulary is tailored to the illustrated concepts.

At the default similarity threshold of 0.28, the x86-64 trial produced these exact results:

| Query group | Indexed metadata | Vocabulary tags | Image/text similarity |
| --- | ---: | ---: | ---: |
| Original visual queries | 0/4 | 4/4 | 1/4 |
| Additional English query with person and year | 0/1 | 1/1 | 1/1 |
| New paraphrase | 0/1 | 0/1 | 1/1 |
| Wrong colour or setting correctly excluded | 2/2 | 2/2 | 0/2 |

The three approaches also kept all four metadata cases correct. The model files total about 149 MiB. In the measured development run with ONNX Runtime 1.32, the experiment peaked at about 275 MiB RSS. Building each set of experimental data took about 0.45 seconds for nine drawings. Median query latency was roughly 0.65 ms with stored tags and 4.4 ms with the similarity fallback, which computes the text vector at query time. The tag payload was 208 bytes and the in-memory vectors used 18 KiB, excluding storage overheads. Disk growth for tags happened to fit existing SQLite pages in this tiny run. These measurements describe the synthetic workload on x86-64. The script remains an offline experiment and the normal application has no model dependencies.

### Browser interface

Run `python scripts/run_api.py` and open `http://127.0.0.1:8787/`. The browser asks for the chat token configured in `API_CHAT_TOKENS` for an authorized Telegram chat.

When the process runs on a NAS and you are browsing from another computer, keep the API on its default loopback address and forward the port through SSH. Use the NAS's SSH port if it differs from the default.

```bash
ssh -N -L 8787:127.0.0.1:8787 user@nas
```

Open `http://127.0.0.1:8787/` on your computer while the tunnel is running. The browser app uses the same API for image previews, browsing, people, and saved searches. Admins can curate people, manage invites and authorized chats according to role, inspect deployment configuration and sync history, and change their Telegram language preference. Server-wide configuration is set in `.env`.

#### Etiquetar álbumes

Abre **Etiquetar álbumes**, busca a las personas por nombre o alias y pulsa **Guardar y siguiente**. Puedes quitar una persona de la selección, añadir otra, o saltar el álbum y volver a él desde **Pendientes**. Un vínculo indica que la persona aparece en alguna foto del álbum. Para corregirlo, abre **Ya revisados** o pulsa **Etiquetar este álbum** desde su galería.

El nombre de la carpeta genera sugerencias con un vocabulario corto de términos en español e inglés. Cada sugerencia muestra el término que coincidió. Puedes aceptar o rechazar las pendientes de una vez, corregir etiquetas por separado y añadir etiquetas manuales de una palabra. Si dejas alguna sugerencia sin decidir, el álbum vuelve a aparecer en la siguiente vuelta. La revisión se guarda en SQLite y se conserva al reindexar mientras se mantenga la ruta. Si se renombra o se mueve la carpeta, el índice la trata como un álbum nuevo. Los términos del nombre original siguen sirviendo para buscar aunque se rechace una sugerencia.

Abre **Por lotes** para agrupar los álbumes pendientes por una misma sugerencia. En cada grupo puedes aceptar la etiqueta para varios álbumes, rechazarla en otros y dejar los dudosos pendientes. **Revisar** abre el editor completo cuando necesites corregir la etiqueta, elegir personas o consultar fotos. Guardar un grupo es atómico: si uno de los álbumes cambió, no se aplica ninguna decisión hasta recargar. Este flujo usa solo nombres y SQLite y no solicita miniaturas ni originales.

La API equivalente usa `GET /api/v1/album-review/batch` y `POST /api/v1/album-review/batch`, acepta hasta 50 decisiones por envío y exige el permiso limitado de curación de álbumes.

El flujo de etiquetado funciona con el archivo desconectado. **Ver hasta 3 fotos** solicita los originales de forma puntual. El catálogo y la búsqueda siguen disponibles sin modelos ni dependencias nuevas.

Abre **Detalles del álbum** para añadir una nota y hasta ocho alias o corregir el título y la fecha. Los valores del índice aparecen encima del formulario. Borra el título o la fecha corregidos para volver a usar los originales. El año de la fecha corregida se usa en los filtros y la navegación por año. Al buscar por un alias o por el título corregido, el resultado indica qué coincidió. Puedes seguir buscando por el nombre original de la carpeta.

Para dar acceso de curación a un familiar, conserva su rol de lector y añade su ID autorizado a `API_CURATOR_CHAT_IDS` y un token propio en `API_CHAT_TOKENS`. Su navegador abrirá directamente **Etiquetar álbumes** al iniciar sesión. Reinicia la API después de editar `.env`. En una red doméstica de confianza puedes configurar `API_BIND_HOST` con la IP privada del NAS y abrir esa dirección y puerto desde el navegador. El valor por defecto es la interfaz local y el ejemplo anterior muestra el acceso por túnel SSH.

En Telegram, un administrador puede usar `/album <ruta>` para ver los detalles y `/album <ruta> | title | <título>` para editarlos. Usa `date` con el formato `AAAA-MM-DD`, `note` para la nota o `aliases` para sustituir la lista, con un alias por línea. Deja el valor vacío para borrarlo. La ruta es la que muestra `/folders`.

#### Lugares y cronología

En **Detalles del álbum**, puedes escribir o borrar el **Lugar del álbum**, por ejemplo *Cabo de Palos, Murcia*. Busca «Palos 2024» en álbumes o abre **Cronología de álbumes** para filtrar por lugar y fechas. La cronología ordena de más reciente a más antiguo y señala si cada fecha sale de la carpeta o de una corrección. Los álbumes sin fecha completa aparecen por año cuando dejas el intervalo vacío. El lugar describe el álbum en conjunto y se guarda como texto en SQLite, fuera de los originales.

En Telegram, `/album <ruta> | place | <lugar>` edita el lugar con permisos de administración. Cualquier lector autorizado puede consultar los seis primeros resultados de `/timeline 2024 | Cartagena` o `/timeline 2024-06-01..2024-08-31 | Cartagena`. La API local ofrece los mismos filtros en `GET /api/v1/folders` con `sort=timeline`, `place`, `date_from` y `date_to` (fechas inclusive). También acepta la consulta habitual `q` y la paginación con `offset` y `limit`.

#### Acotar una búsqueda

Busca **playa con Ana** y, en el mismo campo de la web, escribe **antes de 2020** para acotar los resultados que ya estás viendo. Los años se acumulan. También puedes escribir **solo 2019**, **después de 2016**, **con Ana** o **álbum Verano**. Al añadir una persona, se exige un vínculo con ese álbum en el directorio de Personas. Si varios álbumes coinciden con el nombre, elige uno. Escribe otra consulta para empezar una búsqueda nueva.

En Telegram puedes enviar la aclaración como mensaje posterior o usar `/refine antes de 2020`. Si el bot ofrece varios álbumes, responde con `/refine album <ruta>`. El bot usa la búsqueda de fotos o álbumes más reciente del chat. Puedes fijar la búsqueda refinada en el historial habitual. En la web familiar, la búsqueda actual se conserva mientras la página está abierta.

La API local acepta `POST /api/v1/refine` con `{"q":"playa con Ana","text":"antes de 2020"}`. Usa el `q` devuelto en la búsqueda de fotos o álbumes. Si hay varias opciones, el servidor devuelve `choices` en lugar de una consulta.

#### Colecciones privadas

En la web con tu sesión de propietario, pulsa **Add photo to collection** o **Add album to collection** desde el archivo. Elige una colección o selecciona **New collection** y ponle nombre. Vuelve a **Collections** para abrir una entrada, quitarla o borrar la colección. Cada propietario tiene sus propias colecciones, con un límite de 100 colecciones y 250 entradas en cada una.

SQLite guarda la ruta y la raíz indexada como referencia. Una entrada conserva su sitio en la colección si deja de estar en el índice y vuelve a estar disponible al indexar de nuevo la misma ruta y raíz. Quitar la entrada o borrar la colección solo cambia SQLite.

La API local admite `GET/POST /api/v1/collections`, `GET/DELETE /api/v1/collections/<id>`, `POST /api/v1/collections/<id>/entries` y `DELETE /api/v1/collections/<id>/entries/<entry-id>`. Al crear, envía `{"name":"Verano"}` y opcionalmente `entry`. Una entrada contiene `kind` (`folder` o `image`) y la `path` exacta del índice.

#### Compartir un álbum en privado

Con una sesión de propietario, busca un álbum en **Archivo** y pulsa **Compartir álbum**. La web muestra los enlaces activos de ese álbum y permite crear otro válido durante siete días. El enlace completo se enseña una sola vez: cópialo y envíalo en privado. Cualquier persona que lo tenga podrá ver ese álbum hasta que caduque o lo revoques.

El invitado abre una galería en español sin iniciar sesión. La cabecera muestra el título, la fecha, el lugar y la nota que se hayan guardado para el álbum. En móvil, la primera foto sirve de portada y el resto forma una cuadrícula compacta. Puede ver únicamente el contexto y las fotos indexadas del álbum concedido; no obtiene búsquedas, colecciones ni funciones de curación.

Chromantis comprueba la concesión de nuevo al cargar el álbum, cada original y cada miniatura, por lo que **Revocar** corta la siguiente petición. Si las miniaturas locales están activadas se cargan de forma diferida. Si están desactivadas, la galería muestra marcadores ligeros y no descarga originales automáticamente: el invitado debe pulsar **Abrir original** en la foto concreta.

SQLite guarda el hash del secreto, no el enlace reutilizable. La API ofrece `GET/POST /api/v1/album-shares` y `DELETE /api/v1/album-shares/<id>` solo a propietarios. La galería usa `GET /api/v1/shared/<secret>` y sus rutas `/image` y `/thumbnail`; esas tres rutas están limitadas por la misma concesión de álbum. Esta función no publica el NAS ni configura acceso externo: el enlace solo es alcanzable desde la red o túnel donde ya esté disponible Chromantis.

#### Acceso familiar sin Telegram

Con la API protegida por `API_CHAT_TOKENS` o `API_TOKEN`, el propietario puede crear un código para cada navegador desde la terminal del NAS:

```bash
cd /path/to/chromantis
.venv/bin/python scripts/family_access.py invite "Móvil de papá"
.venv/bin/python scripts/family_access.py list
.venv/bin/python scripts/family_access.py revoke 1
```

Comparte el código en privado. El familiar abre la dirección local de Chromantis, elige **Acceso familiar** y pega el código una sola vez en las 24 horas siguientes. La sesión dura hasta 90 días en ese navegador y abre **Etiquetar álbumes** al volver. El familiar puede buscar y etiquetar cualquier álbum del archivo. Para cancelar un acceso, usa el ID mostrado por `list`. Si el familiar cierra sesión o cambia de navegador, genera un código nuevo.

Usa la web en una red doméstica de confianza. Si sirves la web desde un proxy HTTPS local, conserva la cabecera `Host` del navegador para que la API pueda comprobar el origen y marcar la cookie como `Secure`.

#### Miniaturas para navegar desde el móvil

La caché es opcional. Para activarla, instala el extra local y configura el espacio reservado en `.env` antes de reiniciar la API:

```bash
.venv/bin/python -m pip install '.[telegram,thumbnails]'
```

```dotenv
THUMBNAIL_CACHE_MIB=64
```

La galería solicita miniaturas JPEG de hasta 480 píxeles al entrar cada foto en pantalla. En la primera visita, la API lee la foto desde el archivo para crearla. El navegador recibe el original al abrir la foto y puedes guardarlo con **Descargar original**. Si una imagen excede el límite de generación (32 MiB de entrada o 30 megapíxeles), sigue disponible el botón para abrir el original.

La carpeta `<nombre-de-la-base-de-datos>.thumbnails` queda junto al índice, fuera del archivo de fotos. La caché guarda hasta el presupuesto indicado de datos JPEG y un máximo de 2.048 archivos. Elimina primero los más antiguos. Cuando el siguiente reindexado detecta un cambio de tamaño o fecha de modificación, se genera otra miniatura al volver a verla. Las miniaturas guardadas pueden abrirse desde el navegador mientras la fuente esté desconectada. La web muestra la fecha del último índice correcto y avisa si la fuente falla al pedir una foto. El ajuste `0` deja disponibles las vistas originales y desactiva la generación de miniaturas.

#### Fechas de captura EXIF

Con Pillow instalado mediante el mismo extra de las miniaturas, puedes leer la fecha declarada por la cámara en los JPEG ya indexados. Ejecuta el comando manualmente y, si quieres probar con una sola carpeta, indica su ruta relativa exacta:

```bash
.venv/bin/python scripts/index_capture_dates.py --limit 25 --album "2024/2024-08-04_playa"
```

Omite `--album` para tomar el siguiente lote del índice. Se leen hasta 512 KiB de cada JPEG, sin decodificar píxeles. Se guarda el día de `DateTimeOriginal` cuando es válido. Las pasadas posteriores saltan los archivos ya procesados mientras su tamaño y fecha de modificación sigan siendo los mismos. Los errores de lectura quedan pendientes de reintento.

El visor y `GET /api/v1/image-dates?path=<ruta>` muestran por separado la fecha de captura, la del álbum y la de modificación del archivo. La fecha EXIF refleja el reloj declarado por la cámara. El proceso guarda solo el día y nunca lee el directorio GPS de EXIF. La fecha del álbum sigue guiando la navegación por año.

### Scheduled indexing and status

After the initial index, use incremental mode for routine updates.

```bash
python scripts/reindex_source.py --incremental --progress-every 500
```

Incremental mode lists archive metadata and updates only changed or new records. A missing timestamp or size causes that image to be reparsed. Missing images are removed only after a successful listing, and a late-running scan cannot overwrite a newer completed index. Run the full command without `--incremental` after changing parsing rules or when refreshing all derived metadata.

To schedule an incremental scan on a NAS with cron, add an entry with paths adjusted to the checkout. The example runs daily at 03:20 in the NAS's timezone.

```cron
20 3 * * * cd /path/to/chromantis && .venv/bin/python scripts/reindex_source.py --incremental >> /path/to/chromantis-sync.log 2>&1
```

Use `GET /api/v1/sync/runs?limit=10` to see start and finish times, run status, and counts of indexed, unchanged, skipped, and deleted items. It uses the same authentication as archive search. To process new or failed enrichment jobs, run or schedule `scripts/enrich_images.py` as a separate bounded batch.

### Backup and recovery

Back up the configured SQLite database to a new file. The command uses SQLite's online backup operation, so readers can remain connected and committed WAL changes are included.

```bash
mkdir -p backups
python scripts/database_backup.py create backups/chromantis-2026-11-16.sqlite
python scripts/database_backup.py verify backups/chromantis-2026-11-16.sqlite
```

Both commands print the byte size and SHA-256 digest. Store the backup somewhere separate from the NAS after copying it yourself. The backup contains the index and private curation, including people links, tags, album corrections, collections, access sessions and active album invitations. Treat it as private. It deliberately excludes `.env`, credentials, original photos and the regenerable thumbnail cache.

Recovery never overwrites an existing database. Restore into a new path, verify the result, then point `SQLITE_PATH` at it and restart Chromantis:

```bash
python scripts/database_backup.py \
  --database data/restored-chromantis.db \
  restore backups/chromantis-2026-11-16.sqlite

python scripts/database_backup.py \
  --database data/restored-chromantis.db \
  create backups/recovery-drill.sqlite
```

For a recovery drill, stop the bot and API only before switching `SQLITE_PATH`, keep the old database untouched, start against the restored path and check one corrected album and one private collection. The restore applies current schema migrations before publishing the new database file. Reindex afterward only if the archive root or its contents have changed. Creating, verifying and restoring a backup never opens the photo archive.

## Current v1 limits

- Incremental indexing still enumerates the configured subtree for reliable change and deletion detection
- Optional image enrichment covers captions, OCR, and object tags. Embeddings and EXIF are outside this pipeline.
- Optional model interpretation requires a configured adapter
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
