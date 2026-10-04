---
name: spgr-ingest-document
description: Convert a human-supplied PDF, DOCX, PPTX, XLSX, HTML, or EPUB into a Markdown source file under docs/inputs/ with a provenance header and an extraction-confidence signal. Use when a spec, brand guide, or content document arrives as a file the content-sources rule needs in-repo as text, before the PM unit cites any fact from it.
---

# ingest-document

## Purpose

The content-sources rule says every fact a build cites has an in-repo source under `docs/inputs/`, and spgr-read-file refuses a binary file. A spec or brand guide the human hands over as a PDF or DOCX therefore has no readable in-repo form until it is converted. This skill runs that conversion once, deterministically, and records where the text came from and how far it can be trusted, so a figure extracted from a mangled table becomes an intake question rather than a cited fact. It is mechanical and needs no reasoning budget.

## Inputs

| Field | Description |
|-------|-------------|
| `files` | One or more paths to the supplied documents. Supported: pdf, docx, pptx, xlsx, xls, html, htm, epub, md, txt, csv |
| `out` | Output directory, default `docs/inputs/` |
| `engine` | `auto` (default), `markitdown`, or `docling`. Under `auto` markitdown runs first and a PDF escalates to docling when it is installed and the markitdown output is thin |
| `slug` | Optional output name for a single file. Default is the file stem, lowercased and hyphenated |
| `tables` | Set when a PDF carries tables whose figures must survive. Forces the docling escalation, or marks the output needs-human-input when docling is absent |
| `force` | Replace an existing output written from a different source file |

## Outputs

| Artifact | Description |
|----------|-------------|
| `docs/inputs/<slug>.md` | The converted Markdown, opening with a YAML provenance block: source file name, sha256, size, converter and version, retrieved date, and `extraction_confidence` of `confirmed` or `needs-human-input` |
| `ingest_report` | The script's JSON report under `--json`: per file status (`converted`, `copied`, `needs-human-input`, `collision`, `tool-missing`, `failed`), the engine used, and the output path |

## Procedure

1. Run the script over every supplied document, from the project root:

   ```bash
   python3 .claude/skills/spgr-ingest-document/scripts/ingest_document.py <file>... --out docs/inputs --json
   ```

   Pass `--tables` for a PDF whose figures live in tables. Pass `--slug` only when converting one file whose stem would not make a readable name.

2. Read the report. Exit 0 means every file converted or copied. Exit 1 means a file failed or collided with an existing output from a different source, so read the detail, and pass `--force` only when the new file is meant to replace the old one. Exit 2 means a file needs a converter and none is installed.

3. On exit 2, stop and raise spgr-escalate naming the file and the two ways forward: the human supplies the text (a Markdown or DOCX export, or the facts typed into the intake answer), or an engine is installed with `pip install 'markitdown[all]'` (about 80 MB, no models) or `pip install docling` (over a gigabyte with its layout and table models, and the one that reads scans and multi-column tables correctly). Never transcribe a binary document from memory or from a thumbnail.

4. Hand every output whose `extraction_confidence` is `needs-human-input` to the PM unit as an intake question per figure, date, name, and URL it carries. Those values are not cited until the human confirms them. An output marked `confirmed` is a citable in-repo source, and the PM unit registers each fact it cites in the PRD content-sources table with the `docs/inputs/<slug>.md` path.

5. Record the engine used and any escalation or fallback with spgr-log-decision. Commit the outputs with the intake artifacts, since they are the sources the run cites.

## Notes

- A Google Doc enters by its DOCX or Markdown export, a Notion page by its Markdown export, and both then run through this skill so the provenance header exists. The MCP servers for those products are interactive tools for a human, not a harness channel.
- The provenance header is the collision guard. An output whose recorded sha256 differs from the new source is never silently replaced.
- markitdown is text-stream extraction with no layout model. It is right for Office formats, HTML, and clean digital PDFs, and wrong for scanned pages and multi-column or table-heavy PDFs, which is why the escalation and the confidence signal exist. docling is the escalation engine, not the default, because of its install weight and speed.
- Both engines are optional. `preflight.py` reports them as optional rows at run open, and `templates/project-settings.json` allowlists both commands and this script.
- The script is deterministic and runs with no model. Dispatch it at the deterministic tier.
- This skill has no Phase 1 vault spec. It was authored to the Springer build standards as a net-new capability.
