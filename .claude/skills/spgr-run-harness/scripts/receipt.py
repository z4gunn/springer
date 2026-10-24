#!/usr/bin/env python3
"""Record what a gating command did, and refuse evidence that no longer holds.

A unit report used to paste its verification output, and Check re-derived
the commit and tree fingerprint by hand to decide whether the paste still
described the code. That is a rule a model has to remember. This script makes
it a file: `run` executes the gating command and writes a receipt carrying the
exit code, the number of tests that actually ran, the commit, and a
fingerprint of the working tree. `verify` reads the receipts of one or more
units and fails any that did not pass, ran zero tests, or describe a commit or
tree other than the one in front of it. The pr-merge gate does not open on a
failed verify. Stdlib only.

A test command that exits 0 having run nothing is the failure this exists to
catch: a filter that matches no file, a runner pointed at an empty directory,
a skip that swallowed the suite. A `test` receipt therefore needs a count
read from the runner's own output, and zero is `zero-run`, never `pass`. A
count the script cannot read is `unknown-count`, which also fails, so a new
runner gets a `--count-regex` rather than a free pass.

Usage:
    receipt.py run <unit-dir> --name <name> [--kind test|check|product]
                   [--cwd <dir>] [--count-regex <regex>] [--timeout <s>] -- <command...>
    receipt.py verify <unit-dir>... [--cwd <dir>] [--require <kind>]...

`run` writes <unit-dir>/receipts/<name>.json and passes the command's output
through. `kind` is `test` (the default, needs a count above zero), `check`
(lint, typecheck, build: the exit code alone), or `product` (written by
product-check.py). Run gating commands after committing, so the receipt names
the commit the PR will carry. The fingerprint covers tracked changes and
untracked files outside `runs/` and `.worktrees/`, because the run store is
where the receipts themselves land.

Exit codes. run: the command's own exit code when it ran, 1 when it passed but
the receipt did not (zero-run, unknown-count), 2 on usage. verify: 0 when every
receipt holds, 1 when any does not or a required kind is missing, 2 on usage.
"""

import datetime
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

OUTPUT_TAIL = 2000
DEFAULT_TIMEOUT = 1800
KINDS = ("test", "check", "product")
EXCLUDE = (":(exclude)runs", ":(exclude).worktrees")

# Each runner's own summary line. The largest count any of them reports is the
# count, so a runner that prints both a per-file and a total line is read once.
COUNT_PATTERNS = [
    r"\bRan (\d+) tests?\b",                          # unittest
    r"\b(\d+) passed\b",                              # pytest, vitest, playwright
    r"\bTests:\s+(?:.*?,\s*)?(\d+) total\b",          # jest
    r"\b(\d+) passing\b",                             # mocha
    r"^# (?:tests|pass) (\d+)$",                      # node --test, tap
    r"test result: \w+\. (\d+) passed",               # cargo
    r"\b(\d+) examples?, \d+ failures?",              # rspec
    r"^--- PASS: ",                                   # go test -v, counted per line
]
ZERO_SIGNALS = [
    r"\bno tests ran\b", r"\bcollected 0 items\b", r"\bNo tests found\b",
    r"\[no test files\]", r"\bRan 0 tests\b", r"\b0 passing\b",
]


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def git(cwd, *args):
    try:
        p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, timeout=60)
        return p.returncode, p.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 127, b""


def head_sha(cwd):
    rc, out = git(cwd, "rev-parse", "HEAD")
    return out.decode().strip() if rc == 0 else None


def fingerprint(cwd):
    """A hash of everything uncommitted outside the run store: the tracked
    diff against HEAD, and the path and content of every untracked file."""
    h = hashlib.sha256()
    _, diff = git(cwd, "diff", "HEAD", "--binary", "--", ".", *EXCLUDE)
    h.update(diff)
    _, untracked = git(cwd, "ls-files", "--others", "--exclude-standard", "-z", "--", ".", *EXCLUDE)
    for rel in sorted(p for p in untracked.decode(errors="replace").split("\0") if p):
        h.update(rel.encode() + b"\0")
        try:
            h.update((Path(cwd) / rel).read_bytes())
        except OSError:
            pass
    return "sha256:" + h.hexdigest()


def count_tests(output, count_regex=None):
    """The number of tests the runner says ran, 0 when it says none ran, or
    None when no known summary line is present."""
    if count_regex:
        found = [int(m) for m in re.findall(count_regex, output, re.M) if str(m).isdigit()]
        return max(found) if found else None
    if any(re.search(p, output, re.M | re.I) for p in ZERO_SIGNALS):
        counts = []
    else:
        counts = None
    for pattern in COUNT_PATTERNS:
        if pattern.startswith("^--- PASS"):
            n = len(re.findall(pattern, output, re.M))
            if n:
                counts = (counts or []) + [n]
            continue
        found = [int(m) for m in re.findall(pattern, output, re.M)]
        if found:
            counts = (counts or []) + found
    if counts is None:
        return None
    return max(counts) if counts else 0


def judge(kind, exit_code, tests_ran):
    if exit_code is None:
        return "error"
    if exit_code != 0:
        return "fail"
    if kind in ("test", "product"):
        if tests_ran is None:
            return "unknown-count"
        if tests_ran == 0:
            return "zero-run"
    return "pass"


def write_receipt(unit_dir, name, body):
    out = Path(unit_dir) / "receipts" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(body, indent=2) + "\n")
    return out


def make_receipt(name, kind, command, cwd, exit_code, tests_ran, output, duration, started):
    return {
        "receipt": 1,
        "name": name,
        "kind": kind,
        "command": command,
        "cwd": str(Path(cwd).resolve()),
        "head": head_sha(cwd),
        "fingerprint": fingerprint(cwd),
        "exit_code": exit_code,
        "tests_ran": tests_ran,
        "result": judge(kind, exit_code, tests_ran),
        "started_at": started,
        "duration_s": round(duration, 1),
        "output_tail": output[-OUTPUT_TAIL:],
    }


def cmd_run(unit_dir, name, kind, cwd, count_regex, timeout, command):
    started, t0 = now_iso(), time.monotonic()
    shell_cmd = command[0] if len(command) == 1 else subprocess.list2cmdline(command)
    try:
        proc = subprocess.run(shell_cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        exit_code, output = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        exit_code = None
        partial = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        output = f"timed out after {timeout}s\n" + partial
    except OSError as exc:
        exit_code, output = None, str(exc)
    sys.stdout.write(output)
    tests_ran = count_tests(output, count_regex) if kind == "test" else None
    body = make_receipt(name, kind, shell_cmd, cwd, exit_code, tests_ran, output,
                        time.monotonic() - t0, started)
    path = write_receipt(unit_dir, name, body)
    print(f"\nreceipt: {body['result']} {name} (exit {exit_code}, tests {tests_ran}) at {body['head']}, "
          f"written to {path}")
    if body["result"] == "pass":
        return 0
    return exit_code if exit_code not in (None, 0) else 1


def load_receipts(unit_dir):
    out = []
    for path in sorted((Path(unit_dir) / "receipts").glob("*.json")):
        try:
            out.append((path, json.loads(path.read_text())))
        except (OSError, json.JSONDecodeError) as exc:
            out.append((path, {"name": path.stem, "result": f"unreadable ({exc})"}))
    return out


def cmd_verify(unit_dirs, cwd, required):
    head, tree = head_sha(cwd), fingerprint(cwd)
    problems, seen_kinds, lines = [], {}, []
    for unit_dir in unit_dirs:
        receipts = load_receipts(unit_dir)
        if not receipts:
            problems.append(f"{unit_dir}: no receipts")
        kinds = set()
        for path, r in receipts:
            label = f"{Path(unit_dir).name}/{r.get('name')}"
            why = []
            if r.get("result") != "pass":
                why.append(str(r.get("result")))
            if r.get("head") != head:
                why.append(f"stale commit {str(r.get('head'))[:12]} (HEAD is {str(head)[:12]})")
            elif r.get("fingerprint") != tree:
                why.append("stale tree (changed since the command ran)")
            if why:
                problems.append(f"{label}: {', '.join(why)}")
            else:
                kinds.add(r.get("kind"))
            lines.append(f"{'ok ' if not why else 'BAD'} {label} [{r.get('kind')}] tests={r.get('tests_ran')}"
                         + (f"  {', '.join(why)}" if why else ""))
        seen_kinds[unit_dir] = kinds
        for kind in required:
            if kind not in kinds:
                problems.append(f"{unit_dir}: no passing {kind} receipt")
    for line in lines:
        print(line)
    if problems:
        print(f"verify: {len(problems)} problem(s), the evidence does not hold")
        for p in problems:
            print(f"  {p}")
        return 1
    print(f"verify: {len(lines)} receipt(s) hold at {str(head)[:12]}")
    return 0


def parse(argv):
    if len(argv) < 2 or argv[1] not in ("run", "verify"):
        return None
    mode, rest = argv[1], argv[2:]
    command = []
    if "--" in rest:
        i = rest.index("--")
        rest, command = rest[:i], rest[i + 1:]
    opts = {"cwd": ".", "kind": "test", "name": None, "count_regex": None,
            "timeout": DEFAULT_TIMEOUT, "require": [], "dirs": []}
    i = 0
    while i < len(rest):
        a = rest[i]
        if a in ("--cwd", "--kind", "--name", "--count-regex", "--timeout", "--require") and i + 1 < len(rest):
            key = a[2:].replace("-", "_")
            if key == "require":
                opts["require"].append(rest[i + 1])
            elif key == "timeout":
                opts["timeout"] = int(rest[i + 1])
            else:
                opts[key] = rest[i + 1]
            i += 2
        elif a.startswith("--"):
            return None
        else:
            opts["dirs"].append(a)
            i += 1
    if opts["kind"] not in KINDS or any(k not in KINDS for k in opts["require"]):
        return None
    if mode == "run" and (len(opts["dirs"]) != 1 or not opts["name"] or not command):
        return None
    if mode == "verify" and not opts["dirs"]:
        return None
    return mode, opts, command


def main(argv):
    parsed = parse(argv)
    if parsed is None:
        sys.stderr.write(__doc__.split("\n\n")[3] + "\n")
        return 2
    mode, o, command = parsed
    if mode == "run":
        return cmd_run(o["dirs"][0], o["name"], o["kind"], o["cwd"], o["count_regex"], o["timeout"], command)
    return cmd_verify(o["dirs"], o["cwd"], o["require"])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
