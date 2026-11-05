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
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from .verdict import read_result

SCRIPTS = Path(".claude/skills/spgr-run-harness/scripts")
VALIDATE = Path("schemas/validate.py")
# Paths that need no review, no receipt, and no audit, per the in-session loop.
LEDGER_ONLY = ("runs/", "docs/")


def _run(args, cwd, timeout=300):
    return subprocess.run([sys.executable, *map(str, args)], cwd=str(cwd), capture_output=True, text=True,
                          timeout=timeout)


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


def run_gating(commands, out, cwd):
    """Run each gating command at the worktree's head through receipt.py, writing the
    receipts under out, in order. None when every one passes, else the defect detail
    naming the first that did not, with the tail of its output. A product command is
    judged by its exit code, as a check is, because the receipt's test count only reads
    a test runner's summary."""
    script = Path(cwd) / SCRIPTS / "receipt.py"
    if not script.exists():
        return "receipt.py is missing from the worktree"
    out = Path(out)
    shutil.rmtree(out, ignore_errors=True)
    for command in commands:
        name, kind = command["name"], "check" if command["kind"] == "product" else command["kind"]
        args = [script, "run", out, "--name", name, "--kind", kind, "--cwd", cwd,
                "--timeout", str(command.get("timeout") or GATING_TIMEOUT)]
        if command.get("count_regex"):
            args += ["--count-regex", command["count_regex"]]
        try:
            _run([*args, "--", command["command"]], cwd, timeout=(command.get("timeout") or GATING_TIMEOUT) + 60)
        except subprocess.TimeoutExpired:
            return f"gating command {name} ({command['command']}) did not finish"
        receipt = out / "receipts" / f"{name}.json"
        try:
            body = json.loads(receipt.read_text())
        except (OSError, ValueError):
            return f"gating command {name} ({command['command']}) left no receipt"
        if body.get("result") != "pass":
            why = {"unknown-count": "printed no test count the harness can read. Use a runner that reports one, "
                                    "or give the command a count_regex",
                   "zero-run": "ran no tests", "fail": f"failed with exit {body.get('exit_code')}",
                   "error": "could not run"}.get(body.get("result"), str(body.get("result")))
            tail = (body.get("output_tail") or "").strip()[-OUTPUT_SHOWN:]
            return f"gating command {name} ({command['command']}) {why}. Its output ends: {tail}"
    return None


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


def mechanical_check(session_dir, cwd, run_dir, project, unit_id, started_epoch, require_receipts=True,
                     gating=None):
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
        problem = run_gating(gating, session_dir / "check", cwd)
        if problem:
            return replace(result, status="fail", failure_class="defect", detail=problem)
    elif require_receipts and result.outcome == "pr" and code:
        problem = verify_receipts(session_dir, cwd)
        if problem:
            return replace(result, status="fail", failure_class="defect", detail=f"receipts do not hold: {problem}")
    problems = validate_artifacts(changed_artifacts(run_dir, started_epoch), project)
    if problems:
        return replace(result, status="fail", failure_class="defect",
                       detail="artifacts fail their schema: " + "; ".join(problems)[:600])
    return result
