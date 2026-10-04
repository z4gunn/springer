#!/usr/bin/env python3
"""Preflight the tooling a run will need, once, at run open.

A build unit in the reference run lost time discovering that the chromium
wrapper on the machine was broken and that a cached Chrome for Testing build
worked instead. This script answers those questions before any agent is
dispatched and prints a table the harness records in the run brief.

Usage:
    python3 preflight.py [--profile brochure|small|saas|mobile]

Prints one line per tool: name, status (ok, missing, broken), detail. Exit 0
always, so a missing optional tool never blocks the run. The harness decides
what to do with a missing required tool. The two design-check tools, the
Playwright CLI for captures and the impeccable detector, are optional: without
them spgr-render-design-comps and the design review axis run on markup alone.
"""

import glob
import os
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


def check_venv():
    py = os.path.join(".venv", "bin", "python")
    if not os.path.exists(py):
        return "missing", ".venv absent, schemas/validate.py needs jsonschema"
    rc, _ = run([py, "-c", "import jsonschema, referencing"])
    return ("ok" if rc == 0 else "broken"), py


def check_gh():
    if not shutil.which("gh"):
        return "missing", ""
    rc, out = run(["gh", "auth", "status"])
    return ("ok" if rc == 0 else "broken"), out[:100]


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
        ("impeccable (optional)", *check_binary("impeccable")),
    ]
    if profile in ("saas", "small", "mobile"):
        rows.append(("docker", *check_binary("docker")))
    if profile == "mobile":
        rows.append(("xcodebuild", *check_binary("xcodebuild", ("-version",))))
    width = max(len(r[0]) for r in rows)
    for name, status, detail in rows:
        print(f"{name:{width}}  {status:8} {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
