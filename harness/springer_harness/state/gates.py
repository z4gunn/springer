"""Gates, stored as hil-checkpoint-v2 artifacts under the run's artifacts directory."""

from pathlib import Path

from ..common import artifact_header, iso, next_id, read_json, write_json
from ..errors import GateAlreadyAnswered, InvalidArgs, NotFound


class GateStore:
    def __init__(self, run_dir, ledger, now):
        self.root = Path(run_dir) / "artifacts"
        self.ledger = ledger
        self.now = now

    def ids(self):
        return sorted(p.stem for p in self.root.glob("G-*.json")) if self.root.is_dir() else []

    def path(self, gate_id):
        return self.root / f"{gate_id}.json"

    def get(self, gate_id):
        gate = read_json(self.path(gate_id))
        if gate is None:
            raise NotFound(f"no gate {gate_id}")
        return gate

    def all(self):
        return [self.get(g) for g in self.ids()]

    def open(self, checkpoint_type, level, holds, prompt, options, artifact_ref="none", digest=False,
             decisions=None, urgency="routine", context=None):
        gate_id = next_id("G", self.ids())
        gate = artifact_header(gate_id, "hil-checkpoint", "gate", "v2", self.now())
        gate["content"] = {
            "checkpoint_id": gate_id, "checkpoint_type": checkpoint_type, "artifact_ref": artifact_ref,
            "decision_prompt": prompt, "options": options, "urgency": urgency, "level": level, "holds": holds,
            "digest": digest, "pipeline_status": "resumed" if digest else "paused", "channel_refs": [],
            "response": None, "opened_at": iso(self.now()), "context": context or {},
        }
        if decisions:
            gate["content"]["decisions"] = decisions
        write_json(self.path(gate_id), gate)
        self.ledger.append("gate_opened", gate_id=gate_id, level=level, holds=holds)
        return gate

    def answer(self, gate_id, option, by, free_text=None, rule_change=None, decisions=None):
        gate = self.get(gate_id)
        content = gate["content"]
        if content["response"] is not None:
            raise GateAlreadyAnswered(f"{gate_id} is already answered", {"response": content["response"]})
        offered = {o["option"] for o in content["options"]}
        if option not in offered:
            raise InvalidArgs(f"{option} is not an option of {gate_id}", {"options": sorted(offered)})
        if decisions:
            answers = {d["decision_id"]: d["response"] for d in decisions}
            known = content.get("decisions", [])
            unknown = set(answers) - {d["decision_id"] for d in known}
            if unknown:
                raise InvalidArgs(f"{gate_id} has no decisions {sorted(unknown)}")
            for decision in known:
                decision["response"] = answers.get(decision["decision_id"], decision.get("response"))
        self.ledger.append("gate_answered", gate_id=gate_id, response=option, by=by)
        content["response"] = {"option": option, "free_text": free_text, "rule_change": rule_change,
                               "by": by, "at": iso(self.now())}
        content["pipeline_status"] = "resumed"
        write_json(self.path(gate_id), gate)
        return gate

    def close_digest(self, gate_id, by):
        gate = self.get(gate_id)
        if not gate["content"]["digest"]:
            raise InvalidArgs(f"{gate_id} is not a digest entry")
        if gate["content"]["response"] is None:
            gate["content"]["response"] = {"option": "viewed", "free_text": None, "rule_change": None,
                                           "by": by, "at": iso(self.now())}
            write_json(self.path(gate_id), gate)

    def open_gates(self):
        return [g for g in self.all() if g["content"]["response"] is None]

    def holding(self, unit_id, *types):
        """Open and answered gates that name this unit, newest last."""
        return [g for g in self.all() if unit_id in g["content"]["holds"]
                and not g["content"]["context"].get("retired")
                and (not types or g["content"]["checkpoint_type"] in types)]

    def held_at_start(self, unit_id):
        """True while an open L3 gate holds this unit's start."""
        return any(g["content"]["level"] == "L3" and unit_id in g["content"]["holds"] for g in self.open_gates())
