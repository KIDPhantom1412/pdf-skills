# Artifact contracts

All paths are UTF-8. Page numbers are **1-based PDF pages**.

Work directory default: `./.addpdfocr/<pdf-stem>/` relative to the agent's cwd.

Final PDF: `<stem>.ocr.pdf` next to the source (or a path passed with `--out` when the source directory is read-only).

## `meta.json` (from `detect`)

```json
{
  "ok": true,
  "source_pdf": "C:/books/book.pdf",
  "work_dir": "C:/proj/.addpdfocr/book",
  "page_count": 320,
  "needs_ocr": true,
  "low_text_pages": 300,
  "median_chars": 0,
  "language_guess": "unknown",
  "has_existing_toc": false,
  "existing_toc_count": 0,
  "metadata": {"title": "..."}
}
```

`needs_ocr` is true when at least 40% of pages have almost no extractable text. Stop when it is false unless the user asked to OCR again.

## `ocr.json` (from `ocr`)

```json
{
  "ok": true,
  "engine": "rapidocr",
  "input": "C:/books/book.pdf",
  "output": "C:/books/book.ocr.pdf",
  "pages_jsonl": "C:/proj/.addpdfocr/book/pages.jsonl",
  "language": "japan",
  "rapidocr_rec_lang": "japan",
  "dpi": 144,
  "start": 1,
  "end": 320,
  "pages_done": 320,
  "skipped_pages": 0,
  "appended": false,
  "overlay_textboxes": 8400,
  "overlay_errors": 0,
  "work_dir": "C:/proj/.addpdfocr/book"
}
```

`output` is the searchable PDF. `overlay_textboxes` counts invisible text runs written into that file. `--append` skips pages whose `page` already exists in the JSONL and counts them in `skipped_pages`; it does not merge text layers into an existing output PDF.

## `pages.jsonl` (RapidOCR)

Written by default to `<work>/pages.jsonl`; override the location with `--pages-out`. One JSON object per line:

```json
{"page": 12, "char_count": 980, "text": "....", "font_heading_hints": [], "ocr_engine": "rapidocr", "ocr_line_count": 40}
```

This file is a side product of the text layer. It is not a bookmark outline. `pages-present --pages <work>/pages.jsonl [--start N --end M]` lists the pages it contains and the gaps in a range, so the agent can check coverage without reading the file.
