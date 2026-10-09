# pdf-skills

Agent skills for PDFs. The agent runs the workflow; the Python scripts never call a model.

- **add-pdf-toc** adds a hierarchical bookmark outline (sidebar table of contents). The default depth is the printed TOC. Deeper headings use a full text extract of each in-scope chapter.
- **add-pdf-ocr** adds an invisible text layer so a scanned PDF becomes searchable. It does not add bookmarks.

## Install

Requires [Node.js](https://nodejs.org/) so `npx` works. No skills.sh account and no marketplace submission.

```bash
# This repo, user-level skills (any project)
npx skills add . -g

# After the repo is on GitHub
npx skills add KIDPhantom1412/pdf-skills -g
```

List what the installer sees:

```bash
npx skills add . --list
```

Without Node, copy `skills/add-pdf-toc/` and `skills/add-pdf-ocr/` to the user-level `~/.agents/skills/` (or the current project's `.agents/skills/`).

## Use

In your coding agent's chat, ask for example:

> Add a table of contents to `D:\books\example.pdf`

The agent should load **add-pdf-toc** and run `uv run scripts/addpdftoc.py ...` (uv is required). The default outline matches the printed TOC. Deeper headings come from a full text extract of each in-scope chapter (OCR on a scan, `extract` when a text layer already exists), then entries are verified against page text.

> Add an OCR text layer to `D:\books\example.pdf`

The agent should load **add-pdf-ocr** and run `uv run scripts/addpdfocr.py ...`. The searchable file is `<stem>.ocr.pdf` next to the source.

## Layout

```text
skills/add-pdf-toc/
  SKILL.md
  scripts/addpdftoc.py
  scripts/ocr_engine.py
  scripts/requirements.txt
  references/artifacts.md
  references/language.md
  references/subagents.md
skills/add-pdf-ocr/
  SKILL.md
  scripts/addpdfocr.py
  scripts/ocr_engine.py
  scripts/requirements.txt
  references/artifacts.md
  references/language.md
```

`ocr_engine.py` and `references/language.md` are the same file in both skills so each skill still works if it is installed alone. The copies under `add-pdf-ocr` are canonical.

## Runtime

- **[uv](https://docs.astral.sh/uv/)** (`uv run` reads the script's PEP 723 deps).

## License

MIT
