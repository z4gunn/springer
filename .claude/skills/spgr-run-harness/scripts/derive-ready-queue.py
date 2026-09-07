#!/usr/bin/env python3
"""Derive the deterministic readiness snapshot for one run.

Reads the run store and returns the facts the orchestrator needs to route the
next tick, computed the same way every time so routing is reproducible and the
model adjudicates only genuine ambiguity. This script makes no routing decision.
It reports open gates, open escalations, the confirmed-artifact inventory, the
latest phase, the run profile and flags from run-brief.json, any dispatched
agent that has no completion event yet, and a blocked flag. The orchestrator
turns this into a routed batch.

An un-joined dispatch blocks planning: a background agent outlives the turn
that dispatched it, and a cycle planned against a tree it is still writing is
the FI-024 defect. The check keys on unmatched tool_use_id values in
events.jsonl, never on elapsed time. A background dispatch is joined only by
an `agent_joined` event the harness appends on the task notification, or by
`agent_abandoned` for a dispatch known dead. Foreground dispatches are joined
by the hook's own `agent_completed`.

Usage:
    python3 derive-ready-queue.py <run-dir> [--session <session-id>]

--session names the calling harness session so its own lock on the run is not
reported as a block. A live lock held by any other session blocks planning.

<run-dir> is runs/<run-id>/. Prints a JSON snapshot to stdout. Exit 0 on
success, 1 on a usage or read error.
"""

import json
import sys
import time
from pathlib import Path

# The active run-store subdirectories. archive/ is excluded on purpose, so a
# superseded checkpoint or escalation cannot resurrect a gate or a block.
ACTIVE_SUBDIRS = ("artifacts", "escalations", "checkpoints", "consultations")


def load_artifacts(run_dir):
    """Return (path, artifact-dict) for every parseable artifact in the active
    stores. Scans every ACTIVE_SUBDIRS directory that exists, so an escalation
    or checkpoint counts whether it sits in artifacts/ or in its own subdir."""
    out = []
    for sub in ACTIVE_SUBDIRS:
        d = Path(run_dir) / sub
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.json")):
            try:
                out.append((path, json.loads(path.read_text())))
            except (OSError, json.JSONDecodeError):
                # A malformed file is reported as a read error, never silently used.
                out.append((path, None))
    return out


def load_run_brief(run_dir):
    """Return the run brief content, or {} when none exists yet. The brief is a
    projection (schemas/run-brief-v1.json): profile, flags, pinned rulings, and
    the operative artifact list."""
    bp = Path(run_dir) / "run-brief.json"
    if not bp.exists():
        return {}
    try:
        return json.loads(bp.read_text()).get("content", {})
    except (OSError, json.JSONDecodeError):
        return {}


def unjoined_dispatches(run_dir):
    """Return every agent_dispatched event whose tool_use_id has no matching
    agent_completed, agent_stopped, agent_joined, or agent_abandoned event. A
    background dispatch's agent_backgrounded event is not a join: the tool
    returned while the agent kept running. agent_stopped (SubagentStop) joins
    by tool_use_id, or by the agent_id the backgrounded event recorded. Malformed lines are skipped, since the hook writes
    best-effort and never blocks a tool call."""
    ep = Path(run_dir) / "events.jsonl"
    if not ep.exists():
        return []
    dispatched, joined, agent_ids, stopped_agents = {}, set(), {}, set()
    for line in ep.read_text().splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        tid = ev.get("tool_use_id")
        kind = ev.get("event")
        if kind == "agent_stopped":
            # SubagentStop: joins by tool_use_id when present, else by agent_id.
            if tid:
                joined.add(tid)
            if ev.get("agent_id"):
                stopped_agents.add(ev["agent_id"])
            continue
        if not tid:
            continue
        if kind == "agent_dispatched":
            dispatched.setdefault(tid, ev)
        elif kind == "agent_backgrounded" and ev.get("agent_id"):
            agent_ids[tid] = ev["agent_id"]
        elif kind in ("agent_completed", "agent_joined", "agent_abandoned"):
            joined.add(tid)
    for tid, aid in agent_ids.items():
        if aid in stopped_agents:
            joined.add(tid)
    return [
        {"tool_use_id": tid, "agent": ev.get("agent"), "ts": ev.get("ts"),
         "description": ev.get("description", "")}
        for tid, ev in dispatched.items() if tid not in joined
    ]


def run_lock(run_dir):
    """Return the .lock content plus whether its heartbeat is live, using the
    same rule as claim-run.py. The harness passes --session <id> so a lock it
    holds itself is never reported as a block."""
    lp = Path(run_dir) / ".lock"
    if not lp.exists():
        return None
    try:
        lock = json.loads(lp.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    try:
        claimed = time.mktime(time.strptime(lock.get("claimed_at", ""), "%Y-%m-%dT%H:%M:%SZ")) - time.timezone
        lock["alive"] = (time.time() - claimed) < 30 * 60
    except (ValueError, TypeError):
        lock["alive"] = False
    return lock


def derive(run_dir, session_id=None):
    run_id = Path(run_dir).name
    brief = load_run_brief(run_dir)
    unjoined = unjoined_dispatches(run_dir)
    lock = run_lock(run_dir)
    held_by_other = bool(lock and lock.get("alive") and lock.get("session_id") != session_id)
    artifacts = load_artifacts(run_dir)

    read_errors = [str(p) for p, a in artifacts if a is None]
    # Dedup by artifact_id, keeping the first occurrence so artifacts/ wins if
    # the same id ever appears in two stores.
    good, seen = [], set()
    for _, a in artifacts:
        if a is None:
            continue
        aid = a.get("artifact_id")
        if aid in seen:
            continue
        seen.add(aid)
        good.append(a)

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

    blocked = bool(open_gates or open_escalations or unjoined or held_by_other)
    reason = None
    if held_by_other:
        reason = f"run held by another live session {lock.get('session_id')} since {lock.get('claimed_at')}"
    elif unjoined:
        ids = ", ".join(u["tool_use_id"] for u in unjoined)
        reason = f"un-joined dispatch(es) still running or abandoned without an event: {ids}"
    elif open_gates:
        reason = f"paused at gate(s): {', '.join(open_gates)}"
    elif open_escalations:
        reason = f"open escalation(s): {', '.join(open_escalations)}"

    return {
        "run_id": run_id,
        "profile": brief.get("profile"),
        "flags": brief.get("flags", {}),
        "cycle_counter": len(cycles),
        "latest_phase": latest_phase,
        "open_gates": open_gates,
        "open_escalations": open_escalations,
        "artifact_inventory": inventory,
        "unjoined_dispatches": unjoined,
        "lock": lock,
        "blocked": blocked,
        "blocking_reason": reason,
        "read_errors": read_errors,
    }


def main(argv):
    session_id = None
    if "--session" in argv:
        i = argv.index("--session")
        session_id = argv[i + 1] if i + 1 < len(argv) else None
        argv = argv[:i] + argv[i + 2:]
    if len(argv) != 2:
        sys.stderr.write(__doc__)
        return 1
    run_dir = Path(argv[1])
    if not (run_dir / "artifacts").is_dir():
        sys.stderr.write(f"no artifacts/ directory under {run_dir}\n")
        return 1
    print(json.dumps(derive(run_dir, session_id), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
