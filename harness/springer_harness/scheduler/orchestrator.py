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
import re
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

GATING_KINDS = ("test", "check", "product")
# Agents whose unit writes code and so proves it with a test the harness runs. QA is not
# here: its acceptance tests are written to fail until the code exists.
BUILD_AGENTS = ("spgr-agent-backend-developer", "spgr-agent-frontend-developer", "spgr-agent-mobile-developer")
GATING_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
GATING = {"type": "object", "required": ["name", "command", "kind"], "additionalProperties": False,
          "properties": {"name": {"type": "string"}, "command": {"type": "string"},
                         "kind": {"enum": list(GATING_KINDS)}, "count_regex": {"type": "string"}}}
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
                         "risk_baseline", "model_tier", "gating_commands"],
            "properties": {
                "key": {"type": "string"}, "agent": {"type": "string"},
                "expected_outcome": {"type": "string"}, "brief": {"type": "string"},
                "declared_paths": {"type": "array", "items": {"type": "string"}},
                "depends_on": {"type": "array", "items": {"type": "string"}},
                "risk_baseline": {"enum": list(LEVELS)}, "model_tier": {"enum": list(TIERS)},
                "executable_check": {"type": ["string", "null"]},
                "gating_commands": {"type": "array", "items": GATING},
                "story_ids": {"type": "array", "items": {"type": "string"}}}}},
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
docs/), the skills to follow, and whether the outcome is run artifacts and docs
(committed to its branch, which the harness merges itself) or a pull request (pushed and
opened with spgr-create-pr, then gated by risk). The gating commands go in the unit's
gating_commands, not only in the brief: the harness runs them itself at the branch head
after the session returns, and their result is the evidence the merge reads.

Read first, in order: docs/brief.md, .claude/references/pdca-harness.md (the profile
table, the phase set for this profile, autonomy, walking skeleton), and the run state
below. Follow your agent instructions for routing, the phase gate, and the profile.

Rules for the schema:
- key: a short unique name for a new unit. Never reuse a key in "keys used".
- depends_on: keys from "keys used" or from this batch.
- agent: one of {agents}.
- declared_paths: the repo paths the unit may write. Units in one batch must not overlap.
- gating_commands: what proves the unit's code, each {{name, command, kind}}. name is
  lowercase-kebab and unique in the unit. kind is test for a test runner (it must print
  a count of tests run, e.g. node --test, vitest, pytest, or add count_regex), check for
  lint, typecheck, build, or a verification script judged by its exit code, and product
  for the product check. A unit of {build_agents} names at least one test command. The
  walking-skeleton or scaffold story sets up the test runner and names its test command,
  so every later story has one to extend. A docs or artifact unit names none.
- story_ids: the backlog items the unit builds (e.g. STORY-2026-046), from the
  prioritized-backlog artifact, so the board shows each story where its unit is. Empty
  for work outside the backlog (the PRD, a design unit, a vertical consult).
- risk_baseline: L0 for docs and artifacts, L2 for code that touches auth, data model,
  billing, infra, or CI, L3 for a unit that must not start before a person decides.
- gates: only the gates the autonomy level fires (under standard, one direction-review
  holding the units that need the picked option and direction). holds names unit keys.
- When the run brief's lane is polish, the run takes the one issue in run_brief.issue,
  per Lanes in the reference: one implementing unit, at most two verticals by the paths it
  touches, and the product check, ending in one pull request. The harness adds the code
  review to every pull request itself, so plan no spgr-agent-code-reviewer unit. A vertical
  audits the implementing unit's branch and returns its findings as an artifact, and fixes
  go back to the implementing unit, not into a pull request of the vertical's own. Write no PRD,
  story, criteria, or ADR artifact unless the change is on the gate list. The implementing
  unit's story_ids is run_brief.story_ids, the issue's item on the project backlog. Every
  ruling in run_brief.pinned_rulings binds.
- A unit in blocked, gated, or planned behind a gate is waiting on a person, and the
  answer resumes that same unit. Never route its work again under a new key.
- A unit whose PR is open (state gated) is not a reason to wait. Work that builds on it
  depends_on its key: that unit's worktree starts from the open PR's branch, its own PR
  stacks on that branch, and it merges after the first one. Route that work now.
- done: true only when the profile's work is finished and nothing remains to route.
  Return an empty units list with done false when everything left is held.

{refused}Run state:
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
                        "risk_baseline": "L0", "model_tier": "sonnet", "gating_commands": [], **u}
                       for u in output["units"]]
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
        self._refused = None  # why the last answer was refused, read by the next ask
        self._lock = threading.Lock()

    # --- the Planner protocol ---

    def finished(self):
        latest = self._latest()
        return bool(latest and latest.get("output", {}).get("done") and not latest["output"].get("units"))

    def latest_rationale(self):
        latest = self._latest()
        return (latest or {}).get("output", {}).get("rationale") or None

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
        refused = (f"Your last answer was refused: {self._refused}. Return a batch without that problem.\n\n"
                   if self._refused else "")
        prompt = PROMPT.format(run_id=self.run_id, agents=", ".join(self._agents()), refused=refused,
                               build_agents=", ".join(BUILD_AGENTS), state=json.dumps(state, indent=1))
        record = {"n": n, "asked_at": time.time(), "prompt": prompt}
        try:
            found = run_once(self.binary, self.project, prompt, agent="spgr-agent-orchestrator", model=self.model,
                             schema=SCHEMA, log=self.folder / f"plan-{n:03d}.log")
            found["output"] = normalize(found["output"], found.get("text"))
            problems = self.problems(found["output"], state)
            if problems:
                raise ValueError("; ".join(problems))
            self._refused = None
            record.update(output=found["output"], cost=found["cost"], seconds=found["seconds"])
            write_json(self.folder / f"plan-{n:03d}.json", record)
            with self._lock:
                self._answer = found["output"]
        except Exception as exc:  # a failed Plan is retried after a backoff, never a crash
            record["error"] = str(exc)[:2000]
            self._refused = str(exc)[:1000]
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
            gating = unit.get("gating_commands") or []
            names = [g.get("name") for g in gating if isinstance(g, dict)]
            if len(names) != len(gating) or any(not isinstance(n, str) or not GATING_NAME.match(n) for n in names) \
                    or len(set(names)) != len(names) \
                    or any(g.get("kind") not in GATING_KINDS or not str(g.get("command") or "").strip() for g in gating):
                found.append(f"{unit['key']} has a gating command without a unique lowercase-kebab name, a "
                             f"command, and a kind from {', '.join(GATING_KINDS)}")
            elif unit["agent"] in BUILD_AGENTS and not any(g["kind"] == "test" for g in gating):
                found.append(f"{unit['key']} writes code but names no test gating command. The walking-skeleton "
                             "or scaffold story sets up the test runner")
        for gate in output.get("gates", []):
            if gate["checkpoint_type"] not in GATE_TYPES:
                found.append(f"{gate['checkpoint_type']} is not a gate type ({', '.join(GATE_TYPES)})")
        return found

    def _to_batch(self, output):
        units = [UnitDraft(key=u["key"], agent=u["agent"], expected_outcome=u["expected_outcome"], brief=u["brief"],
                           declared_paths=tuple(u["declared_paths"]), depends_on=tuple(u["depends_on"]),
                           risk_baseline=u["risk_baseline"], model_tier=u["model_tier"],
                           executable_check=u.get("executable_check"),
                           gating_commands=tuple(dict(g) for g in u.get("gating_commands") or ()),
                           story_ids=tuple(u.get("story_ids") or ()))
                 for u in output["units"]]
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
