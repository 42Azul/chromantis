---
title: Local search experiments
description: Optional local interpretation, OCR, and visual search benchmarks.
---

## Optional model interpreter

The API and Telegram use the rule interpreter by default. To use a local model, configure an adapter command in `.env`, such as `QUERY_INTERPRETER_COMMAND=/opt/chromantis/bin/model-adapter`, and restart both clients. The executable receives one UTF-8 JSON object on stdin and must write one JSON object to stdout. Keep diagnostics on stderr.

| Direction | Example |
| --- | --- |
| Stdin | `{"text":"Find a couple of city photos from 2021"}` |
| Stdout | `{"action":"images","query":"city 2021","count":2,"confidence":0.9}` |

Actions are `images`, `folders`, `random`, and `years`. Counts are 1–10 and confidence is 0–1. Confidence below 0.65 requests clarification. A timeout, an executable failure, or an invalid response falls back to the rules. The adapter receives the request text. The existing search engine applies the resulting query to the index.

An in-process adapter can implement `QueryInterpreter.interpret(text)` and be passed into `ApplicationService`. This is the extension point for future providers.

## Optional image enrichment

Run enrichment after indexing. The CLI reads only indexed photos from the configured archive and writes model output to a separate SQLite table with model, version, source metadata, and processing time. It skips photos already processed for that version, retries unsuccessful attempts after unprocessed photos, and ignores stale results when the indexed source metadata changes.

The included OCR adapter requires Tesseract and the selected language data on the machine. Start with a small batch.

```bash
python scripts/enrich_images.py \
  --command "python scripts/tesseract_enricher.py --language eng" \
  --model tesseract-eng --version "$(tesseract --version | head -n 1)" --limit 25
```

Add `--album "2024/2024-08-04_beach"` to restrict the batch to one exact indexed album path. Running the same command later resumes pending photos for that album and model version.

For captions or object tags, configure an image-model adapter with `--command`. Each invocation receives one original image on stdin as bytes and writes one UTF-8 JSON object to stdout. Return empty strings or an empty list for fields your model does not provide.

```json
{"caption":"A bicycle beside a blue wall","ocr_text":"BIKE SHOP","object_tags":["bicycle","wall"]}
```

Set `ENRICHMENT_SEARCH=true` and restart the API and bot to include these fields in image and random-image searches. Matches explain which terms used enrichment, and year and curated-person filters still apply. The default deployment continues to search indexed metadata without running a model.

### Evaluate search with synthetic photos

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

### Local visual search trial

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
