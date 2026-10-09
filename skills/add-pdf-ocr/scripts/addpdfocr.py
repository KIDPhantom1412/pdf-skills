# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pymupdf>=1.24.0",
#   "rapidocr>=3.0.0",
#   "onnxruntime>=1.17.0",
# ]
# ///
"""Add an invisible OCR text layer to a PDF. No AI calls."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from ocr_engine import (  # noqa: E402
    DEFAULT_OCR_DPI,
    _configure_stdio,
    cmd_check_deps,
    cmd_detect,
    cmd_ocr,
    cmd_pages_present,
)

WORK_DIR_NAME = ".addpdfocr"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Add an invisible OCR text layer to a PDF (no AI).")
    parser.set_defaults(default_work_name=WORK_DIR_NAME)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check-deps", help="Report interpreter and OCR binaries")

    detect = sub.add_parser("detect", help="Inspect PDF text density")
    detect.add_argument("pdf")
    detect.add_argument("--work-dir")

    ocr = sub.add_parser("ocr", help="OCR with RapidOCR (default) or ocrmypdf")
    ocr.add_argument("pdf")
    ocr.add_argument("--work-dir")
    ocr.add_argument("--out", help="Searchable PDF (default: <stem>.ocr.pdf next to the source)")
    ocr.add_argument("--pages-out", dest="pages_out", help="Write OCR text JSONL (RapidOCR)")
    ocr.add_argument("--language")
    ocr.add_argument("--engine", choices=["auto", "rapidocr", "ocrmypdf"], default="auto")
    ocr.add_argument("--start", type=int)
    ocr.add_argument("--end", type=int)
    ocr.add_argument("--dpi", type=int, default=DEFAULT_OCR_DPI)
    ocr.add_argument("--deskew", action="store_true")
    ocr.add_argument("--append", action="store_true", help="Append OCR lines to pages_out instead of overwriting")
    ocr.add_argument("--workers", type=int, default=1, help="Number of parallel worker processes for OCR (default 1)")

    pages_p = sub.add_parser("pages-present", help="List pages already in a pages.jsonl, and gaps in a range")
    pages_p.add_argument("--pages", required=True)
    pages_p.add_argument("--start", type=int)
    pages_p.add_argument("--end", type=int)

    return parser


def main(argv: list[str] | None = None) -> None:
    _configure_stdio()
    args = build_parser().parse_args(argv)
    if args.cmd == "ocr" and not args.out:
        pdf = Path(args.pdf).expanduser()
        args.out = str(pdf.with_name(f"{pdf.stem}.ocr.pdf"))
    commands = {
        "check-deps": cmd_check_deps,
        "detect": cmd_detect,
        "ocr": cmd_ocr,
        "pages-present": cmd_pages_present,
    }
    commands[args.cmd](args)


if __name__ == "__main__":
    main()
