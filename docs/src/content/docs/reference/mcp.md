---
title: Read-only MCP trial
description: Evaluate album-scoped MCP tools with SQLite and a synthetic archive.
---

Chromantis now has a transport-neutral MCP tool core for evaluating album-scoped retrieval without exposing the NAS or adding a permanent model process.

## Scope and privacy boundary

- `chromantis_list_album` returns the granted album's curated metadata and bounded indexed filenames.
- `chromantis_search_album` searches only that metadata and those filenames.
- The principal is an existing revocable, expiring album-share capability. Its hash remains in SQLite and its validity is checked again for every tool call.
- Tool arguments cannot choose an album. The grant fixes the only visible album.
- There are no mutation, thumbnail or original-image tools. Returned photo records omit archive paths and URLs.
- The trial reads SQLite only and remains usable while the archive is disconnected.

The core deliberately has no network listener and adds no dependency. It exposes MCP-compatible tool definitions and structured tool results so a later transport can wrap it without moving authorization or query logic out of `app/`.

## Transport decision

This trial exposes no MCP endpoint. Before adding a transport, check the official client connection requirements and the Python compatibility of the selected SDK version.

For that reason this trial does not publish an endpoint, install the SDK, enable a tunnel or implement OAuth. A remote connection remains a separate opt-in decision involving availability, authentication, privacy, NAS cost and whether a household use case justifies it.

Official references:

- [Connecting custom MCP servers in ChatGPT](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt)
- [Official MCP Python SDK](https://py.sdk.modelcontextprotocol.io/v2/)

## Reproduce the trial

```bash
python -m unittest tests.test_mcp_readonly -v
```

The fixture creates two synthetic albums, grants only one, disconnects the archive, lists and searches the granted album, proves that the other album is not returned, rejects a write-like tool and then verifies live revocation.
