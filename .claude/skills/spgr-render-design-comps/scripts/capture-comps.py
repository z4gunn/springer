#!/usr/bin/env python3
"""Capture design comps or built routes across a width and color-scheme matrix,
and run the slop detector when it is installed.

Deterministic, no model. Drives the Playwright CLI (`playwright-cli`, the
@playwright/cli package) to render each page headless at every width and
scheme and write a PNG, then runs `impeccable detect --json` over a file or
directory target when the binary is on PATH. Both tools are optional. When one
is missing the report says so and the script still exits 0, so a missing tool
never blocks a unit. The calling skill reads capture-report.json and decides
what the critique can cover.

Usage:
    capture-comps.py <target> --out <dir> [--widths 375,768,1440]
                     [--schemes light,dark] [--height 900]
                     [--reduced-motion] [--no-detect]

<target> is an .html file, a directory of .html files, or an http(s) URL.
Writes <out>/<page>-<width>-<scheme>.png per cell, <out>/detect.json when the
detector ran, and <out>/capture-report.json always.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_WIDTHS = "375,768,1440"
DEFAULT_SCHEMES = "light,dark"
DEFAULT_HEIGHT = 900
CLI = "playwright-cli"
DETECTOR = "impeccable"


def run(cmd, timeout=120, cwd=None):
    """Run a command and return (exit_code, combined_output). Never raises."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)


def tool_status(name):
    return "ok" if shutil.which(name) else "missing"


def resolve_pages(target):
    """Return (kind, [(name, url)]) for a file, a directory, or a URL."""
    if target.startswith("http://") or target.startswith("https://"):
        path = urlparse(target).path.strip("/")
        name = (path.replace("/", "-") or "page")
        return "url", [(name, target)]
    p = Path(target).resolve()
    if p.is_dir():
        pages = [(f.stem, f.as_uri()) for f in sorted(p.glob("*.html"))]
        return "dir", pages
    if p.is_file():
        return "file", [(p.stem, p.as_uri())]
    raise FileNotFoundError(target)


def locate_shot(expected, out_dir, cwd):
    """The CLI writes under its own output dir on some versions. Find the file
    and move it to the expected path."""
    expected = Path(expected)
    if expected.exists():
        return True
    for candidate in (Path(cwd) / ".playwright-cli" / expected.name,
                      Path(out_dir) / expected.name,
                      Path(cwd) / expected.name):
        if candidate.exists() and candidate != expected:
            shutil.move(str(candidate), str(expected))
            return True
    return False


def capture(pages, out_dir, widths, schemes, height, reduced_motion, cwd):
    shots = []
    failures = []
    for name, url in pages:
        rc, out = run([CLI, "open", url], cwd=cwd)
        if rc != 0:
            failures.append({"page": name, "step": "open", "output": out[-400:]})
            continue
        for width in widths:
            rc, out = run([CLI, "resize", str(width), str(height)], cwd=cwd)
            if rc != 0:
                failures.append({"page": name, "step": f"resize {width}", "output": out[-400:]})
            for scheme in schemes:
                run([CLI, "set-color-scheme", scheme], cwd=cwd)
                if reduced_motion:
                    run([CLI, "set-reduced-motion", "reduce"], cwd=cwd)
                shot = Path(out_dir) / f"{name}-{width}-{scheme}.png"
                rc, out = run([CLI, "screenshot", f"--filename={shot}"], cwd=cwd)
                ok = rc == 0 and locate_shot(shot, out_dir, cwd)
                shots.append({"page": name, "width": width, "scheme": scheme,
                              "path": str(shot), "ok": ok})
                if not ok:
                    failures.append({"page": name, "step": f"screenshot {width} {scheme}",
                                     "output": out[-400:]})
        run([CLI, "close"], cwd=cwd)
    return shots, failures


def count_findings(parsed):
    if isinstance(parsed, list):
        return len(parsed)
    if isinstance(parsed, dict):
        for key in ("findings", "results", "issues"):
            if isinstance(parsed.get(key), list):
                return len(parsed[key])
        if "count" in parsed and isinstance(parsed["count"], int):
            return parsed["count"]
    return None


def detect(target, out_dir, cwd):
    rc, out = run([DETECTOR, "detect", target, "--json"], timeout=300, cwd=cwd)
    out_path = Path(out_dir) / "detect.json"
    parsed = None
    text = out.strip()
    # The engine may print a status line before the JSON. Take the last JSON object or array.
    for start in (text.find("{"), text.find("[")):
        if start >= 0:
            try:
                parsed = json.loads(text[start:])
                break
            except json.JSONDecodeError:
                continue
    out_path.write_text(json.dumps(parsed, indent=2) if parsed is not None else text)
    return {"ran": True, "exit_code": rc, "findings_count": count_findings(parsed),
            "output_path": str(out_path)}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target")
    ap.add_argument("--out", required=True)
    ap.add_argument("--widths", default=DEFAULT_WIDTHS)
    ap.add_argument("--schemes", default=DEFAULT_SCHEMES)
    ap.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    ap.add_argument("--reduced-motion", action="store_true")
    ap.add_argument("--no-detect", action="store_true")
    args = ap.parse_args(argv)

    widths = [int(w) for w in args.widths.split(",") if w.strip()]
    schemes = [s.strip() for s in args.schemes.split(",") if s.strip()]
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    cwd = os.getcwd()

    try:
        kind, pages = resolve_pages(args.target)
    except FileNotFoundError:
        print(f"target not found: {args.target}", file=sys.stderr)
        return 2

    tools = {CLI: tool_status(CLI), DETECTOR: tool_status(DETECTOR)}
    report = {"target": args.target, "kind": kind, "tools": tools,
              "pages": [name for name, _ in pages], "widths": widths, "schemes": schemes,
              "reduced_motion": args.reduced_motion, "shots": [], "failures": [],
              "detect": {"ran": False}}

    if tools[CLI] == "ok" and pages:
        report["shots"], report["failures"] = capture(
            pages, out_dir, widths, schemes, args.height, args.reduced_motion, cwd)
    elif tools[CLI] != "ok":
        report["failures"].append({"step": "capture",
                                   "output": f"{CLI} not on PATH, no screenshots taken"})

    if not args.no_detect and tools[DETECTOR] == "ok":
        report["detect"] = detect(args.target, out_dir, cwd)

    report_path = out_dir / "capture-report.json"
    report_path.write_text(json.dumps(report, indent=2))

    taken = sum(1 for s in report["shots"] if s["ok"])
    print(f"pages {len(pages)}  shots {taken}/{len(report['shots'])}  "
          f"{CLI} {tools[CLI]}  {DETECTOR} {tools[DETECTOR]}")
    if report["detect"]["ran"]:
        print(f"detector exit {report['detect']['exit_code']}  "
              f"findings {report['detect']['findings_count']}  {report['detect']['output_path']}")
    for f in report["failures"]:
        print(f"failure  {f.get('page', '')} {f['step']}: {f['output'].splitlines()[-1] if f['output'] else ''}")
    print(f"report {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
