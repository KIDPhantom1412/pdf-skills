---
name: add-pdf-ocr
description: Add an invisible OCR text layer so a scanned PDF becomes searchable. Use when the user asks to OCR a PDF, add a text layer, make a scanned PDF searchable, or mentions 扫描件识别, OCR, or 文字层. Does not add bookmarks or a table of contents.
compatibility: Requires uv.
---

# Add PDF OCR

The agent drives this workflow. Do not write one-off OCR snippets; use `scripts/addpdfocr.py`.

This skill writes a searchable PDF. It does not add bookmarks. For a sidebar table of contents, use the `add-pdf-toc` skill.

## Resolve paths

- `SKILL_DIR` = directory that contains this `SKILL.md`.
- `SCRIPT` = `SKILL_DIR/scripts/addpdfocr.py`
- Work dir = `./.addpdfocr/<pdf-stem>/` unless the user names another folder.
- Final PDF = `<stem>.ocr.pdf` next to the source (or inside the work dir if the source directory is read-only).

## Run scripts

The script declares its own deps (PEP 723). Always:

```bash
uv run "$SCRIPT" check-deps
```

If `uv` is missing, stop and tell the user to install it: https://docs.astral.sh/uv/getting-started/installation/ — do not fall back to pip or a harness venv. Do not add `--with` packages.

`uv run` installs the PEP 723 dependencies automatically, so under `uv run` these flags are always true. If `check-deps` reports `pymupdf: false` or `ocr_ready: false`, the script was most likely run outside `uv run` (e.g. with a bare interpreter) — re-run it with `uv run`. If the flags are still false, stop and tell the user; do not install packages or switch engines.

Command examples use POSIX shell syntax (`"$VAR"`); adapt quoting and variable expansion to the current shell (PowerShell on Windows).

## OCR language

Do not hardcode a language. Before `ocr`:

1. Guess the primary script from the cover, filename, user, or `meta.language_guess` (scans are often `unknown`).
2. Read `rapidocr_lang_rec` from `check-deps`.
3. Map the guess onto a `LangRec` value from that list.
4. Pass the chosen code to `ocr --language`.

Bilingual books and RapidOCR's single-model limit: [references/language.md](references/language.md). JSON fields: [references/artifacts.md](references/artifacts.md).

## Commands

```bash
uv run "$SCRIPT" detect <pdf> --work-dir <work>
uv run "$SCRIPT" ocr --engine rapidocr <pdf> --work-dir <work> --language <LangRec> --out <stem>.ocr.pdf [--start N --end M] [--workers K]
uv run "$SCRIPT" pages-present --pages <work>/pages.jsonl [--start N --end M]
```

- `--out` writes the searchable PDF and defaults to `<stem>.ocr.pdf` next to the source; the JSONL side file defaults to `<work>/pages.jsonl` (override with `--pages-out`).
- `--workers K` runs K parallel OCR worker processes. Use it for long scans on a multi-core machine.
- Always pass `--engine rapidocr`. The `ocrmypdf` engine needs Tesseract/Ghostscript and uses Tesseract language codes this skill does not map; if `check-deps` shows `rapidocr: false`, stop and report instead of switching.
- `--start` / `--end` restrict the range. Pass them only when the user asked for a page range; the default is the whole file.
- `pages-present` lists which pages of a JSONL already exist and which are missing in a range. Use it instead of reading `pages.jsonl` directly.

## Workflow

Copy and tick:

```
- [ ] check-deps
- [ ] detect
- [ ] if needs_ocr is false: stop unless the user asked to OCR again
- [ ] choose LangRec, then ocr the requested range (whole file by default)
- [ ] report output path, language, pages done, overlay errors
```

### 1. Detect

Run `detect`. It writes the result to `<work>/meta.json` and prints the same JSON to stdout — read `needs_ocr`, `low_text_pages`, `median_chars`, and `language_guess` from there. If `needs_ocr` is false, the PDF already has a text layer. Stop and say so. Continue only when the user explicitly asked to OCR again. `needs_ocr` is true when at least 40% of pages have almost no extractable text. For a borderline result (e.g. `low_text_pages` inflated by thin watermark text), report the numbers (`low_text_pages`, `median_chars`) and let the user decide.

### 2. OCR

Choose `--language` using [references/language.md](references/language.md), then run `ocr --engine rapidocr`.

The command writes `<stem>.ocr.pdf` with an invisible text layer and a `pages.jsonl` side file under the work dir. Leave the source PDF unchanged.

**One-shot rule:** each `ocr --out` run opens the **source** PDF and overlays only the current range; `--append` extends only the JSONL. Batched runs do not accumulate text layers in the output PDF — the final searchable PDF must be produced by a single command covering the whole requested range. Use `--workers` for speed instead of batching.

## Report to the user

Give: output PDF path, RapidOCR `--language`, page count, `pages_done`, `skipped_pages` (pages already in the JSONL; only non-zero with `--append`), and `overlay_errors`. If `overlay_errors` is non-zero, say which pages failed if the stderr progress lines show them.
