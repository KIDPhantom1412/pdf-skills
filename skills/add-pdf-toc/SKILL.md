---
name: add-pdf-toc
description: Add a hierarchical PDF bookmark outline (sidebar TOC) to a searchable or scanned PDF. Default depth is the printed TOC. Deeper headings require a full text extract of each in-scope chapter before the fine-heading subagents run. Use when the user asks to add a table of contents, bookmarks, or outline to a PDF, including a scanned PDF.
compatibility: Requires uv.
---

# Add PDF TOC

The agent drives this workflow. Do not write one-off PyMuPDF snippets; use `scripts/addpdftoc.py`.

## Resolve paths

- `SKILL_DIR` = directory that contains this `SKILL.md`.
- `SCRIPT` = `SKILL_DIR/scripts/addpdftoc.py`
- Work dir = `./.addpdftoc/<pdf-stem>/` unless the user names another folder.
- Final PDF = `<stem>.with-toc.pdf` next to the source (or inside the work dir if the source is read-only).

## Run scripts

The script declares its own deps (PEP 723). Always:

```bash
uv run "$SCRIPT" check-deps
```

If `uv` is missing, stop and tell the user to install it: https://docs.astral.sh/uv/getting-started/installation/ — do not fall back to pip or a harness venv. Do not add `--with` packages.

## OCR language

Do not hardcode a language. Before `ocr`:

1. Guess the primary script from the cover, filename, user, or `meta.language_guess` (scans are often `unknown`).
2. Read `rapidocr_lang_rec` from `check-deps`.
3. Map the guess onto a `LangRec` value from that list.
4. Pass the chosen code to `ocr --language`.

Bilingual books and RapidOCR's single-model limit: [references/language.md](references/language.md).

## Commands

```bash
uv run "$SCRIPT" detect <pdf> --work-dir <work>
uv run "$SCRIPT" ocr --engine rapidocr <pdf> --work-dir <work> --language <LangRec> [--start N --end M] [--append]
uv run "$SCRIPT" extract <searchable-or-original.pdf> --work-dir <work> [--start N --end M] [--append]
uv run "$SCRIPT" slice --pages <work>/pages.jsonl --start N --end M --out <work>/slices/ch-01.jsonl
uv run "$SCRIPT" page-window --pages <work>/pages.jsonl --page N --radius 1
uv run "$SCRIPT" check-outline --outline <work>/outline.proposed.json
uv run "$SCRIPT" write-toc <pdf> --outline <work>/outline.verified.json --out <stem>.with-toc.pdf
```

JSON field definitions: [references/artifacts.md](references/artifacts.md). Subagent roles, prompts, and parallelism: [references/subagents.md](references/subagents.md).

## Workflow

Copy and tick:

```
- [ ] check-deps
- [ ] detect
- [ ] if needs_ocr: look up LangRec, then front-matter OCR (--start 1 --end 30)
- [ ] extract front matter when the PDF already has a text layer
- [ ] coarse map (one subagent) -> printed_toc.json + page_offset + chapters.json
- [ ] choose depth: printed TOC by default; user request overrides
- [ ] if body headings are required: full-extract each in-scope chapter, then fine-heading subagents (batches of 3-5)
- [ ] merge outline.proposed.json
- [ ] check-outline (cheap)
- [ ] verify against page text (full chapter extract, or a window filled in for that bookmark)
- [ ] fix / rerun failing chapters
- [ ] write-toc + report.md
```

Serial until `chapters.json`, `page_offset`, and the depth decision exist. Full-extract a chapter before its fine-heading subagent. Then verify. Do not start the next stage until the previous barrier is done.

### 1. Detect

Run `detect`. Existing bookmarks in the source PDF will not block the process (final output writes to a separate `<stem>.with-toc.pdf` file with a clean outline by default, leaving the original file intact; do not interrupt to ask the user unless they explicitly asked to preserve or merge old bookmarks).

### 2. Page text

Read **page-aligned JSONL only**, not screenshots. Do not pass `--out` to `ocr` here. This step writes page text for headings. To embed a searchable text layer, use the `add-pdf-ocr` skill.

Searchable PDFs (`needs_ocr: false`) use `extract`. Scans (`needs_ocr: true`) use `ocr`. Do not OCR a scan from cover to end before the depth decision.

Front matter first, for the coarse map:

- Scan: OCR pages 1–30 with `--pages-out <work>/pages.jsonl`.
- Searchable: `extract` that same span.
- After the coarse map, lock `page_offset = pdf_page - printed_page` on 2–3 chapter-start pages. On a scan, OCR those pages with `--append`.

Follow-up ranges use `--append` on `ocr` and `extract` so front matter stays in `pages.jsonl`. Do not append pages that are already in the file.

### 3. Coarse map

Launch **one** subagent with the first 20–40 pages (`slice`). Wait for `printed_toc.json` and `chapters.json`. Align printed page numbers to PDF pages before cutting chapters.

Printed TOC entries, after that alignment, are the default outline. They also define chapter ranges. If there is no printed TOC, split the body into ~30-page chunks (adjust at obvious chapter-sized font hints).

### 4. Heading depth

Default depth is the printed TOC's own depth. Use those entries as the outline. Do not run fine-heading subagents, and do not extract chapter bodies for new headings.

The user request overrides that default. Honor a depth cap ("level 2 only"), a page range, named chapters, or an explicit ask for section or subsection headings. Full-extract and fine-heading only chapters inside that request.

If there is no printed TOC, body text is the outline source. The default range is the whole book. The same user limits narrow it.

### 5. Fine outline

Run this step only when section 4 requires body headings.

Full-extract each in-scope chapter first. Every PDF page from `start_page` to `end_page` must already be a line in `pages.jsonl`. A chapter-start page or a `page-window` sample is not enough. Scan: `ocr --append` that range. Searchable: `extract --append` that range. If any page is missing, fill it in and do not launch that chapter's subagent.

Then launch fine-heading subagents by chapter (or chunk).
- **Concurrency control:** When books have many chapters (e.g. 15–30 chapters), do not flood the API with dozens of concurrent subagents at once. Launch in bounded parallel batches of 3–5 chapters to avoid platform rate limits (`RateLimitError`, `resource_exhausted`) and maintain consistent heading depth.
- Each agent receives only its complete slice + the printed TOC fragment for that chapter. If one fails, retry **that** subagent; do not read its JSONL yourself.

Merge into `outline.proposed.json`: printed TOC as the chapter backbone, body headings as deeper levels. If this step did not run, `outline.proposed.json` is the aligned printed TOC. Run `check-outline`. Fix level jumps and backward pages before verify (note: for right-to-left / reverse-bound Japanese classical texts or appendices reading backwards, handle leaf sections carefully).

### 6. Verify and write

Verify **before** the final `write-toc` (verdicts use JSONL, not the PDF). Launch **one verify subagent per chapter** in parallel (or one batch if the outline is small). Each gets `page-window` for its entries (`radius` 1, or 2 after `not_found`).

The window must already contain those pages. After a full chapter extract, read `pages.jsonl`. For a printed-TOC outline, `ocr --append` or `extract --append` only the missing bookmark pages, then read the window. Do not treat that sample as a source of new headings.

The title must appear near the **start of the target page**, not merely anywhere in the window (unit previews and running headers do not count). Apply `suggested_page` for real `off_by_n`. If a chapter's fail rate is high and that chapter had a fine-heading pass, rerun **that chapter's** fine-heading subagent only, then `check-outline` and verify again.

Then `write-toc` and `report.md`.

## Orchestrator context

Do not ingest `pages.jsonl` or chapter slices. You may read `meta.json`, `printed_toc.json`, `chapters.json`, outlines, `check-outline` output, verification summaries, and `report.md`.

## Report to the user

Give: output PDF path, depth used (printed TOC or body headings), whether a full chapter extract ran, RapidOCR `--language` if OCR ran, bookmark count, verify pass rate, remaining failures. Offer to rerun a named chapter or cap depth ("level 2 only").
