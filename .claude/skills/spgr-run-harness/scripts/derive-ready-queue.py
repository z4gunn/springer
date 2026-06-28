#!/usr/bin/env python3
"""Derive the deterministic readiness snapshot for one run.

Reads the run store and returns the facts the orchestrator needs to route the
next tick, computed the same way every time so routing is reproducible and the
model adjudicates only genuine ambiguity. This script makes no routing decision.
It reports open gates, open escalations, the confirmed-artifact inventory, the
latest phase, and a blocked flag. The orchestrator turns this into a routed
batch.

Usage:
    python3 derive-ready-queue.py <run-dir>

<run-dir> is runs/<run-id>/. Prints a JSON snapshot to stdout. Exit 0 on
success, 1 on a usage or read error.
"""

import json
import sys
from pathlib import Path


def load_artifacts(run_dir):
    """Return a list of (path, artifact-dict) for every parseable artifact."""
    artifacts_dir = Path(run_dir) / "artifacts"
    out = []
    for path in sorted(artifacts_dir.glob("*.json")):
        try:
            out.append((path, json.loads(path.read_text())))
        except (OSError, json.JSONDecodeError):
            # A malformed file is reported as a read error, never silently used.
            out.append((path, None))
    return out


def derive(run_dir):
    run_id = Path(run_dir).name
    artifacts = load_artifacts(run_dir)

    read_errors = [str(p) for p, a in artifacts if a is None]
    good = [a for _, a in artifacts if a is not None]

    cycles = [a for a in good if a.get("artifact_type") == "pdca-cycle"]
    cycles.sort(key=lambda a: a.get("content", {}).get("cycle_number", 0))
    latest_cycle = cycles[-1] if cycles else None
    latest_phase = None
    if latest_cycle:
        c = latest_cycle.get("content", {})
        latest_phase = c.get("next_phase") or c.get("phase")

    open_gates = [
        a["content"]["checkpoint_id"]
        for a in good
        if a.get("artifact_type") == "hil-checkpoint"
        and a.get("content", {}).get("pipeline_status") == "paused"
        and a.get("content", {}).get("response_received") in (None, {})
    ]
    open_escalations = [
        a["content"]["escalation_id"]
        for a in good
        if a.get("artifact_type") == "escalation"
        and a.get("content", {}).get("status") == "open"
    ]

    inventory = []
    for a in good:
        atype = a.get("artifact_type")
        if atype in ("pdca-cycle", "run-state", "hil-checkpoint", "escalation", "run-retrospective"):
            continue
        conf = a.get("confidence_map", {})
        inventory.append({
            "artifact_id": a.get("artifact_id"),
            "artifact_type": atype,
            "version_type": a.get("version_type"),
            "all_confirmed": bool(conf) and all(v == "confirmed" for v in conf.values()),
        })

    blocked = bool(open_gates or open_escalations)
    reason = None
    if open_gates:
        reason = f"paused at gate(s): {', '.join(open_gates)}"
    elif open_escalations:
        reason = f"open escalation(s): {', '.join(open_escalations)}"

    return {
        "run_id": run_id,
        "cycle_counter": len(cycles),
        "latest_phase": latest_phase,
        "open_gates": open_gates,
        "open_escalations": open_escalations,
        "artifact_inventory": inventory,
        "blocked": blocked,
        "blocking_reason": reason,
        "read_errors": read_errors,
    }


def main(argv):
    if len(argv) != 2:
        sys.stderr.write(__doc__)
        return 1
    run_dir = Path(argv[1])
    if not (run_dir / "artifacts").is_dir():
        sys.stderr.write(f"no artifacts/ directory under {run_dir}\n")
        return 1
    print(json.dumps(derive(run_dir), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
