# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pymupdf>=1.24.0",
#   "rapidocr>=3.0.0",
#   "onnxruntime>=1.17.0",
# ]
# ///
"""Mechanical PDF helpers for the add-pdf-toc skill. No AI calls."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from ocr_engine import (  # noqa: E402
    DEFAULT_OCR_DPI,
    _configure_stdio,
    _die,
    _dump,
    _ensure_dir,
    _pdf_path,
    _require_pymupdf,
    _work_dir,
    cmd_check_deps,
    cmd_detect,
    cmd_ocr,
    cmd_pages_present,
)

WORK_DIR_NAME = ".addpdftoc"
HEADING_SIZE_RATIO = 1.12
HEADING_MAX_LEN = 80


def _toc_work_dir(pdf: Path, explicit: str | None) -> Path:
    return _work_dir(pdf, explicit, WORK_DIR_NAME)


def _heading_hints(page) -> list[dict[str, Any]]:
    data = page.get_text("dict")
    sizes: list[float] = []
    spans_out: list[tuple[float, str, str, list[float]]] = []
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = (span.get("text") or "").strip()
                size = float(span.get("size") or 0)
                if not text or size <= 0:
                    continue
                sizes.append(size)
                spans_out.append((size, text, span.get("font") or "", list(span.get("bbox") or [])))
    if not sizes:
        return []
    body = statistics.median(sizes)
    threshold = body * HEADING_SIZE_RATIO
    hints: list[dict[str, Any]] = []
    seen: set[str] = set()
    for size, text, font, bbox in spans_out:
        if size < threshold:
            continue
        if not (2 <= len(text) <= HEADING_MAX_LEN):
            continue
        if text.isdigit():
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        hints.append({"text": text, "size": round(size, 2), "font": font, "bbox": [round(x, 2) for x in bbox]})
        if len(hints) >= 12:
            break
    return hints


def cmd_extract(args: argparse.Namespace) -> None:
    pymupdf = _require_pymupdf()
    pdf = _pdf_path(args.pdf)
    work = _ensure_dir(_toc_work_dir(pdf, args.work_dir))
    out = Path(args.out).expanduser().resolve() if args.out else work / "pages.jsonl"

    doc = pymupdf.open(pdf)
    page_count = doc.page_count
    start = args.start or 1
    end = args.end or page_count
    if start < 1 or end < start or end > page_count:
        doc.close()
        _die(f"Invalid page range {start}-{end} for page_count={page_count}")
    existing_pages: set[int] = set()
    if args.append and out.is_file():
        for row in _iter_pages(out):
            try:
                existing_pages.add(int(row["page"]))
            except (KeyError, TypeError, ValueError):
                continue
    count = 0
    skipped_pages = 0
    mode = "a" if args.append else "w"
    try:
        with out.open(mode, encoding="utf-8") as handle:
            for index in range(start, end + 1):
                if index in existing_pages:
                    skipped_pages += 1
                    continue
                page = doc[index - 1]
                text = page.get_text("text") or ""
                record = {
                    "page": index,
                    "char_count": len(text.strip()),
                    "text": text,
                    "font_heading_hints": _heading_hints(page) if args.hints else [],
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1
    finally:
        doc.close()

    payload = {
        "ok": True,
        "source_pdf": str(pdf),
        "pages_jsonl": str(out),
        "page_count": count,
        "skipped_pages": skipped_pages,
        "start": start,
        "end": end,
        "work_dir": str(work),
        "hints": bool(args.hints),
        "append": bool(args.append),
    }
    (work / "extract.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _dump(payload)


def _iter_pages(jsonl: Path) -> Iterable[dict[str, Any]]:
    with jsonl.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def cmd_slice(args: argparse.Namespace) -> None:
    jsonl = Path(args.pages).expanduser().resolve()
    if not jsonl.is_file():
        _die(f"pages.jsonl not found: {jsonl}")
    start, end = args.start, args.end
    if start < 1 or end < start:
        _die("Need 1-based --start/--end with end >= start")

    rows = [row for row in _iter_pages(jsonl) if start <= int(row["page"]) <= end]
    if args.out:
        out = Path(args.out).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as handle:
            for row in rows:
                compact = {
                    "page": row["page"],
                    "char_count": row.get("char_count", 0),
                    "text": row.get("text", ""),
                    "font_heading_hints": row.get("font_heading_hints") or [],
                }
                handle.write(json.dumps(compact, ensure_ascii=False) + "\n")
        _dump({"ok": True, "start": start, "end": end, "count": len(rows), "out": str(out)})
        return
    _dump({"ok": True, "start": start, "end": end, "count": len(rows), "pages": rows})


def cmd_page_window(args: argparse.Namespace) -> None:
    jsonl = Path(args.pages).expanduser().resolve()
    if not jsonl.is_file():
        _die(f"pages.jsonl not found: {jsonl}")
    target = args.page
    radius = max(0, args.radius)
    lo, hi = target - radius, target + radius
    pages = [row for row in _iter_pages(jsonl) if lo <= int(row["page"]) <= hi]
    _dump(
        {
            "ok": True,
            "target_page": target,
            "radius": radius,
            "pages": [
                {
                    "page": row["page"],
                    "text": row.get("text", ""),
                    "font_heading_hints": row.get("font_heading_hints") or [],
                }
                for row in pages
            ],
        }
    )


def _load_outline(path: Path) -> list[list[Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries", data) if isinstance(data, dict) else data
    toc: list[list[Any]] = []
    for item in entries:
        if isinstance(item, dict):
            level = int(item["level"])
            title = str(item["title"]).strip()
            page = int(item["page"])
        else:
            level, title, page = int(item[0]), str(item[1]).strip(), int(item[2])
        if level < 1 or page < 1 or not title:
            _die(f"Invalid outline entry: {item}")
        toc.append([level, title, page])
    if not toc:
        _die("Outline is empty")
    return toc


def cmd_check_outline(args: argparse.Namespace) -> None:
    toc = _load_outline(Path(args.outline).expanduser().resolve())
    issues: list[str] = []
    last_by_level: dict[int, int] = {}
    for i, (level, title, page) in enumerate(toc):
        if i == 0 and level != 1:
            issues.append(f"first entry is level {level}, expected 1 ({title})")
        if i > 0:
            prev_level = toc[i - 1][0]
            if level > prev_level + 1:
                issues.append(f"level jump {prev_level} -> {level} at {title}")
        parent_level = level - 1
        if parent_level >= 1 and parent_level in last_by_level and page < last_by_level[parent_level]:
            issues.append(f"page {page} for {title} is before parent page {last_by_level[parent_level]}")
        last_by_level = {lv: pg for lv, pg in last_by_level.items() if lv < level}
        last_by_level[level] = page
        if i > 0 and page < toc[i - 1][2] and level <= toc[i - 1][0]:
            issues.append(f"page went backwards at {title}: {toc[i - 1][2]} -> {page}")
    _dump({"ok": True, "entries": len(toc), "issue_count": len(issues), "issues": issues})


def cmd_write_toc(args: argparse.Namespace) -> None:
    pymupdf = _require_pymupdf()
    pdf = _pdf_path(args.pdf)
    toc = _load_outline(Path(args.outline).expanduser().resolve())
    out = Path(args.out).expanduser().resolve() if args.out else pdf.with_name(f"{pdf.stem}.with-toc.pdf")
    out.parent.mkdir(parents=True, exist_ok=True)

    doc = pymupdf.open(pdf)
    try:
        if doc.page_count < 1:
            _die("PDF has no pages")
        for _level, title, page in toc:
            if page > doc.page_count:
                _die(f"Outline page {page} ({title}) exceeds page_count {doc.page_count}")
        doc.set_toc(toc)
        doc.save(out, garbage=4, deflate=True)
    finally:
        doc.close()

    payload = {"ok": True, "input": str(pdf), "output": str(out), "entries": len(toc)}
    work = _toc_work_dir(pdf, args.work_dir)
    if work.exists() or args.work_dir:
        _ensure_dir(work)
        (work / "write.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _dump(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mechanical PDF TOC helpers (no AI).")
    parser.set_defaults(default_work_name=WORK_DIR_NAME)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check-deps", help="Report interpreter and OCR binaries")

    detect = sub.add_parser("detect", help="Inspect PDF text density and existing outline")
    detect.add_argument("pdf")
    detect.add_argument("--work-dir")

    ocr = sub.add_parser("ocr", help="OCR page text for headings (no text layer unless --out is set)")
    ocr.add_argument("pdf")
    ocr.add_argument("--work-dir")
    ocr.add_argument("--out", help="Optional searchable PDF. Omit to write JSONL only")
    ocr.add_argument("--pages-out", dest="pages_out", help="Write OCR text JSONL (RapidOCR)")
    ocr.add_argument("--language")
    ocr.add_argument("--engine", choices=["auto", "rapidocr", "ocrmypdf"], default="auto")
    ocr.add_argument("--start", type=int)
    ocr.add_argument("--end", type=int)
    ocr.add_argument("--dpi", type=int, default=DEFAULT_OCR_DPI)
    ocr.add_argument("--deskew", action="store_true")
    ocr.add_argument("--append", action="store_true", help="Append OCR lines to pages_out instead of overwriting")
    ocr.add_argument("--workers", type=int, default=1, help="Number of parallel worker processes for OCR (default 1)")

    extract = sub.add_parser("extract", help="Write per-page JSONL text")
    extract.add_argument("pdf")
    extract.add_argument("--work-dir")
    extract.add_argument("--out")
    extract.add_argument("--start", type=int)
    extract.add_argument("--end", type=int)
    extract.add_argument("--hints", action="store_true", default=True)
    extract.add_argument("--no-hints", action="store_false", dest="hints")
    extract.add_argument("--append", action="store_true", help="Append page lines to the output JSONL instead of overwriting")

    slice_p = sub.add_parser("slice", help="Slice pages.jsonl to a page range")
    slice_p.add_argument("--pages", required=True)
    slice_p.add_argument("--start", type=int, required=True)
    slice_p.add_argument("--end", type=int, required=True)
    slice_p.add_argument("--out")

    window = sub.add_parser("page-window", help="Load target page +/- radius from JSONL")
    window.add_argument("--pages", required=True)
    window.add_argument("--page", type=int, required=True)
    window.add_argument("--radius", type=int, default=1)

    check_o = sub.add_parser("check-outline", help="Cheap structural checks on an outline JSON")
    check_o.add_argument("--outline", required=True)

    pages_p = sub.add_parser("pages-present", help="List pages already in a pages.jsonl, and gaps in a range")
    pages_p.add_argument("--pages", required=True)
    pages_p.add_argument("--start", type=int)
    pages_p.add_argument("--end", type=int)

    write = sub.add_parser("write-toc", help="Write PDF bookmarks from outline JSON")
    write.add_argument("pdf")
    write.add_argument("--outline", required=True)
    write.add_argument("--out")
    write.add_argument("--work-dir")

    return parser


def main(argv: list[str] | None = None) -> None:
    _configure_stdio()
    args = build_parser().parse_args(argv)
    commands = {
        "check-deps": cmd_check_deps,
        "detect": cmd_detect,
        "ocr": cmd_ocr,
        "extract": cmd_extract,
        "slice": cmd_slice,
        "page-window": cmd_page_window,
        "pages-present": cmd_pages_present,
        "check-outline": cmd_check_outline,
        "write-toc": cmd_write_toc,
    }
    commands[args.cmd](args)


if __name__ == "__main__":
    main()
