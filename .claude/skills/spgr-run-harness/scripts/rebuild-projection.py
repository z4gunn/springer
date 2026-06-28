#!/usr/bin/env python3
"""Rebuild run-state.json by replaying the pdca-cycle log.

run-state is a derived cache (ADR-001). This script reconstructs the
cycle-derived fields from the immutable cycle log and the current artifacts,
then writes runs/<run-id>/run-state.json. The wip_board and learnings_pinned are
carried forward from an existing run-state when present, because story-stage
moves become structured in the cycle log only at the parallel-Do increment. The
cycle-derived fields (cycle_counter, generated_from_cycle, active_phase,
open_gates, open_escalations) are always reconstructed from scratch.

Usage:
    python3 rebuild-projection.py <run-dir> [--validate]

<run-dir> is runs/<run-id>/. Writes <run-dir>/run-state.json and prints a
summary. With --validate, also runs schemas/validate.py against the result.
Exit 0 on success, 1 on a usage or read error.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

EMPTY_BOARD = {"backlog": [], "development": [], "review": [], "validation": [], "done": []}


def load_good(run_dir):
    artifacts_dir = Path(run_dir) / "artifacts"
    out = []
    for path in sorted(artifacts_dir.glob("*.json")):
        try:
            out.append(json.loads(path.read_text()))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def existing_state(run_dir):
    sp = Path(run_dir) / "run-state.json"
    if sp.exists():
        try:
            return json.loads(sp.read_text()).get("content", {})
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def rebuild(run_dir):
    run_id = Path(run_dir).name
    good = load_good(run_dir)
    prior = existing_state(run_dir)

    cycles = [a for a in good if a.get("artifact_type") == "pdca-cycle"]
    cycles.sort(key=lambda a: a.get("content", {}).get("cycle_number", 0))
    latest = cycles[-1].get("content", {}) if cycles else {}
    active_phase = latest.get("next_phase") or latest.get("phase") or "discovery"
    generated_from_cycle = latest.get("cycle_number", 0)

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

    content = {
        "run_id": run_id,
        "regenerable": True,
        "generated_from_cycle": generated_from_cycle,
        "active_phase": active_phase,
        "workstreams": prior.get("workstreams", []),
        "wip_board": prior.get("wip_board", dict(EMPTY_BOARD)),
        "ready_queue": [],
        "open_gates": open_gates,
        "open_escalations": open_escalations,
        "cycle_counter": len(cycles),
        "learnings_pinned": prior.get("learnings_pinned", []),
    }
    artifact = {
        "artifact_id": f"run-state-{run_id}",
        "artifact_type": "run-state",
        "schema_version": "v1",
        "producing_agent": "spgr-agent-orchestrator",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "parent_artifact_ref": None,
        "version": "v0.1-draft",
        "version_type": "draft",
        "confidence_map": {"run_state": "confirmed"},
        "decision_log": [],
        "content": content,
    }
    return artifact


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    do_validate = "--validate" in argv
    if len(args) != 1:
        sys.stderr.write(__doc__)
        return 1
    run_dir = Path(args[0])
    if not (run_dir / "artifacts").is_dir():
        sys.stderr.write(f"no artifacts/ directory under {run_dir}\n")
        return 1

    artifact = rebuild(run_dir)
    out_path = run_dir / "run-state.json"
    out_path.write_text(json.dumps(artifact, indent=2))
    c = artifact["content"]
    print(f"wrote {out_path}")
    print(f"  cycle_counter={c['cycle_counter']} active_phase={c['active_phase']} "
          f"open_gates={c['open_gates']} open_escalations={c['open_escalations']}")

    if do_validate:
        validator = Path(__file__).resolve().parents[4] / "schemas" / "validate.py"
        proc = subprocess.run([sys.executable, str(validator), str(out_path)],
                              capture_output=True, text=True)
        sys.stdout.write(proc.stdout)
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
