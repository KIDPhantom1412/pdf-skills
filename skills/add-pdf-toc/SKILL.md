---
name: add-pdf-toc
description: Add a hierarchical PDF bookmark outline (sidebar TOC) to a searchable or scanned PDF. For scans, OCR only the pages needed to read headings, then verify bookmarks against page text with subagents. Use when the user asks to add a table of contents, bookmarks, or outline to a PDF, including a scanned PDF.
compatibility: Requires uv.
---

# Add PDF TOC

The agent drives this workflow. Python scripts never call a model. Do not write one-off PyMuPDF snippets; use `scripts/addpdftoc.py`.

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
uv run "$SCRIPT" ocr --engine rapidocr <pdf> --work-dir <work> --language <LangRec> [--start N --end M]
uv run "$SCRIPT" extract <searchable-or-original.pdf> --work-dir <work> [--start N --end M]
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
- [ ] if needs_ocr: look up LangRec, then Phase 1 front-matter OCR (--start 1 --end 30)
- [ ] extract only if digital / font hints needed
- [ ] coarse map (one subagent) -> printed_toc.json + page_offset + chapters.json
- [ ] fine headings: chapter subagents in bounded batches (3-5 parallel)
- [ ] merge outline.proposed.json
- [ ] check-outline (cheap)
- [ ] verify: targeted page-window OCR & subagent verification
- [ ] fix / rerun failing chapters
- [ ] write-toc + report.md
```

Serial until `chapters.json` and `page_offset` exist. Then fine-heading subagents in bounded parallel batches; then verify subagents. Do not start the next stage until the previous barrier is done.

### 1. Detect

Run `detect`. Existing bookmarks in the source PDF will not block the process (final output writes to a separate `<stem>.with-toc.pdf` file with a clean outline by default, leaving the original file intact; do not interrupt to ask the user unless they explicitly asked to preserve or merge old bookmarks).

### 2. Text layer (Two-Phase Strategy)

For scanned PDFs (`needs_ocr: true`), **do not run full-book OCR upfront**—full-book OCR across hundreds of pages is slow and CPU-heavy. Instead, use a **two-phase OCR workflow**:

1. **Phase 1 (Front-Matter & TOC Skeleton)**:
   - OCR only the front matter (typically pages 1 to 25–40, e.g. `--start 1 --end 30`) using `--pages-out <work>/pages.jsonl`.
   - Run coarse mapping on this slice to find `printed_toc.json` and calculate `page_offset = pdf_page - printed_page`.
   - Sample 2–3 early body chapter start pages with `--start N --end N` to verify and lock in `page_offset`.
2. **Phase 2 (Targeted Verification Sampling)**:
   - If a reliable printed TOC and offset are established, the outline backbone can be mapped directly.
   - Run OCR only on targeted chapter starting pages and section windows (`page-window` radius 1) for subagent verification and deeper heading extraction, rather than OCRing the entire book.
   - If the book lacks a printed TOC, split into ~30-page chunks and OCR chunks sequentially or in bounded batches.

Do not pass `--out` to `ocr`. This step writes page text for headings only. To embed a searchable text layer, use the `add-pdf-ocr` skill. Skip a second `extract` unless you need font hints from a digital PDF.

`extract` is used directly on digital/searchable PDFs without OCR. Subsequent AI reads **page-aligned JSONL only**, not screenshots.

### 3. Coarse map

Launch **one** subagent with the first 20–40 pages (`slice`). Wait for `printed_toc.json` and `chapters.json`. Printed TOC is a routing skeleton, not the final ebook TOC. Align printed page numbers to PDF pages before cutting chapters.

If there is no printed TOC, split into ~30-page chunks (adjust at obvious chapter-sized font hints).

### 4. Fine outline

Launch fine-heading subagents by chapter (or chunk).
- **Concurrency control:** When books have many chapters (e.g. 15–30 chapters), do not flood the API with dozens of concurrent subagents at once. Launch in bounded parallel batches of 3–5 chapters to avoid platform rate limits (`RateLimitError`, `resource_exhausted`) and maintain consistent heading depth.
- Each agent receives only its slice + the printed TOC fragment for that chapter. If one fails, retry **that** subagent; do not read its JSONL yourself.

Merge into `outline.proposed.json`: printed TOC as chapter/section backbone, body headings as deeper levels. Run `check-outline`. Fix level jumps and backward pages before verify (note: for right-to-left / reverse-bound Japanese classical texts or appendices reading backwards, handle leaf sections carefully).

### 5. Verify and write

Verify **before** the final `write-toc` (verdicts use JSONL, not the PDF). Launch **one verify subagent per chapter** in parallel (or one batch if the outline is small). Each gets `page-window` for its entries (`radius` 1, or 2 after `not_found`).

The title must appear near the **start of the target page**, not merely anywhere in the window (unit previews and running headers do not count). Apply `suggested_page` for real `off_by_n`. If a chapter's fail rate is high, rerun **that chapter's** fine-heading subagent only, then `check-outline` and verify again.

Then `write-toc` and `report.md`.

## Orchestrator context

Do not ingest `pages.jsonl` or chapter slices. You may read `meta.json`, `printed_toc.json`, `chapters.json`, outlines, `check-outline` output, verification summaries, and `report.md`.

## Report to the user

Give: output PDF path, whether OCR ran, RapidOCR `--language`, bookmark count, verify pass rate, remaining failures. Offer to rerun a named chapter or cap depth ("level 2 only").
