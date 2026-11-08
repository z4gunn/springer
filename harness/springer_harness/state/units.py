"""The unit as a first-class entity: its directory, spec, state, and lifecycle."""

from pathlib import Path

from ..common import iso, next_id, read_json, write_json
from ..errors import IllegalTransition, NotFound

# The lifecycle table in runtime/references/state-model.md. running --> redispatch
# and gated --> retry are the human interventions (re-dispatch, send back).
TRANSITIONS = {
    "planned": {"ready", "blocked", "cancelled"},
    "ready": {"running", "blocked", "cancelled"},
    "running": {"returned", "abandoned", "redispatch", "cancelled"},
    "returned": {"checking", "cancelled"},
    "checking": {"gated", "done", "retry", "redispatch", "blocked", "cancelled"},
    "gated": {"done", "retry", "blocked", "cancelled"},
    "done": set(),
    "retry": {"ready", "redispatch", "blocked", "cancelled"},
    "redispatch": {"ready", "blocked", "cancelled"},
    "blocked": {"ready", "redispatch", "cancelled"},
    "abandoned": {"redispatch", "cancelled"},
    "cancelled": set(),
}
MAX_RETRIES = 2
IN_FLIGHT = {"running"}
TIERS = ("haiku", "sonnet", "opus")


def is_terminal(state):
    """A unit that reaches done, cancelled, or exhausts its retries is terminal."""
    return state["state"] in ("done", "cancelled") or (
        state["state"] == "blocked" and state["retries_spent"] > MAX_RETRIES)


class UnitStore:
    def __init__(self, run_dir, ledger, now):
        self.root = Path(run_dir) / "units"
        self.ledger = ledger
        self.now = now

    def ids(self):
        """The units that exist, which is once their state is written. A reader that does
        not hold the daemon lock, such as the API's live stream, can see a unit's folder
        between its spec and its state."""
        return [u for u in self.folders() if (self.root / u / "state.json").exists()]

    def folders(self):
        if not self.root.is_dir():
            return []
        return sorted(p.name for p in self.root.iterdir() if p.is_dir())

    def unit_dir(self, unit_id):
        return self.root / unit_id

    def next_id(self):
        return next_id("U", self.folders())

    def create(self, spec):
        unit_id = spec["unit_id"]
        write_json(self.unit_dir(unit_id) / "spec.json", {"artifact_type": "unit-spec", "schema_version": "v1", **spec})
        at = self.now()
        write_json(self.unit_dir(unit_id) / "state.json", {
            "artifact_type": "unit-state", "schema_version": "v1", "unit_id": unit_id, "state": "planned",
            "entered_at": iso(at), "history": [{"state": "planned", "at": iso(at), "reason": "cycle planned"}],
            "retries_spent": 0, "sessions": [], "pr": None, "merge": None, "cancelled_by": None})
        self.ledger.append("unit_state", unit_id=unit_id, **{"from": None}, to="planned", reason="cycle planned")

    def spec(self, unit_id):
        spec = read_json(self.unit_dir(unit_id) / "spec.json")
        if spec is None:
            raise NotFound(f"no unit {unit_id}")
        return spec

    def state(self, unit_id):
        state = read_json(self.unit_dir(unit_id) / "state.json")
        if state is None:
            raise NotFound(f"no unit {unit_id}")
        return state

    def save(self, state):
        write_json(self.unit_dir(state["unit_id"]) / "state.json", state)

    def transition(self, unit_id, to, reason, **updates):
        """Move a unit one edge of the lifecycle. The ledger line is written first,
        so state.json can always be repaired from the ledger after a crash."""
        state = self.state(unit_id)
        if to not in TRANSITIONS[state["state"]]:
            raise IllegalTransition(f"{unit_id} cannot go from {state['state']} to {to}",
                                    {"unit_id": unit_id, "from": state["state"], "to": to})
        self.ledger.append("unit_state", unit_id=unit_id, **{"from": state["state"]}, to=to, reason=reason)
        at = iso(self.now())
        state.update(updates)
        state["state"] = to
        state["entered_at"] = at
        state["history"].append({"state": to, "at": at, "reason": reason})
        self.save(state)
        return state

    def by_state(self, *states):
        return [s for s in (self.state(u) for u in self.ids()) if s["state"] in states]

    def repair_from_ledger(self):
        """A crash between the ledger line and state.json leaves them apart, and
        the ledger wins. Returns the ids repaired."""
        last = {}
        for entry in self.ledger.read():
            if entry.line.get("event") == "unit_state":
                last[entry.line["unit_id"]] = entry.line
        repaired = []
        for unit_id, line in last.items():
            state = read_json(self.unit_dir(unit_id) / "state.json")
            if state and state["state"] != line["to"]:
                at = iso(self.now())
                state["state"] = line["to"]
                state["entered_at"] = at
                state["history"].append({"state": line["to"], "at": at, "reason": f"repaired: {line['reason']}"})
                self.save(state)
                repaired.append(unit_id)
        return repaired
