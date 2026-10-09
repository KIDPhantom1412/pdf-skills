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
uv run "$SCRIPT" ocr --engine rapidocr <pdf> --work-dir <work> --language <LangRec> --out <stem>.ocr.pdf
uv run "$SCRIPT" ocr --engine rapidocr <pdf> --work-dir <work> --language <LangRec> --out <stem>.ocr.pdf --start N --end M
```

`--out` defaults to `<stem>.ocr.pdf` next to the source when omitted. Pass `--start` / `--end` only when the user asked for a page range. The default is the whole file.

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

Run `detect`. If `needs_ocr` is false, the PDF already has a text layer. Stop and say so. Continue only when the user explicitly asked to OCR again.

### 2. OCR

Choose `--language` using [references/language.md](references/language.md), then run `ocr --engine rapidocr`.

The command writes `<stem>.ocr.pdf` with an invisible text layer and a `pages.jsonl` side file under the work dir. Leave the source PDF unchanged.

## Report to the user

Give: output PDF path, RapidOCR `--language`, page count, `pages_done`, and `overlay_errors`. If `overlay_errors` is non-zero, say which pages failed if the stderr progress lines show them.
