"""Plan with the orchestrator agent: its judgment core, given what the run has done,
names the next units and the gap each closes. Everything else stays in the engine.

The call is one headless Claude Code session with a JSON schema, so the batch comes
back typed. It runs on a thread and next_batch answers None until it returns, so a
tick never waits on a model. Plan is asked only when nothing can move on its own,
which is the barrier the in-session loop kept at the turn boundary. Each call and its
answer is kept under runs/<run-id>/plan/ for the retrospective and for debugging.
"""

import hashlib
import json
import threading
import time
from pathlib import Path

from ..common import read_json, write_json
from ..providers.claude_code import run_once
from .engine import GATE_TYPES
from .plan import GateDraft, PlanBatch, UnitDraft

TIERS = ("haiku", "sonnet", "opus")
LEVELS = ("L0", "L1", "L2", "L3")
BACKOFF_SECONDS = 120

OPTION = {"type": "object", "required": ["option", "consequence"], "additionalProperties": False,
          "properties": {"option": {"type": "string"}, "consequence": {"type": "string"},
                         "recommended_because": {"type": "string"}}}
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["done", "phase", "rationale", "units", "gates"],
    "properties": {
        "done": {"type": "boolean"},
        "phase": {"type": "string"},
        "next_phase": {"type": ["string", "null"]},
        "rationale": {"type": "string"},
        "units": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["key", "agent", "expected_outcome", "brief", "declared_paths", "depends_on",
                         "risk_baseline", "model_tier"],
            "properties": {
                "key": {"type": "string"}, "agent": {"type": "string"},
                "expected_outcome": {"type": "string"}, "brief": {"type": "string"},
                "declared_paths": {"type": "array", "items": {"type": "string"}},
                "depends_on": {"type": "array", "items": {"type": "string"}},
                "risk_baseline": {"enum": list(LEVELS)}, "model_tier": {"enum": list(TIERS)},
                "executable_check": {"type": ["string", "null"]}}}},
        "gates": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["checkpoint_type", "prompt", "holds", "options"],
            "properties": {
                "checkpoint_type": {"type": "string"}, "prompt": {"type": "string"},
                "holds": {"type": "array", "items": {"type": "string"}},
                "options": {"type": "array", "minItems": 1, "items": OPTION},
                "artifact_ref": {"type": "string"},
                "decisions": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["decision_id", "kind", "prompt"],
                    "properties": {"decision_id": {"type": "string"},
                                   "kind": {"enum": ["question", "prd-approval", "architecture-options-selection",
                                                     "design-direction-selection", "default-review"]},
                                   "prompt": {"type": "string"}}}}}}},
    },
}

PROMPT = """You are the Plan step of the Springer harness daemon, not a session the harness
dispatches. Return the next WIP-bounded batch for run {run_id} as the JSON the schema
fixes, and do nothing else: write no file, dispatch no agent, open no gate yourself.

The harness then creates each unit, runs it as a fresh headless session of its agent in
its own git worktree off the default branch, checks it mechanically, and asks you again
once nothing is in flight. A session sees only its brief, so each unit's brief must name
the files to read in order (docs/brief.md, the artifacts under runs/{run_id}/artifacts/,
docs/), the skills to follow, the gating commands, and whether the outcome is run
artifacts and docs (committed to its branch, which the harness merges itself) or a pull
request (pushed and opened with spgr-create-pr, then gated by risk).

Read first, in order: docs/brief.md, .claude/references/pdca-harness.md (the profile
table, the phase set for this profile, autonomy, walking skeleton), and the run state
below. Follow your agent instructions for routing, the phase gate, and the profile.

Rules for the schema:
- key: a short unique name for a new unit. Never reuse a key in "keys used".
- depends_on: keys from "keys used" or from this batch.
- agent: one of {agents}.
- declared_paths: the repo paths the unit may write. Units in one batch must not overlap.
- risk_baseline: L0 for docs and artifacts, L2 for code that touches auth, data model,
  billing, infra, or CI, L3 for a unit that must not start before a person decides.
- gates: only the gates the autonomy level fires (under standard, one direction-review
  holding the units that need the picked option and direction). holds names unit keys.
- When the run brief's lane is polish, the run takes the one issue in run_brief.issue,
  per Lanes in the reference: one implementing unit, its review, at most two verticals by
  the paths it touches, and the product check, ending in one pull request. Write no PRD,
  story, criteria, or ADR artifact unless the change is on the gate list. Every ruling in
  run_brief.pinned_rulings binds.
- A unit in blocked, gated, or planned behind a gate is waiting on a person, and the
  answer resumes that same unit. Never route its work again under a new key.
- done: true only when the profile's work is finished and nothing remains to route.
  Return an empty units list with done false when everything left is held.

Run state:
{state}
"""


def normalize(output, text=None):
    """Defaults for what a reply parsed from text may leave out, where the schema
    would have required it. A reply that is not an object stays as it is."""
    if not isinstance(output, dict):
        return output
    output = {"done": False, "phase": "planning", "next_phase": None, "units": [], "gates": [], **output}
    output.setdefault("rationale", "")
    if not output["rationale"] and text:
        output["rationale"] = _summary(text.rsplit("```", 1)[-1], 400)
    output["units"] = [{"expected_outcome": u.get("brief", "")[:200], "declared_paths": [], "depends_on": [],
                        "risk_baseline": "L0", "model_tier": "sonnet", **u} for u in output["units"]]
    output["gates"] = [{"holds": [], "options": [{"option": "proceed", "consequence": "The held units start."}], **g}
                       for g in output["gates"]]
    return output


def _summary(text, limit=600):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit] + "..."


class OrchestratorPlanner:
    def __init__(self, project_path, run_id, kind, binary="claude", model="sonnet"):
        self.project = Path(project_path)
        self.run_id = run_id
        self.kind = kind
        self.binary = binary
        self.model = model
        self.run_dir = self.project / "runs" / run_id
        self.folder = self.run_dir / "plan"
        self._thread = None
        self._answer = None
        self._error_at = 0
        self._asked_for = None  # the state the last answer was for
        self._lock = threading.Lock()

    # --- the Planner protocol ---

    def finished(self):
        latest = self._latest()
        return bool(latest and latest.get("output", {}).get("done") and not latest["output"].get("units"))

    def next_batch(self, snapshot):
        if getattr(snapshot, "active", snapshot.nonterminal):
            return None  # something can still move on its own
        with self._lock:
            if self._answer is not None:
                answer, self._answer = self._answer, None
                return self._to_batch(answer)
            if self._thread and self._thread.is_alive():
                return None
            if time.time() - self._error_at < BACKOFF_SECONDS or self.finished():
                return None
            # An empty answer stands until something changes (e.g. a gate is answered).
            if self._asked_for == self._fingerprint():
                return None
            self._thread = threading.Thread(target=self._ask, name=f"plan-{self.run_id}", daemon=True)
            self._thread.start()
        return None

    # --- the call ---

    def _agents(self):
        return sorted(p.stem for p in (self.project / ".claude" / "agents").glob("spgr-agent-*.md"))

    def state(self):
        brief = read_json(self.run_dir / "run-brief.json") or {}
        units = []
        for spec_path in sorted((self.run_dir / "units").glob("U-*/spec.json")):
            spec = read_json(spec_path)
            state = read_json(spec_path.parent / "state.json") or {}
            last = (state.get("sessions") or [None])[-1]
            ret = spec_path.parent / "sessions" / last / "return.txt" if last else None
            units.append({"unit_id": spec["unit_id"], "agent": spec["agent"], "state": state.get("state"),
                          "expected_outcome": spec["expected_outcome"], "pr": state.get("pr"),
                          "return": _summary(ret.read_text()) if ret and ret.exists() else None})
        gates = []
        for path in sorted((self.run_dir / "artifacts").glob("G-*.json")):
            content = (read_json(path) or {}).get("content", {})
            gates.append({"type": content.get("checkpoint_type"), "prompt": content.get("decision_prompt"),
                          "response": content.get("response"), "holds": content.get("holds"),
                          "decisions": [{"prompt": d.get("prompt"), "response": d.get("response")}
                                        for d in content.get("decisions") or []]})
        artifacts = sorted(p.name for p in (self.run_dir / "artifacts").glob("*.json") if not p.name.startswith("G-"))
        return {"run_brief": brief.get("content", brief), "keys_used": read_json(self.run_dir / "unit-keys.json", {}),
                "units": units, "gates": gates, "artifacts": artifacts,
                "earlier_plans": [p.get("output", {}).get("rationale") for p in self._plans()]}

    def _fingerprint(self):
        state = self.state()
        state.pop("earlier_plans")
        return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()

    def _plans(self):
        return [read_json(p) for p in sorted(self.folder.glob("plan-*.json"))] if self.folder.is_dir() else []

    def _latest(self):
        plans = self._plans()
        return plans[-1] if plans else None

    def _ask(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        n = len(list(self.folder.glob("plan-*.json"))) + 1
        state = self.state()
        self._asked_for = self._fingerprint()
        prompt = PROMPT.format(run_id=self.run_id, agents=", ".join(self._agents()),
                               state=json.dumps(state, indent=1))
        record = {"n": n, "asked_at": time.time(), "prompt": prompt}
        try:
            found = run_once(self.binary, self.project, prompt, agent="spgr-agent-orchestrator", model=self.model,
                             schema=SCHEMA, log=self.folder / f"plan-{n:03d}.log")
            found["output"] = normalize(found["output"], found.get("text"))
            problems = self.problems(found["output"], state)
            if problems:
                raise ValueError("; ".join(problems))
            record.update(output=found["output"], cost=found["cost"], seconds=found["seconds"])
            write_json(self.folder / f"plan-{n:03d}.json", record)
            with self._lock:
                self._answer = found["output"]
        except Exception as exc:  # a failed Plan is retried after a backoff, never a crash
            record["error"] = str(exc)[:2000]
            write_json(self.folder / f"error-{n:03d}.json", record)
            self._error_at = time.time()
            self._asked_for = None

    def problems(self, output, state):
        if not isinstance(output, dict):
            return ["no structured output"]
        found, agents = [], set(self._agents())
        used = set(state["keys_used"])
        keys = [u["key"] for u in output.get("units", [])]
        if len(keys) != len(set(keys)):
            found.append("a key repeats in the batch")
        for unit in output.get("units", []):
            if unit["key"] in used:
                found.append(f"key {unit['key']} is already used")
            if unit["agent"] not in agents:
                found.append(f"{unit['agent']} is not an agent of this project")
            for dep in unit["depends_on"]:
                if dep not in used and dep not in keys:
                    found.append(f"{unit['key']} depends on unknown key {dep}")
        for gate in output.get("gates", []):
            if gate["checkpoint_type"] not in GATE_TYPES:
                found.append(f"{gate['checkpoint_type']} is not a gate type ({', '.join(GATE_TYPES)})")
        return found

    def _to_batch(self, output):
        units = [UnitDraft(key=u["key"], agent=u["agent"], expected_outcome=u["expected_outcome"], brief=u["brief"],
                           declared_paths=tuple(u["declared_paths"]), depends_on=tuple(u["depends_on"]),
                           risk_baseline=u["risk_baseline"], model_tier=u["model_tier"],
                           executable_check=u.get("executable_check")) for u in output["units"]]
        # A gate may name work not planned yet (the direction review comes before the
        # units that need its answer). It holds what exists, and nothing new is
        # planned until it is answered, because the run state does not change.
        known = set(read_json(self.run_dir / "unit-keys.json", {})) | {u.key for u in units}
        gates = [GateDraft(checkpoint_type=g["checkpoint_type"], prompt=g["prompt"],
                           holds=tuple(k for k in g["holds"] if k in known),
                           options=tuple(g["options"]), decisions=tuple(g.get("decisions") or ()),
                           artifact_ref=g.get("artifact_ref") or "none") for g in output["gates"]]
        if not units and not gates:
            return None
        return PlanBatch(output["phase"], output["rationale"], units, gates, next_phase=output.get("next_phase"),
                         barrier=False)


def orchestrator_factory(project_path_of, binary="claude"):
    """One planner per run, like the canned factory. project_path_of(slug) resolves late,
    so the factory can be built before the daemon it serves."""
    planners = {}

    def factory(slug, run_id, kind):
        key = (slug, run_id)
        if key not in planners:
            planners[key] = OrchestratorPlanner(project_path_of(slug), run_id, kind, binary)
        return planners[key]

    return factory
