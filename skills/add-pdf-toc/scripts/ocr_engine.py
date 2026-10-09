"""Shared OCR engine for the add-pdf-ocr and add-pdf-toc skills.

Canonical copy: skills/add-pdf-ocr/scripts/ocr_engine.py
Keep this file identical in both skill script directories. Change OCR behavior
in the canonical copy, then copy it over the add-pdf-toc copy.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

MIN_CHARS_SEARCHABLE = 30
OCR_PAGE_RATIO = 0.4
DEFAULT_OCR_DPI = 144


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def _die(message: str, code: int = 1) -> None:
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False), file=sys.stderr)
    raise SystemExit(code)


def _dump(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _require_pymupdf():
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        _die("pymupdf is not installed in this interpreter. Install it in an isolated env (uvx --with pymupdf or venv + pip).")
    import pymupdf

    return pymupdf


def _pdf_path(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        _die(f"PDF not found: {path}")
    return path


def _default_work_name(args: argparse.Namespace) -> str:
    name = getattr(args, "default_work_name", None)
    if not name:
        _die("default_work_name is not set")
    return str(name)


def _work_dir(pdf: Path, explicit: str | None, default_name: str) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return (Path.cwd() / default_name / pdf.stem).resolve()


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _which_first(*names: str) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def _try_import(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def _script_name() -> str:
    argv0 = sys.argv[0] if sys.argv else ""
    name = Path(argv0).name
    return name or "addpdfocr.py"


def cmd_check_deps(_args: argparse.Namespace) -> None:
    python_ok = True
    pymupdf_ok = _try_import("pymupdf")
    rapidocr_ok = _try_import("rapidocr")
    lang_rec: list[str] = []
    if rapidocr_ok:
        try:
            from rapidocr import LangRec

            lang_rec = [item.value for item in LangRec]
        except Exception:
            lang_rec = []

    _dump(
        {
            "ok": True,
            "python": sys.executable,
            "python_version": sys.version.split()[0],
            "python_ok": python_ok,
            "pymupdf": pymupdf_ok,
            "rapidocr": rapidocr_ok,
            "rapidocr_lang_rec": lang_rec,
            "ocr_ready": rapidocr_ok,
        }
    )


def _guess_language(samples: Iterable[str]) -> str:
    text = "".join(samples)
    if not text:
        return "unknown"
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    kana = sum(1 for ch in text if ("\u3040" <= ch <= "\u309f") or ("\u30a0" <= ch <= "\u30ff"))
    hangul = sum(1 for ch in text if "\uac00" <= ch <= "\ud7af")
    latin = sum(1 for ch in text if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))

    if kana > 10:
        return "japan"
    if hangul > 10:
        return "korean"
    if cjk > latin * 0.3 and cjk > 20:
        return "chi_sim+eng" if latin else "chi_sim"
    if latin:
        return "eng"
    return "unknown"


def cmd_detect(args: argparse.Namespace) -> None:
    pymupdf = _require_pymupdf()
    pdf = _pdf_path(args.pdf)
    work = _ensure_dir(_work_dir(pdf, args.work_dir, _default_work_name(args)))

    doc = pymupdf.open(pdf)
    try:
        page_count = doc.page_count
        char_counts: list[int] = []
        samples: list[str] = []
        empty_or_image = 0
        for i, page in enumerate(doc):
            text = page.get_text("text") or ""
            n = len(text.strip())
            char_counts.append(n)
            if n < MIN_CHARS_SEARCHABLE:
                empty_or_image += 1
            if i < 8:
                samples.append(text[:1500])
        existing = doc.get_toc(simple=True) or []
        existing_entries = [{"level": int(row[0]), "title": str(row[1]), "page": int(row[2])} for row in existing]
        (work / "existing_toc.json").write_text(
            json.dumps({"ok": True, "count": len(existing_entries), "entries": existing_entries}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        needs_ocr = page_count > 0 and (empty_or_image / page_count) >= OCR_PAGE_RATIO
        language = _guess_language(samples)
        meta = {
            "ok": True,
            "source_pdf": str(pdf),
            "work_dir": str(work),
            "page_count": page_count,
            "needs_ocr": needs_ocr,
            "low_text_pages": empty_or_image,
            "median_chars": int(statistics.median(char_counts)) if char_counts else 0,
            "language_guess": language,
            "has_existing_toc": bool(existing),
            "existing_toc_count": len(existing),
            "metadata": {k: v for k, v in (doc.metadata or {}).items() if v},
        }
    finally:
        doc.close()

    (work / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    _dump(meta)


def _ocr_language(args: argparse.Namespace, work: Path) -> str:
    if args.language:
        return args.language
    meta_path = work / "meta.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        guess = meta.get("language_guess") or "eng"
        if guess != "unknown":
            return guess
    return "chi_sim+eng"


def _rapidocr_rec_lang(language: str) -> str:
    raw = language.lower().replace(" ", "")
    if "jpn" in raw or "japan" in raw:
        return "japan"
    if raw in {"chi_tra", "chi-tra", "zh-tw", "zh-hant"} or "chi_tra" in raw:
        return "chinese_cht"
    if "chi" in raw or raw in {"ch", "zh", "zh-cn", "zh-hans"}:
        return "ch"
    if raw in {"en", "eng", "english"}:
        return "en"
    if "kor" in raw or "korean" in raw:
        return "korean"
    return "ch"


def _rapidocr_lines(result: Any) -> list[tuple[list[list[float]], str, float]]:
    boxes = getattr(result, "boxes", None)
    txts = getattr(result, "txts", None)
    scores = getattr(result, "scores", None)
    if txts is not None:
        lines: list[tuple[list[list[float]], str, float]] = []
        n = len(txts)
        for i in range(n):
            txt = str(txts[i] or "").strip()
            if not txt:
                continue
            box = boxes[i] if boxes is not None else [[0, 0], [0, 0], [0, 0], [0, 0]]
            score = float(scores[i]) if scores is not None else 0.0
            pts = [[float(p[0]), float(p[1])] for p in box]
            lines.append((pts, txt, score))
        return lines
    if not result:
        return []
    # Older RapidOCR: list of [box, text, score]
    lines = []
    for item in result:
        if not item or len(item) < 2:
            continue
        box, txt = item[0], str(item[1] or "").strip()
        if not txt:
            continue
        score = float(item[2]) if len(item) > 2 else 0.0
        pts = [[float(p[0]), float(p[1])] for p in box]
        lines.append((pts, txt, score))
    return lines


def _lines_to_text(lines: list[tuple[list[list[float]], str, float]]) -> str:
    ordered = sorted(lines, key=lambda row: (min(p[1] for p in row[0]), min(p[0] for p in row[0])))
    return "\n".join(txt for _box, txt, _score in ordered)


def _insert_invisible_ocr(page, lines: list[tuple[list[list[float]], str, float]], zoom: float, fontname: str) -> int:
    import pymupdf

    written = 0
    for box, txt, _score in lines:
        txt_str = txt.strip()
        if not txt_str:
            continue
        xs = [p[0] / zoom for p in box]
        ys = [p[1] / zoom for p in box]
        x0, y0 = min(xs), min(ys)
        x1, y1 = max(xs), max(ys)
        w = x1 - x0
        h = y1 - y0
        if w < 1 or h < 1:
            continue
        fontsize = max(4.0, min(h * 0.85, 48.0))
        point = pymupdf.Point(x0, y1 - h * 0.15)
        try:
            rc = page.insert_text(
                point,
                txt_str,
                fontname=fontname,
                fontsize=fontsize,
                color=(0, 0, 0),
                render_mode=3,
                overlay=True,
            )
            if rc >= 0:
                written += 1
        except Exception:
            continue
    return written


_worker_engine: Any = None


def _ocr_worker_init(rec_lang: str) -> None:
    global _worker_engine
    try:
        from rapidocr import RapidOCR

        _worker_engine = RapidOCR(params={"Rec.lang_type": rec_lang, "EngineConfig.onnxruntime.intra_op_num_threads": 2})
    except Exception:
        _worker_engine = None


def _ocr_worker_task(args: tuple[str, int, float]) -> tuple[int, list[tuple[list[list[float]], str, float]], str | None]:
    pdf_str, index, zoom = args
    import pymupdf

    doc = pymupdf.open(pdf_str)
    try:
        page = doc[index - 1]
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        img_bytes = pix.tobytes("png")
    finally:
        doc.close()

    if _worker_engine is None:
        return index, [], "RapidOCR engine not initialized in worker"

    try:
        result = _worker_engine(img_bytes)
        lines = _rapidocr_lines(result)
        return index, lines, None
    except Exception as exc:
        return index, [], str(exc)


def _ocr_rapidocr(args: argparse.Namespace, pdf: Path, work: Path, language: str) -> dict[str, Any]:
    try:
        from rapidocr import RapidOCR
    except ImportError:
        _die(f"rapidocr is not installed. Run this script with uv: uv run {_script_name()}")

    pymupdf = _require_pymupdf()
    rec_lang = _rapidocr_rec_lang(language)
    fontname = "china-s" if rec_lang in {"japan", "ch", "chinese_cht"} else "helv"
    dpi = int(args.dpi or DEFAULT_OCR_DPI)
    zoom = dpi / 72.0
    start = args.start or 1
    doc = pymupdf.open(pdf)
    page_count = doc.page_count
    end = args.end or page_count
    if start < 1 or end < start or end > page_count:
        doc.close()
        _die(f"Invalid page range {start}-{end} for page_count={page_count}")

    workers = max(1, getattr(args, "workers", 1) or 1)
    jsonl_path = Path(args.pages_out).expanduser().resolve() if args.pages_out else work / "pages.jsonl"
    out_pdf = Path(args.out).expanduser().resolve() if args.out else None
    overlay_written = 0
    overlay_errors = 0
    pages_done = 0
    saved_tmp = False
    tmp_pdf = None

    mode = "a" if args.append else "w"
    try:
        with jsonl_path.open(mode, encoding="utf-8") as handle:
            if workers > 1 and (end - start + 1) > 1:
                from concurrent.futures import ProcessPoolExecutor

                tasks = [(str(pdf), index, zoom) for index in range(start, end + 1)]
                with ProcessPoolExecutor(max_workers=workers, initializer=_ocr_worker_init, initargs=(rec_lang,)) as executor:
                    for index, lines, err in executor.map(_ocr_worker_task, tasks, chunksize=1):
                        if err:
                            print(
                                json.dumps({"ok": False, "page": index, "error": err}, ensure_ascii=False),
                                file=sys.stderr,
                            )
                        text = _lines_to_text(lines)
                        handle.write(
                            json.dumps(
                                {
                                    "page": index,
                                    "char_count": len(text.strip()),
                                    "text": text,
                                    "font_heading_hints": [],
                                    "ocr_engine": "rapidocr",
                                    "ocr_line_count": len(lines),
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                        handle.flush()
                        if out_pdf is not None:
                            try:
                                overlay_written += _insert_invisible_ocr(doc[index - 1], lines, zoom, fontname)
                            except Exception:
                                overlay_errors += 1
                        pages_done += 1
                        print(
                            json.dumps(
                                {
                                    "progress": True,
                                    "page": index,
                                    "end": end,
                                    "chars": len(text.strip()),
                                    "lines": len(lines),
                                },
                                ensure_ascii=False,
                            ),
                            file=sys.stderr,
                        )
            else:
                engine = RapidOCR(params={"Rec.lang_type": rec_lang})
                for index in range(start, end + 1):
                    page = doc[index - 1]
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                    try:
                        result = engine(pix.tobytes("png"))
                        lines = _rapidocr_lines(result)
                    except Exception as exc:
                        lines = []
                        print(
                            json.dumps({"ok": False, "page": index, "error": str(exc)}, ensure_ascii=False),
                            file=sys.stderr,
                        )
                    text = _lines_to_text(lines)
                    handle.write(
                        json.dumps(
                            {
                                "page": index,
                                "char_count": len(text.strip()),
                                "text": text,
                                "font_heading_hints": [],
                                "ocr_engine": "rapidocr",
                                "ocr_line_count": len(lines),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    handle.flush()
                    if out_pdf is not None:
                        try:
                            overlay_written += _insert_invisible_ocr(page, lines, zoom, fontname)
                        except Exception:
                            overlay_errors += 1
                    pages_done += 1
                    print(
                        json.dumps(
                            {
                                "progress": True,
                                "page": index,
                                "end": end,
                                "chars": len(text.strip()),
                                "lines": len(lines),
                            },
                            ensure_ascii=False,
                        ),
                        file=sys.stderr,
                    )
        if out_pdf is not None:
            out_pdf.parent.mkdir(parents=True, exist_ok=True)
            tmp_pdf = out_pdf.with_name(f"{out_pdf.stem}.tmp_{os.getpid()}{out_pdf.suffix}")
            doc.save(tmp_pdf, garbage=4, deflate=True)
            saved_tmp = True
    finally:
        doc.close()
        if saved_tmp and tmp_pdf is not None and tmp_pdf.exists():
            tmp_pdf.replace(out_pdf)

    return {
        "ok": True,
        "engine": "rapidocr",
        "input": str(pdf),
        "output": str(out_pdf) if out_pdf else None,
        "pages_jsonl": str(jsonl_path),
        "language": language,
        "rapidocr_rec_lang": rec_lang,
        "dpi": dpi,
        "start": start,
        "end": end,
        "pages_done": pages_done,
        "overlay_textboxes": overlay_written,
        "overlay_errors": overlay_errors,
        "work_dir": str(work),
    }


def _ocr_ocrmypdf(args: argparse.Namespace, pdf: Path, work: Path, language: str) -> dict[str, Any]:
    out = Path(args.out).expanduser().resolve() if args.out else work / f"{pdf.stem}.searchable.pdf"
    tesseract = _which_first("tesseract")
    ghostscript = _which_first("gs", "gswin64c", "gswin32c")
    script = _script_name()
    if not tesseract or not ghostscript:
        _die(
            "ocrmypdf engine needs Tesseract and Ghostscript on PATH. "
            f"tesseract={tesseract!r}, ghostscript={ghostscript!r}. "
            f"This skill uses RapidOCR only. Run: uv run {script} ocr --engine rapidocr ..."
        )

    cmd = [
        sys.executable,
        "-m",
        "ocrmypdf",
        "--skip-text",
        "-l",
        language,
        str(pdf),
        str(out),
    ]
    if args.deskew:
        cmd.insert(3, "--deskew")
    if args.start or args.end:
        start = args.start or 1
        end = args.end or start
        cmd[3:3] = ["--pages", f"{start}-{end}"]

    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as exc:
        _die(f"Failed to launch ocrmypdf: {exc}")

    if completed.returncode != 0:
        _die(
            "ocrmypdf failed. Install ocrmypdf in the same isolated env "
            f"(uv run --with ocrmypdf). stderr: {(completed.stderr or '')[-2000:]}"
        )

    return {
        "ok": True,
        "engine": "ocrmypdf",
        "input": str(pdf),
        "output": str(out),
        "language": language,
        "work_dir": str(work),
    }


def cmd_ocr(args: argparse.Namespace) -> None:
    pdf = _pdf_path(args.pdf)
    work = _ensure_dir(_work_dir(pdf, args.work_dir, _default_work_name(args)))
    language = _ocr_language(args, work)
    engine = args.engine
    if engine == "auto":
        engine = "rapidocr" if _try_import("rapidocr") else "ocrmypdf"

    if engine == "rapidocr":
        payload = _ocr_rapidocr(args, pdf, work, language)
    elif engine == "ocrmypdf":
        payload = _ocr_ocrmypdf(args, pdf, work, language)
    else:
        _die(f"Unknown OCR engine: {engine}")

    (work / "ocr.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _dump(payload)
