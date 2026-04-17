# Chromantis Planning

> A searchable visual memory over FTP photo folders, designed to evolve from deterministic indexing into LLM-assisted retrieval through chat.

## Overview

Chromantis is a project to turn a large set of photo folders stored on an FTP server into a structured, searchable knowledge base that can be queried from a chatbot interface, starting with Telegram.

The source data is organized mostly like this:

```text
/year/folder-name-describing-content-with-date/photos...
```

Example:

```text
/2021/2021-08-15_trip_to_cadiz/IMG_001.jpg
/2021/2021-08-15_trip_to_cadiz/IMG_002.jpg
/2023/2023-12-24_christmas_family_dinner/DSC_1203.jpg
```

The long-term idea is inspired by the notion of a personal knowledge base that can be queried in natural language: a user sends a thought, memory, hint, question, or rough description to a bot, and the system returns the most relevant image, folder, year, or set of matches.

At first, the system should remain **simple, deterministic, and debuggable**:

* scan folders from FTP
* extract path-based metadata
* normalize names and dates
* store structured records in a local database
* support basic tagging and search
* expose a Telegram bot for retrieval

Later, the system can evolve into richer image understanding:

* automatic captions
* semantic embeddings
* visual similarity search
* face/event/location clustering
* LLM-assisted query rewriting and reasoning

---

## Goals

### Initial goal

Build a reliable index of all folders and images from FTP so that a chatbot can answer questions like:

* "Show me Christmas photos from 2023"
* "Find the folder for the Cádiz trip"
* "Photos from summer 2021"
* "Give me images from that dinner with family"
* "What folders exist for 2020?"
* "Return a random memory from 2019"

### Long-term goal

Evolve the system into a multimodal personal retrieval engine where the user can ask vague or natural questions and still get useful results:

* "That day at the beach when we were with Pablo"
* "Do I have pictures of blue boats?"
* "Find old birthday dinners"
* "Show me something happy from 2018"

---

## Product idea

Chromantis should behave like a **visual memory layer** on top of an existing folder hierarchy.

It is not meant to replace the current file structure at first. Instead, it should:

1. observe the structure
2. extract consistent metadata
3. enrich it with tags and normalized fields
4. expose it through a chatbot-friendly interface

This makes the first version low-risk and highly practical.

---

## Guiding principles

### 1. Deterministic first

Before adding LLMs, build a system that works with path parsing, rules, tags, and indexed metadata.

### 2. Preserve source of truth

The FTP folder layout remains the original source. Chromantis builds a searchable layer on top.

### 3. Incremental enrichment

Start with year, folder name, date, image path, and derived tags. Later add captions, embeddings, OCR, EXIF, and image analysis.

### 4. Traceable retrieval

Every result should clearly explain why it matched:

* year match
* folder title match
* tag match
* semantic match
* random selection within filtered scope

### 5. Easy to reindex

The system should support change detection and incremental refreshes when new folders or files are added.

---

## Core use cases

### Folder retrieval

User asks for a known trip, event, or period, and the bot returns the matching folder or a shortlist.

### Image retrieval

User asks for photos matching a year, event, or keyword, and the bot returns one or more images.

### Random memory

User asks for a random memory, optionally constrained by year, person, event, or rough theme.

### Structured browsing through chat

User asks:

* "What do I have from 2022?"
* "List folders with Christmas"
* "Which years contain beach trips?"

### Future semantic retrieval

User asks something fuzzy, and the system combines metadata search with AI-generated enrichments.

---

## Proposed architecture

### 1. FTP scanner

Responsible for walking the FTP tree and discovering folders and image files.

Responsibilities:

* connect to FTP
* recursively scan directories
* detect image files
* capture path, size, timestamps if available
* identify new / removed / changed files

Potential implementation detail:

* periodic sync job
* manual reindex command
* checksum or mtime-based change detection

### 2. Metadata extractor

Parses folder and file paths into structured fields.

Example derived fields:

* `year`
* `folder_name_raw`
* `folder_name_normalized`
* `event_date` (if derivable)
* `keywords_from_path`
* `filename`
* `extension`
* `full_path`

Example:

```text
/2023/2023-12-24_christmas_family_dinner/IMG_1024.jpg
```

Can become:

```json
{
  "year": 2023,
  "event_date": "2023-12-24",
  "folder_name_raw": "2023-12-24_christmas_family_dinner",
  "folder_title": "christmas family dinner",
  "tags": ["christmas", "family", "dinner"],
  "filename": "IMG_1024.jpg",
  "path": "/2023/2023-12-24_christmas_family_dinner/IMG_1024.jpg"
}
```

### 3. Index database

Stores canonical records for folders, files, tags, and future enrichments.

Good first options:

* SQLite for local simplicity
* PostgreSQL if multi-user or remote hosting becomes important

Suggested entities:

### folders

* id
* year
* folder_path
* folder_name_raw
* folder_name_normalized
* event_date
* title
* created_at
* updated_at

### images

* id
* folder_id
* file_path
* filename
* extension
* ftp_modified_at
* checksum (optional)
* width / height (future)
* exif_date (future)
* created_at
* updated_at

### tags

* id
* tag
* source (`path`, `manual`, `ai`)

### image_tags

* image_id
* tag_id

### folder_tags

* folder_id
* tag_id

### embeddings (future)

* entity_type
* entity_id
* model
* vector_reference
* created_at

### 4. Search layer

The logic that converts a user request into retrieval.
