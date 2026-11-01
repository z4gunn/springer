"""Check for one returned unit: read what the session left, name the verdict.

This is the seam. The canned run reads result.json alone. The Claude Code provider
at step 6 feeds it the real receipts, classify-failure, and the review package, and
nothing above this module changes.
"""

from pathlib import Path

from ..common import read_json
from ..providers.coding_agent import CheckResult
from .risk import level_for

# Each failure class and what it does. Only a defect spends a retry.
RETRY = "retry"
REDISPATCH = "redispatch"
BLOCK = "blocked"
POLICY = {"defect": RETRY, "transient": REDISPATCH, "environment": REDISPATCH, "context": REDISPATCH,
          "question": REDISPATCH, "blocked": BLOCK}
ADDENDA = {
    "question": "Do not stop to ask. Take the reversible default, log it, and continue.",
    "context": "The last session ran out of context. Stay inside the declared paths and read less.",
}


def read_result(session_dir):
    data = read_json(Path(session_dir) / "result.json")
    if data is None:
        return CheckResult(status="fail", failure_class="defect", detail="the session left no result.json")
    return CheckResult(status=data.get("status", "fail"), outcome=data.get("outcome", "artifact"), pr=data.get("pr"),
                       touched_paths=tuple(data.get("touched_paths", ())), failure_class=data.get("failure_class"),
                       detail=data.get("detail", ""), raised_level=data.get("raised_level"),
                       findings=tuple(data.get("findings", ())))


def risk_for(result, baseline):
    """Baseline from the spec, raised by the path rules and by reviewers, never lowered."""
    return level_for(result.touched_paths, baseline, result.raised_level)
