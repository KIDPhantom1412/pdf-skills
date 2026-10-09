# Subagent roles

The orchestrator never attaches `pages.jsonl` and never reads a chapter slice to finish a failed agent's work. Retry that agent instead.

```
detect → front-matter text → coarse (1, serial)
                                ↓ barrier: chapters.json + depth
                             full-extract in-scope chapters (only when body headings are required)
                                ↓
                             fine headings × N (parallel, one per chapter)
                                ↓ barrier: merge + check-outline
                             verify × M (parallel, one per chapter)
                                ↓
                             write-toc
```

Launch each parallel group in bounded batches (3–5 subagents per batch). A platform `resource_exhausted` or rate limit on one agent is not a reason to serialize everything; retry the missing chapter. Retry a failed subagent at most 2 times; if it still fails, keep the printed-TOC entries for that chapter (if any), skip its body headings, and record the gap in `report.md`.

Pass only the sliced JSONL and the printed-TOC fragment for that chapter.

## Coarse map (one subagent)

Input: first 20–40 pages of `pages.jsonl` (and later pages only if the TOC is not in front matter).

Task:

1. Decide if a printed table of contents exists.
2. If yes, extract hierarchical entries and printed page numbers. Estimate PDF offset by searching chapter titles in later body text if those pages were provided; otherwise leave `page_offset` null for the orchestrator to resolve with extra slices. Do not trust printed numbers that OCR glued to the wrong heading until two body matches agree.
3. Emit `printed_toc.json` and a `chapters.json` draft.
4. Fill `front_matter` from the pages before the printed TOC, in reading order, plus a contents entry for `toc_pages` when a printed TOC exists. One level-1 entry per distinct section that is actually there. Cover, title page, copyright, and a preface that starts before the contents are included only when those pages exist — and they are not the whole set. Also include every other real section (half-title, series or imprint page, dedication, epigraph, acknowledgments, translator's or editor's note, how to use this book, lists of figures / tables / abbreviations, about the author, a map, a second preface, or anything else those pages contain). Use a short structural title (`Cover` / `封面`, `Title page` / `扉页`, `Copyright` / `版权页`, `Contents` / `目录` or `目次`, in the book's script) only for cover, title page, copyright, and the contents page, with `"structural": true`. Every other title is the heading on that page, with `quote` copied from it and `"structural": false`. A preface or similar section that starts after the TOC and is absent from the printed entries still goes in `front_matter`, at its real start page. Do not invent a section. Skip blank pages and ads.
5. If no printed TOC, say so. The orchestrator will split by page count (~30 pages) or by strong font hints. Still emit `front_matter` for the real sections before the body.

Do not emit the detailed ebook outline here. Front matter may be one `front` chapter; body lessons are separate chapters. `front_matter` is the bookmark list for those pages, not a replacement for the body outline.

## Fine headings (one subagent per chapter, parallel)

The orchestrator launches this role only when the outline must go deeper than the printed TOC, or there is no printed TOC. The slice is a full extract of the chapter, not a sample.

Input:

- Slice for `start_page`–`end_page`, with every page in that range present
- Printed TOC entries for this chapter (may be empty)
- Font hints already in the JSONL

If any page in the range is missing, do not guess titles for the gap. Stop and name the missing pages so the orchestrator can extract them and retry.

Task: extract a finer outline than the printed TOC from **body headings**. Rules:

- Every title must appear in the page text (`quote`), except the front-matter labels below.
- Prefer headings near the start of a section, not running headers/footers or unit-preview lists of later lessons.
- Use printed TOC as a skeleton you may deepen, not a ceiling.
- Pages are PDF pages from the JSONL `page` field.
- Return JSON `{ "entries": [ { "level", "title", "page", "quote" } ] }` only. Write the file the orchestrator named.

If the slice is mostly plates, return fewer entries rather than guessing.

**Front matter:** structural titles (`Cover`, `Title page`, `Copyright`, `Contents`, or the book's own script: 封面 / 扉页 / 版权页 / 目录) are only for the cover, title page, copyright page, and contents page. Any other section before the printed TOC keeps the heading printed on that page (献辞, 使用说明, 插图目录, and whatever else is there). `quote` must still be copied from that page. Do not invent a section the pages do not contain, and do not invent body section titles this way.

A chapter that is not the first in the book may start at level 2 when its parent unit already exists; the orchestrator merges.

## Verify (one subagent per chapter, parallel)

Input: that chapter's outline entries plus `page-window` JSON for each (`radius` 1, or 2 if the first pass is `not_found`).

Decide from the **target page's opening lines**, not from “string appears somewhere in the window”:

| verdict | when |
| --- | --- |
| `match` | Title/quote near the **start** of the **target** page (true section start) |
| `off_by_n` | Section actually starts on a nearby page; set `suggested_page` |
| `wrong` | Window is a different section |
| `not_found` | Not in the window |

Ignore running headers/footers and unit-preview pages that list later lesson titles. A hit on page N−1 that is only a preview is **not** `off_by_n`.

Return JSON `{ "results": [ ...verdicts ] }`.
