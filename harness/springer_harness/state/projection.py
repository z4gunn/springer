"""run-state.json, a cache rebuilt from the cycle log, the unit records, and the
ledger. Any process can rebuild it, and nothing reads it as a source of truth."""

from pathlib import Path

from ..common import artifact_header, parse_iso, read_json, write_json
from .backlog import BacklogStore

BOARD = {"backlog": ("planned", "ready", "retry", "redispatch", "blocked", "abandoned"),
         "development": ("running",), "review": ("returned", "checking", "gated"), "validation": (),
         "done": ("done", "cancelled")}


def is_paused(ledger):
    paused = False
    for entry in ledger.read():
        if entry.line.get("event") == "operation_applied":
            if entry.line.get("type") == "run.pause":
                paused = True
            elif entry.line.get("type") == "run.resume":
                paused = False
    return paused


def rebuild(run_dir, run_id, ledger, units, gates, cycles, now, sessions_for, window=None, profile=None,
            write=True):
    states = [units.state(u) for u in units.ids()]
    counts = {}
    for state in states:
        counts[state["state"]] = counts.get(state["state"], 0) + 1
    last_seq = max((e.line["seq"] for e in ledger.read() if isinstance(e.line.get("seq"), int)), default=0)
    in_flight = []
    for state in states:
        if state["state"] != "running" or not state["sessions"]:
            continue
        store = sessions_for(state["unit_id"])
        session = store.get(state["sessions"][-1])
        if session is None:
            continue
        total = session["input_tokens"] + session["output_tokens"]
        in_flight.append({"unit_id": state["unit_id"], "session_id": session["session_id"],
                          "agent": units.spec(state["unit_id"])["agent"], "model": session["model"] or "unknown",
                          "started_at": session["started_at"], "context_percent": session["context_percent_at_exit"],
                          "cost": session["cost_usd_list_price"], "tokens": total,
                          "last_tool_call": store.last_tool_call(session["session_id"])})
    open_gates = [g["content"] for g in gates.open_gates() if not g["content"]["digest"]]
    cycle_records = cycles.all()
    phase = cycle_records[-1]["content"]["phase"] if cycle_records else "planning"
    worktrees = []
    for entry in ledger.read():
        if entry.line.get("event") == "worktree_claimed":
            worktrees = [w for w in worktrees if w["unit_id"] != entry.line["unit_id"]]
            worktrees.append({"unit_id": entry.line["unit_id"], "path": entry.line["path"]})
        elif entry.line.get("event") == "worktree_released":
            worktrees = [w for w in worktrees if w["unit_id"] != entry.line["unit_id"]]
    waiting = None
    if window is not None and window["dispatch_rate"] == 0:
        waiting = "usage_window"
    elif any(g["checkpoint_type"] == "provisioning-required" for g in open_gates):
        waiting = "provisioning"
    elif open_gates and not in_flight:
        waiting = "gate"
    escalations = [read_json(p) for p in sorted(Path(run_dir, "artifacts").glob("E-*.json"))]
    backlog = BacklogStore.for_run(run_dir).sync() or {"epics": []}
    features = [f for epic in backlog["epics"] for f in epic["features"]]
    doc = artifact_header(f"run-state-{run_id}", "run-state", "run_state", "v2", now())
    doc["content"] = {
        "run_id": run_id, "regenerable": True, "generated_from_cycle": len(cycle_records), "active_phase": phase,
        "cycle_counter": len(cycle_records), "generated_from_seq": last_seq,
        "wip_board": {column: [s["unit_id"] for s in states if s["state"] in members]
                      for column, members in BOARD.items()},
        "workstreams": [], "units": counts, "in_flight": in_flight,
        "open_gates": [{"id": g["checkpoint_id"], "level": g["level"], "holds": g["holds"],
                        "age_seconds": int(now() - parse_iso(g["opened_at"]))} for g in open_gates],
        "open_escalations": [e["content"]["escalation_id"] for e in escalations if e["content"]["status"] == "open"],
        "worktrees": worktrees, "paused": is_paused(ledger), "waiting_on": waiting,
        "mvp_line": {"above": [f["feature_id"] for f in features if f["mvp"]],
                     "below": [f["feature_id"] for f in features if not f["mvp"]]} if features else None,
        "deferred": [f["feature_id"] for f in features if f["deferred"]],
        "window": None if window is None else {"provider": window["provider"], "used_fraction": window["used_fraction"],
                                               "resets_at": window["resets_at"]},
    }
    if profile:
        doc["content"]["profile"] = profile
    if write:
        write_json(f"{run_dir}/run-state.json", doc)
    return doc

