"""Mechanical Check for a real session, ported from the in-session loop's step 4.

The green path costs no model tokens: the session's own result.json, its receipts
verified at the worktree's head, and every artifact it wrote validated against its
schema. A failure is classified by classify-failure.py, so only a defect spends a
retry. The scripts are the instance's own, run from the unit's worktree, so the
daemon and the runtime cannot disagree about what a receipt or a class is.
"""

import json
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


def changed_artifacts(run_dir, since):
    folder = Path(run_dir) / "artifacts"
    return sorted(p for p in folder.glob("*.json") if p.stat().st_mtime >= since) if folder.is_dir() else []


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


def mechanical_check(session_dir, cwd, run_dir, project, unit_id, started_epoch):
    """A CheckResult for one returned session. The order is the in-session loop's:
    the result the session left, then receipts, then the artifacts it wrote."""
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
    if result.outcome == "pr" and not all(p.startswith(LEDGER_ONLY) for p in result.touched_paths):
        problem = verify_receipts(session_dir, cwd)
        if problem:
            return replace(result, status="fail", failure_class="defect", detail=f"receipts do not hold: {problem}")
    problems = validate_artifacts(changed_artifacts(run_dir, started_epoch), project)
    if problems:
        return replace(result, status="fail", failure_class="defect",
                       detail="artifacts fail their schema: " + "; ".join(problems)[:600])
    return result
