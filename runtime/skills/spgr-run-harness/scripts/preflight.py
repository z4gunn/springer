#!/usr/bin/env python3
"""Preflight the tooling a run will need, once, at run open.

A build unit in the reference run lost time discovering that the chromium
wrapper on the machine was broken and that a cached Chrome for Testing build
worked instead. This script answers those questions before any agent is
dispatched and prints a table the harness records in the run brief.

Usage:
    python3 preflight.py [--profile brochure|small|saas|mobile|api]

Prints one line per tool: name, status (ok, missing, broken), detail. Exit 0
always, so a missing optional tool never blocks the run. The harness decides
what to do with a missing required tool. The two design-check tools, the
Playwright CLI for captures and the impeccable detector, are optional: without
them spgr-render-design-comps and the design review axis run on markup alone.
The two document converters, markitdown and docling, are optional too: without
them spgr-ingest-document escalates a binary document to the human.
"""

import glob
import os
import re
import shutil
import subprocess
import sys


def run(cmd, timeout=20):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or p.stderr).strip().splitlines()[0] if (p.stdout or p.stderr).strip() else ""
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)


def check_binary(name, args=("--version",)):
    path = shutil.which(name)
    if not path:
        return "missing", ""
    rc, out = run([path, *args])
    return ("ok" if rc == 0 else "broken"), f"{path} {out}"[:120]


def check_browser():
    """A Chromium-family binary that actually launches headless."""
    candidates = [shutil.which(n) for n in ("chromium", "google-chrome", "chrome", "chromium-browser")]
    candidates += glob.glob(os.path.expanduser("~/.cache/puppeteer/chrome/*/chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"))
    candidates += glob.glob(os.path.expanduser("~/.cache/puppeteer/chrome/*/chrome-linux*/chrome"))
    candidates += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                   "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    for c in candidates:
        if not c or not os.path.exists(c):
            continue
        rc, out = run([c, "--headless=new", "--disable-gpu", "--no-sandbox", "--dump-dom", "about:blank"], timeout=40)
        if rc == 0:
            return "ok", c
    return "missing", "no Chromium-family binary launches headless; Lighthouse and axe cannot run"


def find_impeccable():
    """The impeccable launcher. A global `npx impeccable install` puts it
    inside the skill folder, not on PATH. Same order as design-detect.py."""
    env = os.environ.get("IMPECCABLE_BIN")
    project = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    candidates = [
        env,
        shutil.which("impeccable"),
        os.path.join(project, ".claude", "skills", "impeccable", "scripts", "impeccable"),
        os.path.expanduser("~/.claude/skills/impeccable/scripts/impeccable"),
        os.path.expanduser("~/.impeccable/bin/impeccable"),
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def check_impeccable():
    launcher = find_impeccable()
    if not launcher:
        return "missing", "not on PATH, in a skill install, or in IMPECCABLE_BIN"
    rc, out = run([launcher, "--version"])
    return ("ok" if rc == 0 else "broken"), f"{launcher} {out}"[:120]


def check_venv():
    py = os.path.join(".venv", "bin", "python")
    if not os.path.exists(py):
        return "missing", ".venv absent, schemas/validate.py needs jsonschema"
    rc, _ = run([py, "-c", "import jsonschema, referencing"])
    return ("ok" if rc == 0 else "broken"), py


def scope_detail(status_text):
    """One phrase on whether the gh token can read the repository's security
    alerts. The Dependabot, code-scanning, and secret-scanning reads need the
    security_events scope, which the repo scope includes. A fine-grained token
    prints no scopes line, so its detail says so rather than guessing."""
    for line in status_text.splitlines():
        if "Token scopes:" in line:
            scopes = re.findall(r"'([^']+)'", line)
            if "repo" in scopes or "security_events" in scopes:
                return "scopes include repo, security alerts readable"
            return "scopes lack repo and security_events, security alerts unreadable"
    return "no scopes line, fine-grained token or older gh"


def check_gh():
    if not shutil.which("gh"):
        return "missing", ""
    try:
        p = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "broken", str(exc)[:100]
    text = (p.stdout or "") + (p.stderr or "")
    first = text.strip().splitlines()[0] if text.strip() else ""
    if p.returncode != 0:
        return "broken", first[:100]
    return "ok", f"{first[:60]}, {scope_detail(text)}"


def check_git_identity():
    rc1, name = run(["git", "config", "user.name"])
    rc2, email = run(["git", "config", "user.email"])
    if rc1 or rc2 or not name or not email:
        return "missing", "git user.name or user.email unset"
    return "ok", f"{name} <{email}>"


def main(argv):
    profile = "saas"
    if "--profile" in argv:
        profile = argv[argv.index("--profile") + 1]
    rows = [
        ("python3", *check_binary("python3")),
        ("venv jsonschema", *check_venv()),
        ("git identity", *check_git_identity()),
        ("gh auth", *check_gh()),
        ("node", *check_binary("node")),
        ("npx", *check_binary("npx")),
        ("headless browser", *check_browser()),
        ("playwright-cli (optional)", *check_binary("playwright-cli")),
        ("impeccable (optional)", *check_impeccable()),
        ("markitdown (optional)", *check_binary("markitdown")),
        ("docling (optional)", *check_binary("docling")),
    ]
    if profile in ("saas", "small", "mobile", "api"):
        rows.append(("docker", *check_binary("docker")))
    if profile == "mobile":
        rows.append(("xcodebuild", *check_binary("xcodebuild", ("-version",))))
    width = max(len(r[0]) for r in rows)
    for name, status, detail in rows:
        print(f"{name:{width}}  {status:8} {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
