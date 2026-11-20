"""Mechanical Check for a real session, ported from the in-session loop's step 4.

The green path costs no model tokens: the session's own result.json, the unit's
gating commands run by the harness at the worktree's head, and every artifact the
session wrote validated against its schema. A failure is classified by
classify-failure.py, so only a defect spends a retry. The scripts are the
instance's own, run from the unit's worktree, so the daemon and the runtime cannot
disagree about what a receipt or a class is.

The harness runs the gating commands itself rather than trusting receipts the session
wrote. In the reference run most retries were receipts a session took before a later
commit, or a check recorded as a test. A unit whose spec names no gating commands (one
planned before they existed) keeps the old path: its session's receipts are verified.
"""

import json
import re
import shutil
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from .verdict import read_result

SCRIPTS = Path(".claude/skills/spgr-run-harness/scripts")
VALIDATE = Path("schemas/validate.py")
# Paths that need no review, no receipt, and no audit, per the in-session loop.
LEDGER_ONLY = ("runs/", "docs/")


def _run(args, cwd, timeout=300, env=None):
    return subprocess.run([sys.executable, *map(str, args)], cwd=str(cwd), capture_output=True, text=True,
                          timeout=timeout, env={**os.environ, **env} if env else None)


def classify(session_dir, cwd, run_dir, unit_id):
    """The class classify-failure.py names, or defect when it cannot run."""
    script = Path(cwd) / SCRIPTS / "classify-failure.py"
    if not script.exists():
        return "defect", "classify-failure.py is missing from the worktree"
    done = _run([script, session_dir, "--run-dir", run_dir, "--unit-id", unit_id], cwd)
    try:
        found = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return "defect", f"classify-failure.py said nothing usable: {done.stderr[-300:]}"
    return found["class"], (found.get("evidence") or "")[:300]


def verify_receipts(session_dir, cwd):
    """None when the receipts hold, else what receipt.py verify reported."""
    script = Path(cwd) / SCRIPTS / "receipt.py"
    if not script.exists():
        return "receipt.py is missing from the worktree"
    done = _run([script, "verify", session_dir, "--cwd", cwd, "--require", "test"], cwd)
    return None if done.returncode == 0 else (done.stdout + done.stderr).strip()[-600:]


GATING_TIMEOUT = 1800
OUTPUT_SHOWN = 800


def needs_gating(result):
    """A PR, or code reported as an artifact, which still becomes a PR."""
    return result.outcome == "pr" or not all(p.startswith(LEDGER_ONLY) for p in result.touched_paths)


def run_gating(commands, out, cwd, warnings=None, baseline=None, changed=None, reruns=None, env=None):
    """Run each gating command at the worktree's head through receipt.py, writing the
    receipts under out, in order. None when every one passes, else the defect detail
    naming the first that did not, with the tail of its output. A product command is
    judged by its exit code, as a check is, because the receipt's test count only reads
    a test runner's summary.

    A test command that exits 0 with a count receipt.py cannot read is the plan's
    command shape, not the session's work, so it costs no retry. It passes with a
    line appended to warnings, and the caller holds the merge for a person.

    A command that fails here and fails on the unit's base too is the base's failure,
    which no retry of this change can fix: the reference run spent eight sessions on a
    contrast failure main already had. baseline(command) gives the base's output tail
    when the command fails there, and such a command passes with a warning, so the
    merge waits on a person who sees both outputs. A base that could not run the
    command (a missing module or program) says nothing, so the failure stays the
    change's, unless the change could not run it either: a broken check.

    A test command whose failing test files all lie outside the unit's change
    (changed, the paths its branch changes) runs once more before it counts. A full
    suite on a loaded machine times out tests the change never touched, and the
    reference run spent a retry on three of them in one afternoon. A pass on the rerun
    passes, with the files named in reruns, and does not hold the merge. A second
    failure is judged as any failure is."""
    script = Path(cwd) / SCRIPTS / "receipt.py"
    if not script.exists():
        return "receipt.py is missing from the worktree"
    out = Path(out)
    shutil.rmtree(out, ignore_errors=True)
    for command in commands:
        name = command["name"]
        body = _gate(script, command, out, cwd, env)
        if isinstance(body, str):
            return body
        outside = outside_change(body, command, changed)
        if outside:
            # Kept beside the receipts, not among them, so a verify never reads it.
            kept = out / "first-run"
            kept.mkdir(parents=True, exist_ok=True)
            (out / "receipts" / f"{name}.json").replace(kept / f"{name}.json")
            body = _gate(script, command, out, cwd, env)
            if isinstance(body, str):
                return body
            if body.get("result") == "pass":
                if reruns is not None:
                    reruns.append({"name": name, "files": outside})
                continue
        if body.get("result") == "unknown-count" and body.get("exit_code") == 0:
            if warnings is not None:
                warnings.append(f"{name} ({command['command']}) exited 0 but printed no test count the harness "
                                f"can read, so the merge waits on a person")
                continue
        if body.get("result") == "fail" and baseline is not None and warnings is not None:
            base_tail = baseline(command)
            if base_tail is not None:
                tail = (body.get("output_tail") or "").strip()[-OUTPUT_SHOWN // 2:]
                here, there = cannot_run(body.get("exit_code"), tail), cannot_run(None, base_tail)
                if here and there:
                    warnings.append(f"{name} ({command['command']}) is a broken check: it cannot run here or on "
                                    f"the base ({here}), so it tested nothing. Fix the command or install what "
                                    f"it needs. The merge waits on a person.")
                    continue
                # A base that could not run the command says nothing about it, so a
                # failure that ran here stays this change's defect.
                if not there:
                    warnings.append(f"{name} ({command['command']}) fails on the base too, so it is not this "
                                    f"change's defect and the merge waits on a person. Here its output ends: {tail} "
                                    f"On the base it ends: {base_tail.strip()[-OUTPUT_SHOWN // 2:]}")
                    continue
        if body.get("result") != "pass":
            why = {"unknown-count": "printed no test count the harness can read. Use a runner that reports one, "
                                    "or give the command a count_regex",
                   "zero-run": "ran no tests", "fail": f"failed with exit {body.get('exit_code')}",
                   "error": "could not run"}.get(body.get("result"), str(body.get("result")))
            tail = (body.get("output_tail") or "").strip()[-OUTPUT_SHOWN:]
            return f"gating command {name} ({command['command']}) {why}. Its output ends: {tail}"
    return None


def _gate(script, command, out, cwd, env=None):
    """Run one gating command through receipt.py. Its receipt body, or the defect
    detail when it did not finish or left no receipt. A product check alone gets the
    project's check environment (a staging account, a fixtures path). A build or test
    command never sees it."""
    name, kind = command["name"], "check" if command["kind"] == "product" else command["kind"]
    timeout = command.get("timeout") or GATING_TIMEOUT
    args = [script, "run", out, "--name", name, "--kind", kind, "--cwd", cwd, "--timeout", str(timeout)]
    if command.get("count_regex"):
        args += ["--count-regex", command["count_regex"]]
    try:
        _run([*args, "--", command["command"]], cwd, timeout=timeout + 60,
             env=env if command["kind"] == "product" else None)
    except subprocess.TimeoutExpired:
        return f"gating command {name} ({command['command']}) did not finish"
    try:
        return json.loads((Path(out) / "receipts" / f"{name}.json").read_text())
    except (OSError, ValueError):
        return f"gating command {name} ({command['command']}) left no receipt"


ANSI = re.compile(r"\x1b\[[0-9;]*m")
# A runner's failure line (vitest and jest FAIL, pytest FAILED), and, for a tail cut
# before those lines, a test file in a stack frame. node_modules is never the test.
FAILED_LINE = re.compile(r"(?m)(?:^|\s)(?:FAIL|FAILED)\s+([\w@./-]+\.[A-Za-z]{1,5})\b")
TEST_FILE = re.compile(r"([\w@./-]+(?:\.(?:test|spec)\.[A-Za-z]{1,4}|/test_\w+\.py|_test\.(?:py|go)))\b")


def failing_files(tail):
    """The test files a runner's output tail names as failing, or an empty set."""
    text = ANSI.sub("", tail or "")
    found = set(FAILED_LINE.findall(text)) or set(TEST_FILE.findall(text))
    return {f for f in found if "node_modules/" not in f}


def outside_change(body, command, changed):
    """The failing test files, sorted, when a test command failed only in files the
    unit's change leaves alone. Empty when it passed, is not a test, names no file,
    or any failing file is one the change touches. No changed paths (a diff that could
    not be read reads as none) means the change is unknown, and gets no rerun."""
    if not changed or body.get("result") != "fail" or command.get("kind") != "test":
        return []
    files = failing_files(body.get("output_tail"))
    return sorted(files) if files and not files & set(changed) else []


# What a command prints when it never reached the thing it checks: a missing module,
# package, or program. Exit 127 is the shell's command not found.
MISSING = re.compile(r"(No module named '?[\w.]+'?|Cannot find module '?[^'\s]+'?|ERR_MODULE_NOT_FOUND"
                     r"|command not found|sh: (?:\d+: )?[\w./-]+: not found|No such file or directory: '[^']+')")


def cannot_run(exit_code, tail):
    """What kept the command from running, quoted from its output, or None."""
    found = MISSING.search(tail or "")
    if found:
        return found.group(1)
    return "exit 127, command not found" if exit_code == 127 else None


def fails_at(command, out, cwd, env=None):
    """The command's output tail when it runs to a plain failure in cwd, else None: a
    pass, a timeout, or a command that could not run there says nothing about the base.
    A product check runs with the same check environment it had at the head, or a base
    run without the staging account fails and reads as the base's failure."""
    script = Path(cwd) / SCRIPTS / "receipt.py"
    if not script.exists():
        return None
    timeout = command.get("timeout") or GATING_TIMEOUT
    args = [script, "run", out, "--name", command["name"], "--kind",
            "check" if command["kind"] == "product" else command["kind"], "--cwd", cwd, "--timeout", str(timeout)]
    if command.get("count_regex"):
        args += ["--count-regex", command["count_regex"]]
    try:
        _run([*args, "--", command["command"]], cwd, timeout=timeout + 60,
             env=env if command["kind"] == "product" else None)
    except subprocess.TimeoutExpired:
        return None
    try:
        body = json.loads((Path(out) / "receipts" / f"{command['name']}.json").read_text())
    except (OSError, ValueError):
        return None
    return (body.get("output_tail") or "") if body.get("result") == "fail" else None


HARNESS_OWNED = ("CYCLE-", "G-", "E-")  # the daemon writes these, never a session


def changed_artifacts(run_dir, since):
    """The artifacts the session wrote: changed since it started, and not one of the
    records the daemon itself writes while the session runs."""
    folder = Path(run_dir) / "artifacts"
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.glob("*.json")
                  if p.stat().st_mtime >= since and not p.name.startswith(HARNESS_OWNED))


def validate_artifacts(paths, project):
    """Each artifact through schemas/validate.py. Returns the failures as text."""
    script = Path(project) / VALIDATE
    if not script.exists():
        return []
    problems = []
    for path in paths:
        done = _run([script, path], project, timeout=60)
        if done.returncode:
            problems.append(f"{path.name}: {(done.stdout + done.stderr).strip()[-300:]}")
    return problems


UNREADABLE_COUNT_LEVEL = "L2"


def hold_for_person(result, warnings):
    """A pass whose gating left warnings: raised so it cannot merge without a person,
    with the warnings in its findings so the merge gate shows them."""
    if not warnings or result.status != "pass":
        return result
    level = max(result.raised_level or "L0", UNREADABLE_COUNT_LEVEL)
    return replace(result, raised_level=level, findings=tuple(result.findings) + tuple(
        {"severity": "P2", "file": "", "detail": w} for w in warnings))


def mechanical_check(session_dir, cwd, run_dir, project, unit_id, started_epoch, require_receipts=True,
                     gating=None, baseline=None, changed=None):
    """A CheckResult for one returned session. The order is the in-session loop's:
    the result the session left, then the gating commands (or, for a unit with none,
    the session's receipts), then the artifacts it wrote."""
    session_dir, cwd = Path(session_dir), Path(cwd)
    result = read_result(session_dir)
    has_result = (session_dir / "result.json").exists()
    if result.status != "pass":
        cls, evidence = classify(session_dir, cwd, run_dir, unit_id)
        given = result.failure_class if has_result else None
        # The session's own class stands unless the script finds a platform cause,
        # which a session cannot see from inside (e.g. its own usage limit).
        chosen = cls if cls in ("transient", "context", "environment") or not given else given
        detail = result.detail if has_result else f"no result.json. {evidence}"
        return replace(result, status="fail", failure_class=chosen, detail=detail.strip())
    code = not all(p.startswith(LEDGER_ONLY) for p in result.touched_paths)
    if gating and needs_gating(result):
        # Run in place, for a caller with no tick to protect. The daemon runs them off
        # the tick through GatingRuns and passes none here.
        warnings = []
        problem = run_gating(gating, session_dir / "check", cwd, warnings, baseline, changed)
        if problem:
            return replace(result, status="fail", failure_class="defect", detail=problem)
        result = hold_for_person(result, warnings)
    elif require_receipts and result.outcome == "pr" and code:
        problem = verify_receipts(session_dir, cwd)
        if problem:
            return replace(result, status="fail", failure_class="defect", detail=f"receipts do not hold: {problem}")
    problems = validate_artifacts(changed_artifacts(run_dir, started_epoch), project)
    if problems:
        return replace(result, status="fail", failure_class="defect",
                       detail="artifacts fail their schema: " + "; ".join(problems)[:600])
    return result
