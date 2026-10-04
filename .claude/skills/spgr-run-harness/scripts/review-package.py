#!/usr/bin/env python3
"""Write one review package for a BASE..HEAD range so the diff never enters
the main session.

The harness dispatches a reviewer with a brief, the implementer's report, and
this file. Without it the main session pastes or reads the diff itself, and
in the reference run the main session spent more output tokens than all
subagents combined. The package holds the commit list, the stat, and the
diff with ten lines of context, under a header that records the two SHAs and
whether the working tree was dirty when the package was cut, so a reviewer
can tell what it is grading.

The range is guarded: HEAD must be a descendant of BASE, otherwise the package
is refused, because a diff across unrelated history grades the wrong work.

Usage:
    review-package.py <base> <head> --out <file> [--repo <path>] [--context 10]

Exit 0 when the package was written, 1 when the range was refused, 2 when
git could not answer (not a repository, unknown ref).
"""

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def git(repo, *args):
    """Run git in repo and return (exit_code, stdout). Never raises."""
    try:
        p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=120)
        return p.returncode, p.stdout
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)


def resolve(repo, ref):
    rc, out = git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    return out.strip() if rc == 0 else None


def build_package(repo, base, head, context=10):
    """Return (status, text). status is 'ok', 'refused', or 'error'."""
    base_sha = resolve(repo, base)
    head_sha = resolve(repo, head)
    if not base_sha or not head_sha:
        return "error", f"unknown ref: {'base ' + base if not base_sha else ''}{'head ' + head if not head_sha else ''}".strip()
    rc, _ = git(repo, "merge-base", "--is-ancestor", base_sha, head_sha)
    if rc != 0:
        return "refused", f"{head} is not a descendant of {base}, refusing to package the range"
    _, log = git(repo, "log", "--oneline", "--no-decorate", f"{base_sha}..{head_sha}")
    _, stat = git(repo, "diff", "--stat", base_sha, head_sha)
    _, diff = git(repo, "diff", f"-U{context}", base_sha, head_sha)
    _, dirty = git(repo, "status", "--porcelain")
    lines = [
        "# Review package",
        "",
        f"base: {base} ({base_sha})",
        f"head: {head} ({head_sha})",
        f"cut_at: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"working_tree_dirty: {'true' if dirty.strip() else 'false'}",
        f"commits: {len(log.strip().splitlines()) if log.strip() else 0}",
        "",
        "## Commits",
        "",
        log.rstrip() or "(none)",
        "",
        "## Stat",
        "",
        stat.rstrip() or "(no changes)",
        "",
        f"## Diff (-U{context})",
        "",
        diff.rstrip() or "(no changes)",
        "",
    ]
    return "ok", "\n".join(lines)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base")
    ap.add_argument("head")
    ap.add_argument("--out", required=True)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--context", type=int, default=10)
    a = ap.parse_args(argv[1:])
    rc, _ = git(a.repo, "rev-parse", "--git-dir")
    if rc != 0:
        print(f"review-package: {a.repo} is not a git repository")
        return 2
    status, text = build_package(a.repo, a.base, a.head, a.context)
    if status == "refused":
        print(f"review-package: {text}")
        return 1
    if status == "error":
        print(f"review-package: {text}")
        return 2
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(f"review-package: wrote {out} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
