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

The package opens with the gate-integrity tags: every change a script can see
that makes a gate easier to pass rather than the code better. A removed or
skipped test, a net loss of assertions in a test file, an edit to lint, type,
test-runner, or CI configuration, a new suppression comment, an edited
snapshot or real fixture or product-check list, a file outside the story's
touch paths, and source that landed before its test. A tag is not a verdict.
The reviewer gives each one a disposition in the code-review `gate_tags`
list, and `dispositions` refuses a review that skipped one. The tags are also
written beside the package as <out>.tags.json.

Usage:
    review-package.py <base> <head> --out <file> [--repo <path>] [--context 10]
                      [--touch-paths <prefix>...]
    review-package.py dispositions <tags.json> <code-review.json>

Exit 0 when the package was written, 1 when the range was refused, 2 when
git could not answer (not a repository, unknown ref). dispositions exits 0
when every tag has a disposition with a reason, 1 when any is missing.
"""

import argparse
import json
import re
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


TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec|e2e)/|\.(test|spec)\.[A-Za-z0-9]+$|_test\.(go|py)$|(^|/)test_[^/]*\.py$")
CHECK_CONFIG = re.compile(
    r"(^|/)(tsconfig[^/]*\.json|\.eslintrc[^/]*|eslint\.config\.[^/]+|\.prettierrc[^/]*|prettier\.config\.[^/]+"
    r"|biome\.jsonc?|\.golangci\.ya?ml|ruff\.toml|\.flake8|mypy\.ini|\.pylintrc|\.pre-commit-config\.ya?ml"
    r"|(jest|vitest|playwright)\.config\.[^/]+|\.nycrc[^/]*|\.c8rc[^/]*|codecov\.ya?ml|lefthook\.ya?ml)$"
    r"|(^|/)\.github/workflows/|(^|/)\.husky/|(^|/)\.claude/(settings\.json|hooks/)")
GOLDEN = re.compile(r"(^|/)__snapshots__/|\.snap$|(^|/)golden/|(^|/)tests/fixtures/real/|(^|/)runs/_product-check\.json$")
SKIP = re.compile(r"\b(it|test|describe)\.(skip|only|todo)\(|\bx(it|describe|test)\(|@pytest\.mark\.(skip|xfail)"
                  r"|@unittest\.skip|\bt\.Skip\(|\.only\(")
SUPPRESSION = re.compile(r"eslint-disable|@ts-ignore|@ts-expect-error|@ts-nocheck|#\s*noqa|#\s*type:\s*ignore"
                         r"|nosemgrep|istanbul ignore|c8 ignore|pragma: no cover|NOLINT|//\s*nolint")
TEST_DECL = re.compile(r"^\s*(async\s+)?def test_|^\s*func Test|^\s*(it|test|describe)\(")
ASSERTION = re.compile(r"\bassert|\bexpect\(|\.should\b|\brequire\.")
NOT_SOURCE = re.compile(r"\.(md|txt|rst)$|(^|/)(runs|docs)/")
HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def changed_lines(diff_u0):
    """Yield (path, sign, line_number, text) for every added or removed line
    of a -U0 diff. Removed lines carry the old line number."""
    path, old, new = None, 0, 0
    for line in diff_u0.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("--- "):
            continue
        elif line.startswith("@@"):
            m = HUNK.match(line)
            if m:
                old, new = int(m.group(1)), int(m.group(2))
        elif path and line.startswith("+"):
            yield path, "+", new, line[1:]
            new += 1
        elif path and line.startswith("-"):
            yield path, "-", old, line[1:]
            old += 1


def gate_tags(repo, base_sha, head_sha, touch_paths=None):
    """Every change in the range that eases a gate, as a list of tags."""
    tags = []

    def tag(kind, path, line, detail):
        tags.append({"id": f"GI-{len(tags) + 1}", "tag": kind, "file": path, "line": line, "detail": detail})

    _, status = git(repo, "diff", "--name-status", "--no-renames", base_sha, head_sha)
    files = []
    for row in status.splitlines():
        parts = row.split("\t")
        if len(parts) >= 2:
            files.append((parts[0][0], parts[-1]))
    for st, path in files:
        if TEST_PATH.search(path) and st == "D":
            tag("TEST-REMOVED", path, None, "test file deleted")
        if CHECK_CONFIG.search(path):
            tag("CHECK-CONFIG", path, None, f"check configuration {'added' if st == 'A' else 'changed'}")
        if GOLDEN.search(path) and st in ("M", "D"):
            tag("GOLDEN-EDITED", path, None, "snapshot, real fixture, or product-check list "
                                             + ("deleted" if st == "D" else "edited"))
        if touch_paths and not path.startswith("runs/") and \
                not any(path.startswith(p.lstrip("./")) for p in touch_paths):
            tag("OUT-OF-SCOPE", path, None, "outside the story's touch paths")

    deleted = {p for st, p in files if st == "D"}
    _, diff = git(repo, "diff", "-U0", "--no-renames", base_sha, head_sha)
    asserts = {}
    for path, sign, line, text in changed_lines(diff):
        is_test = bool(TEST_PATH.search(path))
        if sign == "+" and SKIP.search(text):
            tag("TEST-SKIPPED", path, line, text.strip()[:160])
        if sign == "+" and SUPPRESSION.search(text):
            tag("SUPPRESSION", path, line, text.strip()[:160])
        if is_test and path not in deleted:
            if sign == "-" and TEST_DECL.search(text):
                tag("TEST-REMOVED", path, line, text.strip()[:160])
            if ASSERTION.search(text):
                pair = asserts.setdefault(path, [0, 0])
                pair[0 if sign == "+" else 1] += 1
    for path, (added, removed) in sorted(asserts.items()):
        if removed > added:
            tag("ASSERTION-LOSS", path, None, f"{removed} assertion lines removed, {added} added")

    _, log = git(repo, "log", "--reverse", "--format=%x00%H", "--name-only", f"{base_sha}..{head_sha}")
    first_test = first_source = None
    for index, block in enumerate(c for c in log.split("\0") if c.strip()):
        paths = [p for p in block.splitlines()[1:] if p.strip()]
        if first_test is None and any(TEST_PATH.search(p) for p in paths):
            first_test = index
        if first_source is None and any(not TEST_PATH.search(p) and not CHECK_CONFIG.search(p)
                                        and not NOT_SOURCE.search(p) for p in paths):
            first_source = index
    if first_source is not None:
        if first_test is None:
            tag("TEST-ORDER", None, None, "source changed and no test changed in the range")
        elif first_source < first_test:
            tag("TEST-ORDER", None, None, f"source landed in commit {first_source + 1} before the first "
                                          f"test change in commit {first_test + 1}")
    return tags


def render_tags(tags):
    if not tags:
        return ["(none)"]
    out = []
    for t in tags:
        where = t["file"] or "range"
        if t["line"]:
            where += f":{t['line']}"
        out.append(f"- {t['id']} {t['tag']} {where}: {t['detail']}")
    return out


def build_package(repo, base, head, context=10, touch_paths=None):
    """Return (status, text, tags). status is 'ok', 'refused', or 'error'."""
    base_sha = resolve(repo, base)
    head_sha = resolve(repo, head)
    if not base_sha or not head_sha:
        return "error", f"unknown ref: {'base ' + base if not base_sha else ''}{'head ' + head if not head_sha else ''}".strip(), []
    rc, _ = git(repo, "merge-base", "--is-ancestor", base_sha, head_sha)
    if rc != 0:
        return "refused", f"{head} is not a descendant of {base}, refusing to package the range", []
    tags = gate_tags(repo, base_sha, head_sha, touch_paths)
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
        f"gate_tags: {len(tags)}",
        "",
        "## Gate integrity",
        "",
        "Give every tag a disposition in the code-review gate_tags list: accepted with the reason it is",
        "right for this story, or a finding.",
        "",
        *render_tags(tags),
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
    return "ok", "\n".join(lines), tags


def check_dispositions(tags_path, review_path):
    """Return the list of problems: a tag with no disposition, or one with no
    reason. The review is an envelope artifact or its bare content."""
    tags = json.loads(Path(tags_path).read_text())
    review = json.loads(Path(review_path).read_text())
    content = review.get("content", review)
    given = {d.get("id"): d for d in content.get("gate_tags", []) if isinstance(d, dict)}
    problems = []
    for t in tags:
        d = given.get(t["id"])
        if d is None:
            problems.append(f"{t['id']} {t['tag']} has no disposition")
        elif d.get("disposition") not in ("accepted", "finding") or not str(d.get("reason", "")).strip():
            problems.append(f"{t['id']} {t['tag']} needs a disposition of accepted or finding with a reason")
    return problems


def main(argv):
    if len(argv) > 1 and argv[1] == "dispositions":
        if len(argv) != 4:
            print("usage: review-package.py dispositions <tags.json> <code-review.json>")
            return 2
        try:
            problems = check_dispositions(argv[2], argv[3])
        except (OSError, json.JSONDecodeError) as exc:
            print(f"review-package: cannot read {exc}")
            return 2
        for p in problems:
            print(f"review-package: {p}")
        print(f"review-package: {'every gate tag has a disposition' if not problems else f'{len(problems)} gate tag(s) unresolved'}")
        return 1 if problems else 0
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base")
    ap.add_argument("head")
    ap.add_argument("--out", required=True)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--context", type=int, default=10)
    ap.add_argument("--touch-paths", nargs="*", default=None)
    a = ap.parse_args(argv[1:])
    rc, _ = git(a.repo, "rev-parse", "--git-dir")
    if rc != 0:
        print(f"review-package: {a.repo} is not a git repository")
        return 2
    status, text, tags = build_package(a.repo, a.base, a.head, a.context, a.touch_paths)
    if status == "refused":
        print(f"review-package: {text}")
        return 1
    if status == "error":
        print(f"review-package: {text}")
        return 2
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    tags_path = out.with_name(out.name + ".tags.json")
    tags_path.write_text(json.dumps(tags, indent=2) + "\n")
    print(f"review-package: wrote {out} ({len(text.splitlines())} lines, {len(tags)} gate tag(s) in {tags_path.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
