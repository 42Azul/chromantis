---
title: Telegram bot
description: Search in chat, browse people, and return to recent or pinned searches.
---

Run the bot as part of [NAS setup](../start/install.md#set-up-a-nas-with-telegram), or start it in its own terminal with `.venv/bin/python scripts/run_bot.py`.

1. Send `/start` and choose a language. You can change it later with `/settings`.
2. If prompted, sign in with the current access code. The bot prints a six-digit viewer code at startup unless `TELEGRAM_ACCESS_CODE` is configured. An owner or admin can issue a short-lived viewer invite instead.
3. Try `show me 3 city photos from 2021`, `/folders 2021-2023`, or **People**.

| To | Use |
| --- | --- |
| List indexed years and albums | `/years [YYYY-YYYY]`, `/folders <query>` |
| See photos | `/images [count] <query>`, `/random [count] [query]`, `/more [count]` |
| Narrow the latest search | `/refine before 2020` or a follow-up message. If asked to choose, use `/refine album <path>`. |
| Browse linked albums and people | `/people`, `/people show <name-or-alias>` |
| Reuse a search | **Recent searches**, **Pinned searches**, `/recent`, `/pinned` |
| Browse a timeline | `/timeline 2024 \| Cartagena` or `/timeline 2024-06-01..2024-08-31 \| Cartagena` |
| Inspect the running bot and index | `/whoami`, `/stats`, `/help` |

Photo batches identify mixed folders and offer a **Folders** button for choosing one. Browse progress and search history persist per chat across restarts. People cards can show photos from linked albums. The result reason `album_person="Name"` describes album-level evidence.

## Owner and admin commands

```text
/people add <display-name>
/people alias <canonical> | <alias>
/people rename <canonical> | <new-display-name>
/people link <canonical> | <folder-path>
/people unlink <canonical> | <folder-path>
/album <path> | title | <new title>
/invite [viewer|admin] [days]
/invite list
/invite revoke <code>
/authorized
/authorized role <chat-id> <viewer|admin|owner>
/authorized revoke <chat-id>
```

Person cards offer buttons for the same curation actions. Use the exact album path shown by `/folders`. For `/album`, omit the field to view details or use `date` (YYYY-MM-DD), `note`, `place`, or `aliases` (one per line). An empty value clears the field.

Viewers search and browse. Admins curate people and manage viewer access. Owners also manage admins and change dynamic chat roles. Static viewers and owners come from the configured allowlists. Their access is managed in configuration. Dynamic viewers can leave with `/logout`.

Telegram sends requested photo replies through Telegram. Use the [local browser](./family.md) for family browsing on your own network.
