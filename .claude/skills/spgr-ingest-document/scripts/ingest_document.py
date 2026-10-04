#!/usr/bin/env python3
"""Convert a supplied document into a Markdown source file under docs/inputs/.

Deterministic, no model. A human's spec, brand guide, or content document
arrives as PDF, DOCX, PPTX, or XLSX, and spgr-read-file refuses a binary
file, while the content-sources rule needs every cited fact as text inside the
repository. This script runs the converter, writes the Markdown with a
provenance header, and says how far the extraction can be trusted.

Two engines, both optional. `markitdown` is the default: fast, light, good on
Office formats and clean digital PDFs. `docling` is the escalation for a PDF
whose tables, columns, or scanned pages markitdown mangles. When docling is
absent such a PDF is still written, with extraction_confidence set to
needs-human-input so the PM unit asks the human to confirm the figures rather
than citing them. Markdown, text, and CSV files are copied with the header and
no converter.

Usage:
    ingest_document.py <file>... [--out docs/inputs] [--engine auto|markitdown|docling]
                       [--slug <name>] [--tables] [--force] [--json]

Writes <out>/<slug>.md per input. --slug applies to a single input only. An
existing output with a different source sha256 is a collision and is not
overwritten unless --force.

Exit codes:
    0  every file converted or copied
    1  a file failed or collided
    2  a file needs an engine and none is installed
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

OFFICE = {".docx", ".pptx", ".xlsx", ".xls", ".html", ".htm", ".epub"}
PDF = {".pdf"}
PLAIN = {".md", ".txt", ".csv"}
SUPPORTED = OFFICE | PDF | PLAIN
HEADING = re.compile(r"^#{1,6}\s+\S", re.M)
MIN_CHARS_PER_PAGE_HINT = 200


def run(cmd, timeout=600):
    """Run a command and return (exit_code, stdout, stderr). Never raises."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout or "", p.stderr or ""
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", str(exc)


def find_engine(name):
    """PATH first, then ~/.local/bin, then a project .venv/bin."""
    found = shutil.which(name)
    if found:
        return found
    for base in (Path.home() / ".local" / "bin", Path.cwd() / ".venv" / "bin"):
        candidate = base / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def engine_version(path):
    rc, out, err = run([path, "--version"], timeout=60)
    line = (out or err).strip().splitlines()
    return line[0][:80] if line else ""


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def slugify(stem):
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return slug or "document"


def existing_sha(out_path):
    """The source sha256 recorded in an existing output's header, or None."""
    if not out_path.exists():
        return None
    head = out_path.read_text(errors="replace")[:2000]
    m = re.search(r"^source_sha256:\s*([0-9a-f]{64})\s*$", head, re.M)
    return m.group(1) if m else ""


def provenance(src, digest, converter, version, confidence):
    today = datetime.date.today().isoformat()
    return (
        "---\n"
        f"source_file: {src.name}\n"
        f"source_sha256: {digest}\n"
        f"source_size_bytes: {src.stat().st_size}\n"
        f"converter: {converter}\n"
        f"converter_version: {version or 'n/a'}\n"
        f"retrieved: {today}\n"
        f"extraction_confidence: {confidence}\n"
        "---\n\n"
    )


def looks_thin(text):
    """A conversion with no headings or almost no text is a layout or scan
    failure, not a document with nothing in it."""
    body = text.strip()
    if not body:
        return True
    return len(body) < MIN_CHARS_PER_PAGE_HINT or not HEADING.search(body)


def convert_markitdown(engine, src):
    rc, out, err = run([engine, str(src)])
    return rc, out, err


def convert_docling(engine, src, out_dir):
    """docling writes <stem>.md next to --output. Read it back and remove it,
    so the only durable file is the one this script writes with its header."""
    scratch = out_dir / ".docling-scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    rc, out, err = run([engine, str(src), "--to", "md", "--output", str(scratch)])
    produced = scratch / f"{src.stem}.md"
    text = produced.read_text(errors="replace") if produced.exists() else ""
    shutil.rmtree(scratch, ignore_errors=True)
    if rc == 0 and not text:
        rc, err = 1, err or "docling produced no Markdown file"
    return rc, text, err


def ingest_one(src, out_dir, engine_pref, slug, tables, force, engines):
    ext = src.suffix.lower()
    result = {"file": str(src), "status": "failed", "engine": None, "output": None, "detail": ""}
    if not src.is_file():
        result["detail"] = "file not found"
        return result
    if ext not in SUPPORTED:
        result["detail"] = f"unsupported extension {ext or '(none)'}"
        return result

    digest = sha256_of(src)
    out_path = out_dir / f"{slug or slugify(src.stem)}.md"
    result["output"] = str(out_path)
    prior = existing_sha(out_path)
    if prior is not None and prior != digest and not force:
        result["status"] = "collision"
        result["detail"] = f"{out_path} exists from a different source, pass --force to replace"
        return result

    if ext in PLAIN:
        text = src.read_text(errors="replace")
        if ext == ".csv":
            text = "```csv\n" + text.rstrip("\n") + "\n```\n"
        header = provenance(src, digest, "copy", "", "confirmed")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path.write_text(header + text)
        result.update(status="copied", engine="copy")
        return result

    md, dl = engines["markitdown"], engines["docling"]
    use = engine_pref
    if use == "auto":
        use = "markitdown" if md else ("docling" if dl else None)
    if use is None or (use == "markitdown" and not md) or (use == "docling" and not dl):
        result["status"] = "tool-missing"
        result["detail"] = "no converter installed, pip install 'markitdown[all]' or pip install docling"
        return result

    confidence = "confirmed"
    text, used, version = "", None, ""
    if use == "markitdown":
        rc, text, err = convert_markitdown(md, src)
        if rc != 0:
            result["detail"] = err.strip()[:200] or f"markitdown exit {rc}"
            return result
        used, version = "markitdown", engine_version(md)
        if ext in PDF and (tables or looks_thin(text)):
            if dl and engine_pref == "auto":
                rc, dtext, err = convert_docling(dl, src, out_dir)
                if rc == 0:
                    text, used, version = dtext, "docling", engine_version(dl)
                else:
                    confidence = "needs-human-input"
                    result["detail"] = f"docling failed, kept markitdown output: {err.strip()[:120]}"
            else:
                confidence = "needs-human-input"
                result["detail"] = ("tables requested" if tables else "thin or headingless PDF text") + \
                    " and docling not used, confirm every figure with the human"
    else:
        rc, text, err = convert_docling(dl, src, out_dir)
        if rc != 0:
            result["detail"] = err.strip()[:200] or f"docling exit {rc}"
            return result
        used, version = "docling", engine_version(dl)
        if ext in PDF and looks_thin(text):
            confidence = "needs-human-input"
            result["detail"] = "docling output is thin, likely a scan without OCR"

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(provenance(src, digest, used, version, confidence) + text.rstrip("\n") + "\n")
    result.update(status="converted" if confidence == "confirmed" else "needs-human-input", engine=used)
    return result


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", default="docs/inputs")
    ap.add_argument("--engine", choices=("auto", "markitdown", "docling"), default="auto")
    ap.add_argument("--slug", default=None)
    ap.add_argument("--tables", action="store_true", help="the PDF carries tables that must survive")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv[1:])
    if args.slug and len(args.files) > 1:
        sys.stderr.write("--slug applies to a single input file\n")
        return 1

    engines = {"markitdown": find_engine("markitdown"), "docling": find_engine("docling")}
    out_dir = Path(args.out)
    results = [ingest_one(Path(f), out_dir, args.engine, args.slug, args.tables, args.force, engines)
               for f in args.files]

    statuses = {r["status"] for r in results}
    if "tool-missing" in statuses:
        code = 2
    elif statuses & {"failed", "collision"}:
        code = 1
    else:
        code = 0

    if args.json:
        print(json.dumps({"engines": engines, "results": results, "exit": code}, indent=2))
    else:
        width = max(len(Path(r["file"]).name) for r in results)
        for r in results:
            tail = f" {r['detail']}" if r["detail"] else ""
            print(f"{Path(r['file']).name:{width}}  {r['status']:17} {r['engine'] or '-':10} {r['output'] or ''}{tail}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
