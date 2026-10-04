#!/usr/bin/env python3
"""Detect a quality bar that a change lowered, from the diff alone.

Deterministic, no model. A review that reads a diff for correctness can miss
the moves that make the bar easier to clear: a linter silenced on one line, a
test skipped or focused, a test file deleted, assertions removed, a stub left
in production code, a hook bypass added to a script, or a coverage threshold
nudged down. This script looks only for those moves, in the lines a change
added or the files it removed, so the Code Reviewer can carry each one as a
finding with a file and line instead of hunting for it. The idea comes from
the floor guard in addyosmani/agent-skills, rewritten for Springer.

Scope is the diff from `git merge-base HEAD <base>` to the working tree plus
untracked files, so it sees staged, unstaged, and committed work on a branch.

Usage:
    floor_guard.py [--repo <path>] [--base origin/main] [--json]

Rules, each reported with file, line, and the matched text:
    suppression   a new lint or type suppression comment, or a
                  @ts-expect-error with no reason
    test-skip     a new skip, only, todo, or xit in a test file
    test-deleted  a deleted test file
    assertions    a modified test file with fewer assertions than before
    stub          TODO, FIXME, NotImplementedError, a not-implemented throw,
                  an empty catch, or except-pass added to non-test source
    hook-bypass   --no-verify or --no-gpg-sign added to a script, hook,
                  workflow, or config
    threshold     a numeric floor loosened in CONSTRAINTS.md, a coverage
                  fail_under, or a coverageThreshold value. Tightening is
                  silent.

A line carrying `floor: keep <reason>` is not a violation. It is listed under
`kept` with its reason so the reviewer still sees it.

Exit 0 when clean, 1 when any violation is found, 2 when the check could not
run (not a git repository, no merge base). Exit 2 means unverified, never
clean.
"""

import argparse
import difflib
import json
import os
import re
import subprocess
import sys

KEEP = re.compile(r"floor:\s*keep\b\s*(.*)$")

SUPPRESSION = re.compile(
    r"eslint-disable|@ts-ignore|@ts-nocheck|#\s*noqa|#\s*type:\s*ignore|"
    r"#\s*pylint:\s*disable|#\s*nosec|//\s*nolint"
)
TS_EXPECT_NO_REASON = re.compile(r"@ts-expect-error\s*$")

SKIP_ANYWHERE = re.compile(
    r"\bxit\(|\bxdescribe\(|\btest\.todo\(|@pytest\.mark\.skip|@unittest\.skip|\bt\.Skip\("
)
SKIP_IN_TESTS = re.compile(r"\.skip\(|\.only\(")

ASSERTION = re.compile(r"\b(assert\w*|expect|should)\b")

STUB = re.compile(
    r"\bTODO\b|\bFIXME\b|NotImplementedError|"
    r"(throw|raise)\b.*not implemented|"
    r"catch\s*(\([^)]*\))?\s*\{\s*\}",
    re.IGNORECASE,
)
EXCEPT_LINE = re.compile(r"^\s*except\b[^:]*:\s*(pass\s*)?$")

HOOK_BYPASS = re.compile(r"--no-verify|--no-gpg-sign")
PROSE_SUFFIXES = (".md", ".txt", ".rst")

TEST_PATH = re.compile(
    r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]*\.py$|_test\.(go|py|rb)$|"
    r"\.(test|spec)\.[a-z]+$|(^|/)conftest\.py$"
)

FLOOR_WORDS_MIN = re.compile(r"\b(at least|minimum|min|over|above|more than|no less than)\b", re.I)
FLOOR_WORDS_MAX = re.compile(r"\b(at most|maximum|max|under|below|less than|no more than|within)\b", re.I)
NUMBER = re.compile(r"\d+(?:\.\d+)?")
FAIL_UNDER = re.compile(r"fail[_-]under\s*[=:]\s*(\d+(?:\.\d+)?)")
COVERAGE_KEY = re.compile(r"\b(branches|functions|lines|statements)\b\s*:\s*(\d+(?:\.\d+)?)")


def git(args, cwd):
    """Run git and return (exit_code, stdout). Never raises."""
    try:
        p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
        return p.returncode, p.stdout
    except OSError as exc:
        return 127, str(exc)


def is_test_path(path):
    return TEST_PATH.search(path) is not None


def read_text(path):
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    if b"\0" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def old_text(root, merge_base, path):
    rc, out = git(["show", f"{merge_base}:{path}"], root)
    return out if rc == 0 else ""


def added_lines(old, new):
    """Yield (line_number, text) for every line present in new but not old."""
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag in ("insert", "replace"):
            for j in range(j1, j2):
                yield j + 1, new_lines[j]


class Report:
    def __init__(self):
        self.violations = []
        self.kept = []

    def add(self, rule, path, line, text):
        m = KEEP.search(text)
        if m:
            self.kept.append({"rule": rule, "file": path, "line": line,
                              "reason": m.group(1).strip() or "no reason given"})
        else:
            self.violations.append({"rule": rule, "file": path, "line": line,
                                    "text": text.strip()[:160]})


def check_added_line(report, path, line_no, text, test_file, new_lines):
    if SUPPRESSION.search(text) or TS_EXPECT_NO_REASON.search(text):
        report.add("suppression", path, line_no, text)
    if SKIP_ANYWHERE.search(text) or (test_file and SKIP_IN_TESTS.search(text)):
        report.add("test-skip", path, line_no, text)
    if not test_file:
        if STUB.search(text):
            report.add("stub", path, line_no, text)
        elif EXCEPT_LINE.match(text):
            stripped = text.strip()
            if stripped.endswith("pass"):
                report.add("stub", path, line_no, text)
            elif line_no < len(new_lines) and new_lines[line_no].strip() == "pass":
                report.add("stub", path, line_no, text)
    if HOOK_BYPASS.search(text) and not path.endswith(PROSE_SUFFIXES):
        report.add("hook-bypass", path, line_no, text)


def check_assertions(report, path, old, new):
    before = len(ASSERTION.findall(old))
    after = len(ASSERTION.findall(new))
    if old and after < before:
        report.add("assertions", path, 0, f"assertions {before} -> {after}")


def floor_values(text):
    """Map a threshold line, with its numbers blanked, to (value, direction).
    direction is 'min' for a floor a decrease loosens and 'max' for a ceiling
    an increase loosens."""
    values = {}
    for line in text.splitlines():
        nums = NUMBER.findall(line)
        if not nums:
            continue
        direction = None
        if FLOOR_WORDS_MIN.search(line):
            direction = "min"
        elif FLOOR_WORDS_MAX.search(line):
            direction = "max"
        if direction is None:
            continue
        key = NUMBER.sub("#", line).strip()
        values[key] = (float(nums[0]), direction, line.strip())
    return values


def check_thresholds(report, path, old, new):
    name = os.path.basename(path)
    if name == "CONSTRAINTS.md":
        before = floor_values(old)
        after = floor_values(new)
        for key, (val, direction, line) in after.items():
            if key not in before:
                continue
            prev = before[key][0]
            loosened = (direction == "min" and val < prev) or (direction == "max" and val > prev)
            if loosened:
                report.add("threshold", path, line_number_of(new, line), f"{prev:g} -> {val:g}: {line}")
        return
    for pattern in (FAIL_UNDER,):
        olds = [float(v) for v in pattern.findall(old)]
        news = pattern.findall(new)
        if olds and news and float(news[0]) < olds[0]:
            line = next((l for l in new.splitlines() if pattern.search(l)), "")
            report.add("threshold", path, line_number_of(new, line), f"fail_under {olds[0]:g} -> {float(news[0]):g}")
    if "coverageThreshold" in old and "coverageThreshold" in new:
        before = {k: float(v) for k, v in COVERAGE_KEY.findall(old)}
        for line_no, line in enumerate(new.splitlines(), 1):
            for key, value in COVERAGE_KEY.findall(line):
                if key in before and float(value) < before[key]:
                    report.add("threshold", path, line_no, f"coverageThreshold {key} {before[key]:g} -> {float(value):g}")


def line_number_of(text, line):
    for i, candidate in enumerate(text.splitlines(), 1):
        if candidate.strip() == line.strip():
            return i
    return 0


def changed_files(root, merge_base):
    """Return ([(status, path)], untracked_paths)."""
    rc, out = git(["diff", "--name-status", "-M", merge_base], root)
    if rc != 0:
        return None, None
    entries = []
    for row in out.splitlines():
        parts = row.split("\t")
        status = parts[0][0]
        path = parts[-1]
        entries.append((status, path))
    rc, out = git(["ls-files", "--others", "--exclude-standard"], root)
    untracked = out.splitlines() if rc == 0 else []
    return entries, untracked


def resolve_merge_base(root, base):
    for candidate in (base, "main"):
        rc, out = git(["merge-base", "HEAD", candidate], root)
        if rc == 0 and out.strip():
            return candidate, out.strip()
    return None, None


def run_check(root, base):
    base_used, merge_base = resolve_merge_base(root, base)
    if merge_base is None:
        return None
    entries, untracked = changed_files(root, merge_base)
    if entries is None:
        return None
    report = Report()
    seen = set()
    for status, path in entries:
        seen.add(path)
        if status == "D":
            if is_test_path(path):
                report.add("test-deleted", path, 0, path)
            continue
        new = read_text(os.path.join(root, path))
        if new is None:
            continue
        old = old_text(root, merge_base, path)
        scan_file(report, path, old, new)
    for path in untracked:
        if path in seen:
            continue
        new = read_text(os.path.join(root, path))
        if new is None:
            continue
        scan_file(report, path, "", new)
    return {"base": base_used, "merge_base": merge_base,
            "violations": report.violations, "kept": report.kept}


def scan_file(report, path, old, new):
    test_file = is_test_path(path)
    new_lines = new.splitlines()
    for line_no, text in added_lines(old, new):
        check_added_line(report, path, line_no, text, test_file, new_lines)
    if test_file:
        check_assertions(report, path, old, new)
    check_thresholds(report, path, old, new)


def print_table(result):
    print(f"floor-guard: base {result['base']} at {result['merge_base'][:12]}")
    for v in result["violations"]:
        where = f"{v['file']}:{v['line']}" if v["line"] else v["file"]
        print(f"  {v['rule']:13} {where}  {v['text']}")
    for k in result["kept"]:
        where = f"{k['file']}:{k['line']}" if k["line"] else k["file"]
        print(f"  kept {k['rule']:8} {where}  {k['reason']}")
    print(f"floor-guard: {result['status']} ({len(result['violations'])} violation(s), {len(result['kept'])} kept)")


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=os.getcwd())
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv[1:])

    rc, out = git(["rev-parse", "--show-toplevel"], args.repo)
    if rc != 0 or not out.strip():
        result = {"status": "unverified", "reason": "not a git repository", "violations": [], "kept": []}
        print(json.dumps(result) if args.json else f"floor-guard: unverified, {result['reason']}")
        return 2
    root = out.strip()
    result = run_check(root, args.base)
    if result is None:
        result = {"status": "unverified", "reason": f"no merge base with {args.base} or main",
                  "violations": [], "kept": []}
        print(json.dumps(result) if args.json else f"floor-guard: unverified, {result['reason']}")
        return 2
    result["status"] = "violation" if result["violations"] else "clean"
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_table(result)
    return 1 if result["violations"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
