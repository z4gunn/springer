"""Cycle records, as pdca-cycle-v1 artifacts. The daemon writes one at Plan and
completes it at Act. A cycle closes when every unit it routed is terminal."""

from pathlib import Path

from ..common import artifact_header, next_id, read_json, write_json


class CycleStore:
    def __init__(self, run_dir, run_id, now):
        self.root = Path(run_dir) / "artifacts"
        self.run_id = run_id
        self.now = now

    def ids(self):
        return sorted(p.stem for p in self.root.glob("CYCLE-*.json")) if self.root.is_dir() else []

    def get(self, cycle_id):
        return read_json(self.root / f"{cycle_id}.json")

    def all(self):
        return [self.get(c) for c in self.ids()]

    def next_id(self):
        return next_id("CYCLE", self.ids())

    def plan(self, cycle_id, phase, routed_batch, rationale, next_phase=None):
        cycle = artifact_header(cycle_id, "pdca-cycle", "cycle", "v1", self.now())
        cycle["content"] = {
            "cycle_id": cycle_id, "cycle_number": int(cycle_id.rsplit("-", 1)[1]), "run_id": self.run_id,
            "phase": phase, "plan": {"routed_batch": routed_batch, "rationale": rationale},
            # The schema requires a dispatch per routed unit. Each reads skipped until Act
            # records what actually happened, so a cycle is valid while it is open.
            "do": {"dispatched": [{"agent": i["agent"], "unit_id": i.get("unit_id"), "status": "skipped"}
                                  for i in routed_batch]},
            "check": {"verdict": "gate", "validations": [], "audits": []},
            "act": {"transition": "pause", "state_changes": [], "versioned_refs": [], "escalation_ref": None,
                    "checkpoint_ref": None, "pending_batch": None},
            "next_phase": next_phase, "closed": False,
        }
        write_json(self.root / f"{cycle_id}.json", cycle)
        return cycle

    def close(self, cycle_id, unit_states, transition="advance"):
        """The Act record: the terminal state of each routed unit."""
        cycle = self.get(cycle_id)
        content = cycle["content"]
        by_unit = {i.get("unit_id"): i for i in content["plan"]["routed_batch"]}
        if unit_states:
            content["do"]["dispatched"] = [
                {"agent": by_unit[u]["agent"], "unit_id": u, "status": "completed" if s == "done" else "failed",
                 "produced_artifact_refs": []} for u, s in unit_states.items()]
        passed = all(s in ("done", "cancelled") for s in unit_states.values())
        content["check"]["verdict"] = "pass" if passed else "blocked"
        content["act"]["transition"] = transition if passed else "escalate"
        content["act"]["state_changes"] = [f"{u}: {s}" for u, s in unit_states.items()]
        content["closed"] = True
        write_json(self.root / f"{cycle_id}.json", cycle)
        return cycle

    def complete_run(self):
        """Mark the newest cycle as the one that completed the run."""
        ids = self.ids()
        if ids:
            cycle = self.get(ids[-1])
            cycle["content"]["act"]["transition"] = "complete"
            cycle["content"]["next_phase"] = None
            write_json(self.root / f"{ids[-1]}.json", cycle)

    def is_complete(self):
        ids = self.ids()
        return bool(ids) and self.get(ids[-1])["content"]["act"]["transition"] == "complete"
