---
title: Local API
description: Authentication, search, album review, and photo tagging endpoints.
---

The browser, bot, and Android client share the application service. Use this HTTP API from a trusted local client.

Available read-only endpoints:

- `GET /api/v1/health`
- `GET /api/v1/stats`
- `GET /api/v1/years?from=2019&to=2021`
- `GET /api/v1/folders?q=city&limit=10`
- `GET /api/v1/images?q=city&limit=10`
- `GET /api/v1/album-images?path=<indexed-album-path>&limit=30&offset=0`
- `GET /api/v1/random?q=city&count=3`
- `GET /api/v1/people`

Use `Authorization: Bearer <token>` or `X-API-Token: <token>`. If either token setting is configured, the API requires a token except on `/api/v1/health`. `API_TOKEN` keeps its existing read-only access to search. Chat tokens use the current Telegram role and stop working while their chat is unauthorized.

Family sessions can use `/api/v1/years`, `/api/v1/folders` and `/api/v1/album-images` to browse the index. The album-images route takes the exact, URL-encoded path returned by folder search and returns `{"items": [...], "next_offset": ...}` in file-path order. The page size is capped at 50, and `next_offset` is null on the last page. These requests read SQLite metadata only. A client can request thumbnails separately when needed.

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

## Query and browse API

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

## Manual photo tagging API

| Method and path | Request | Access |
| --- | --- | --- |
| `GET /api/v1/photo-tags` | Repeat the URL-encoded `path` parameter for 1–50 indexed photos | Existing album curators |
| `PATCH /api/v1/photo-tags` | Photo identities and a shared set of changes | Existing album curators |
| `GET /api/v1/confirmed-images` | `person` (name or alias) or `person_id`, and/or `tag` (exact manual photo tag), plus optional `limit` and `offset` | Search readers and active family sessions |

The tagging routes return `{"items": [...]}` in selection order. Each item has `path`, `identity`, `people` entries with `person_id` and `origin`, and `manual_tags` entries with `tag` and `origin`. Use existing person IDs from `GET /api/v1/album-review/people`. Use each `path` from the gallery and copy its `identity` from the tagging response when saving.

```json
{
  "photos": [
    {"path": "2024/2024-03-16_picnic/synthetic.jpg", "identity": "0123456789abcdef0123456789abcdef"}
  ],
  "add_people": [7],
  "remove_people": [],
  "manual_add": ["family"],
  "manual_remove": []
}
```

Edits apply atomically to the selection and can be retried. The existing 16 KiB request body limit returns 413 for larger payloads. Clients can split long selections into smaller requests, each saved atomically. A missing or changed photo during a save returns 409 so the client can reload the selection. Tags follow the album tagging rule of one word up to 40 letters. Actual additions and removals use the existing audit log with manual origin and the acting chat or family session. Ordinary readers can search. Reading or editing the tagging selection requires curation permission. Family-session writes use the same-origin JSON request used by album curation.

Confirmed image search returns `{"items": [...], "next_offset": ...}` for explicit photo links or manual photo tags, with a default page size of 30 and a maximum of 50. A missing person or tag gives an empty result. The `tag` parameter uses the same one-word rule and normalization as manual photo tagging. Album and indexed tags are outside this filter. Existing person searches in `/api/v1/folders` and `/api/v1/images` still use album links and their existing text matching. Manual photo tags can also match image keywords in `/api/v1/images`.

An indexed photo keeps its identity and decisions across scans while its path, configured root, size and modification time stay the same. If the archive listing omits size or modification time, the index retains the last known values for identity checks. A conflicting comparable value, removal, or a root change clears its active decisions. A replacement with identical observed metadata shares the previous identity. Curation and search use SQLite metadata, and indexing opens no originals for this feature.

Run the synthetic regression suite with `python -m unittest tests.test_photo_tags -v`.

Combine `person=Ana&tag=romeria` to require both confirmed evidence and the manual tag on the same photo. A person linked only to the album does not satisfy this query.

## Album review, sharing, and maintenance

| Method and path | Purpose |
| --- | --- |
| `GET /api/v1/album-review` | Next pending album by `after` ID or a specific indexed `path` |
| `GET /api/v1/album-review/people` | People directory for curators, including aliases |
| `GET /api/v1/album-review/photos` | Up to three indexed photos for an exact album path |
| `POST /api/v1/album-review` | Save album changes against its current revision |
| `GET/POST /api/v1/album-review/batch` | Review repeated suggestions and save up to 50 decisions atomically |
| `GET/POST /api/v1/album-shares` | List or create grants as owner |
| `DELETE /api/v1/album-shares/{id}` | Revoke a grant as owner |
| `GET /api/v1/shared/{secret}` | View the granted album; its `/image` and `/thumbnail` routes are scoped to it |
| `GET /api/v1/sync/runs?limit=10` | Recent index runs and item counts |
| `POST /api/v1/sync/runs` | Start a background incremental scan as owner |
| `GET /api/v1/archive-status` | Latest successful index and thumbnail status |
| `GET /api/v1/image-dates?path=<indexed-image-path>` | Distinct album, camera, and file dates |

Start a scan with an empty request body or `{}` and an owner token. A `202` response returns the new run ID in `item.id`. Read its status in the run history. An active scan returns `409`. The source and index location come from the server configuration.

`GET /api/v1/folders` accepts `sort=timeline`, `place`, `date_from`, and `date_to` alongside the usual `q`, `offset`, and `limit`. Date bounds are inclusive. `POST /api/v1/refine` takes `{"q":"beach","text":"before 2020"}` and returns a refined query or choices when the request is ambiguous.

For a combined Spanish request, set `q` to `fotos de la playa con Ana antes de 2020`. The year is exclusive, and the person must be linked to the album. Use the original `q` for refinements. An unknown name or alias returns 400 with `code: person`. Person lists such as `Ana y Luis` or `Ana, Luis` resolve all names or reject the request with `code: person`; all resolved people must have album links. A complete saved alias takes precedence over separators. The same syntax works in a `with`/`con` refinement.

Add `filters=1` to `GET /api/v1/folders` to receive `filters.q` (the query for follow-ups), `filters.text` (search text) and `filters.active`. Each active filter reports its `kind`, `label`, and the next `q` to use if removed (`without`). This lists the explicit refinements and the person and year from a combined request.

Owner collections use `GET/POST /api/v1/collections`, `GET/DELETE /api/v1/collections/{id}`, `POST /api/v1/collections/{id}/entries`, and `DELETE /api/v1/collections/{id}/entries/{entry-id}`. Creation accepts a `name` and optional `entry`. Each entry contains `kind` (`folder` or `image`) and its exact indexed `path`.
