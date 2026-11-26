"""One run's scheduler: the ten-step tick from the state model, and crash recovery.

Every step is idempotent against the files on disk, so a tick interrupted anywhere
is safe to run again. The engine keeps nothing durable in memory. Session handles are
the only in-memory state, and losing them is what a crash is.
"""

import dataclasses
import os
import re
import signal
import subprocess
from pathlib import Path

from ..check import review
from ..check.gating import GatingRuns
from ..check.mechanical import cannot_run, fails_at, hold_for_person, mechanical_check, needs_gating
from ..check.risk import LEVELS, baseline_for, triggers
from ..check.verdict import ADDENDA, BLOCK, POLICY, REDISPATCH, RETRY, read_result, risk_for
from ..common import agent_has_shell, artifact_header, iso, next_id, parse_iso, read_json, write_json
from ..errors import IllegalTransition, RunExternallyHeld
from ..providers.coding_agent import CheckResult, SpawnRequest
from ..state.cycles import CycleStore
from ..state.backlog import BacklogStore
from ..state.brief import BriefStore
from ..state.gates import GateStore
from ..state.ledger import Ledger
from ..state.lock import RunLock
from ..state.projection import is_paused, rebuild
from ..state.sessions import SessionStore
from ..state.units import MAX_RETRIES, TIERS, UnitStore, is_terminal
from .plan import Snapshot
from .worktrees import RULINGS

RETRY_NOTE_CHARS = 1500
UNLOCK = "unlock"  # the gate option that records a config-unlock ruling


def gating_note(commands):
    """What the session is told about the commands the harness runs after it returns."""
    if not commands:
        return ""
    lines = "\n".join(f"- {c['name']} ({c['kind']}): {c['command']}" for c in commands)
    return ("\n\nGating commands. The harness runs these itself at your branch head after you return, and "
            "their result is the evidence the merge reads. Commit all your work before you return. Run them "
            "yourself while you work so you return green, and take no receipt for them: the harness's run is "
            "the receipt. A test command must print a count of tests run.\n"
            + lines)

def criteria_note(project_path, story_ids):
    """The acceptance criteria of the unit's stories, quoted into its brief. A pointer to
    the criteria artifact was not enough: a unit that could not read it built a story
    without two of its named checks. The newest run's criteria for a story win."""
    if not story_ids:
        return ""
    found = {}
    paths = sorted(Path(project_path).glob("runs/*/artifacts/acceptance-criteria*.json"),
                   key=lambda p: p.stat().st_mtime)
    for path in paths:
        for item in ((read_json(path) or {}).get("content") or {}).get("criteria") or []:
            if isinstance(item, dict) and item.get("story_ref") in story_ids and item.get("ac_id"):
                found.setdefault(item["story_ref"], {})[item["ac_id"]] = item
    if not found:
        return ""
    lines = []
    for story in story_ids:
        for item in (found.get(story) or {}).values():
            check = f" Check: {item['check']}" if item.get("check") else ""
            lines.append(f"- {item['ac_id']}: {item.get('then') or item.get('when') or ''}{check}")
    return ("\n\nAcceptance criteria. Every one must hold when you return, and every check a criterion "
            "names must exist and pass, even when the brief above does not repeat it.\n" + "\n".join(lines))


GATE_TYPES = ("direction-review", "architecture-options-selection", "architecture-confirmation", "prd-approval",
              "design-direction-selection", "pr-merge", "security-compliance-flag", "scope-change", "discovery-go-no-go",
              "structure-confirmation", "scope-review", "taste-review", "production-release", "provisioning-required")
# Gates only the harness opens. A plan or a unit asking for one is told to ask again:
# the production release is the harness's own gate, run on the project's release command.
REQUESTABLE_GATE_TYPES = tuple(t for t in GATE_TYPES if t != "production-release")
DECISION_KINDS = ("question", "prd-approval", "architecture-options-selection", "design-direction-selection",
                  "default-review")
MAX_REDISPATCHES = 3
MERGE_OPTIONS = [
    {"option": "approve", "consequence": "It merges, and stacked work can follow.",
     "recommended_because": "Reviewed and green. Read the findings first."},
    {"option": "send_back", "consequence": "A fresh session fixes it. One retry is spent."},
]
START_OPTIONS = [
    {"option": "proceed", "consequence": "The held units start.",
     "recommended_because": "The input they were missing is now present."},
    {"option": "cancel", "consequence": "The held units are cancelled."},
]
ADJUDICATE_OPTIONS = [
    {"option": "retry", "consequence": "A fresh session tries again.",
     "recommended_because": "The escalation names a cause that can now be fixed."},
    {"option": "cancel", "consequence": "The unit is cancelled and its dependents are blocked."},
]


def overlaps(paths_a, paths_b):
    """Two declared path sets overlap when one path contains or equals the other."""
    def norm(p):
        return p.rstrip("/") + "/"
    return any(norm(a).startswith(norm(b)) or norm(b).startswith(norm(a)) for a in paths_a for b in paths_b)


def _git_out(cwd, *args):
    done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=60)
    return done.returncode, done.stdout.strip()


# A CI failure that is the runner's, not the change's, gets a rerun before a session.
INFRA_FAILURE = re.compile(r"heap out of memory|Reached heap limit|exit code 13[47]\b|runner has received a shutdown"
                           r"|lost communication with the server|No space left on device|ETIMEDOUT|ECONNRESET"
                           r"|the job failed with every step green|a tool install step failed before anything was checked",
                           re.I)
CI_RERUN_GRACE = 180
HOSTED_CI_LABEL = "springer:hosted-ci"


class RunEngine:
    def __init__(self, project_slug, project_path, run_id, provider, planner, source_host, worktrees, window, owner,
                 now, in_flight_total=None, settings=None, release=None):
        self.project_slug = project_slug
        self.project_path = Path(project_path)
        self.run_id = run_id
        self.run_dir = self.project_path / "runs" / run_id
        self.provider = provider
        self.planner = planner
        self.source_host = source_host
        self.worktrees = worktrees
        self.window = window
        self.now = now
        # Every project draws from one usage window, so the room is counted across
        # them. A lone engine counts only its own units.
        self.in_flight_total = in_flight_total or (lambda: len(self.units.by_state("running")))
        self.ledger = Ledger(self.run_dir, run_id, now)
        self.units = UnitStore(self.run_dir, self.ledger, now)
        self.gates = GateStore(self.run_dir, self.ledger, now)
        self.cycles = CycleStore(self.run_dir, run_id, now)
        self.lock = RunLock(self.run_dir, owner, now)
        self.handles = {}
        self.keys = self._load_keys()
        self.settings = settings or (lambda: {"ci_signal": "receipts"})
        self.gating_runs = GatingRuns()
        self._warned = set()  # (unit, session, detail) already written, so a re-read verdict is not again
        # release(by, gate_id) starts the project's deploy and returns (out_dir, None),
        # or (None, why not). None when the daemon offers no releases (the tests' engines).
        self.release = release

    # --- helpers ---

    def sessions(self, unit_id):
        return SessionStore(self.units.unit_dir(unit_id), self.now)

    def _keys_path(self):
        return self.run_dir / "unit-keys.json"

    def _load_keys(self):
        return read_json(self._keys_path(), {})

    def _spec(self, unit_id):
        return self.units.spec(unit_id)

    def _append_note(self, unit_id, text):
        with open(self.units.unit_dir(unit_id) / "redispatch-notes.txt", "a") as fh:
            fh.write(text + "\n")

    def add_note(self, text, by):
        """A person's note for the next session of every unit still open. Returns the units
        it reached. A unit done or cancelled has no next session."""
        reached = []
        for unit_id in self.units.ids():
            if not is_terminal(self.units.state(unit_id)):
                self._append_note(unit_id, f"A note from the human ({by}): {text}")
                reached.append(unit_id)
        return reached

    def _notes(self, unit_id):
        path = self.units.unit_dir(unit_id) / "redispatch-notes.txt"
        return path.read_text() if path.exists() else ""

    def _declared_tier(self, unit_id):
        """The model the unit's agent declares in its frontmatter, or None. A plan once ran
        the Auth, Security and Compliance sign-offs on sonnet, though each declares opus
        because its finding blocks a checkpoint."""
        ref = self._spec(unit_id).get("role_prompt_ref")
        try:
            text = (Path(self.project_path) / ref).read_text() if ref else ""
        except OSError:
            return None
        front = text.split("---", 2)[1] if text.startswith("---") and text.count("---") >= 2 else ""
        for line in front.splitlines():
            key, _, value = line.partition(":")
            if key.strip() == "model" and value.strip() in TIERS:
                return value.strip()
        return None

    def _tier(self, unit_id, state):
        """The spec's tier, never below the agent's declared model (a review unit's tier
        is the engine's, see _review_tier), one up on the second retry (a review's first),
        or the tier a human raised to."""
        spec = self._spec(unit_id)
        index = TIERS.index(spec["model_tier"])
        declared = None if spec.get("review_of") else self._declared_tier(unit_id)
        if declared:
            index = max(index, TIERS.index(declared))
        # A review the engine tiered steps up on its first failure, a unit on its second.
        if state["retries_spent"] >= (1 if spec.get("review_of") else 2):
            index = min(index + 1, len(TIERS) - 1)
        for entry in self.ledger.read():
            line = entry.line
            if line.get("event") == "operation_applied" and line.get("type") == "unit.redispatch" \
                    and line["args"].get("unit_id") == unit_id and line["args"].get("model_tier"):
                index = max(index, TIERS.index(line["args"]["model_tier"]))
        return TIERS[index]

    def _base_for(self, unit_id):
        """Main, or the open PR branch of a dependency for a stacked unit. A review
        unit sits on the head of the PR it reviews."""
        reviewed = self._spec(unit_id).get("review_of")
        if reviewed:
            return self.units.state(reviewed)["pr"]["branch"]
        for dep in self._spec(unit_id)["dependencies"]:
            dep_state = self.units.state(dep)
            if dep_state["state"] != "done" and dep_state.get("pr"):
                return dep_state["pr"]["branch"]
        return self.worktrees.default_branch()

    def open_units(self):
        return [self.units.state(u) for u in self.units.ids()]

    def paused(self):
        return is_paused(self.ledger)

    # --- the tick ---

    def tick(self):
        """Returns a word for what the tick did: held, parked, complete, or ticked."""
        if not self.lock.refresh():
            self.project()
            return "held"
        record = self.window.sample(self.provider.usage_signal())
        in_flight = bool(self.units.by_state("running"))
        if in_flight:
            self.ledger.append("window_sample", provider=record["provider"], used_fraction=record["used_fraction"],
                               resets_at=record["resets_at"])
        if self.window.parked():
            self.project()
            return "parked"
        self.reconcile()
        self.join()
        self.check()
        self.resolve_gates()
        self.close_cycles()
        if self.cycles.is_complete():
            self.project()
            return "complete"
        paused = self.paused()
        if not paused:
            self.derive_ready()
            self.plan()
            self.derive_ready()
            self.dispatch()
        self.finish_if_done()
        if not paused and not self.cycles.is_complete():
            self.ask_when_idle()
        self.project()
        return "complete" if self.cycles.is_complete() else "ticked"

    def require_writable(self):
        if self.lock.externally_held():
            raise RunExternallyHeld(f"{self.run_id} is held by {self.lock.externally_held()}")

    def project(self):
        return rebuild(self.run_dir, self.run_id, self.ledger, self.units, self.gates, self.cycles, self.now,
                       self.sessions, window=self.window.read())

    # --- step 3: reconcile sessions ---

    def reconcile(self):
        for state in self.units.by_state("running"):
            unit_id = state["unit_id"]
            if not state["sessions"]:
                # The claim stood and the spawn raised (the provider's binary was being
                # replaced), so there is no session to reconcile. The unit goes again.
                self.units.transition(unit_id, "redispatch", "the session never started")
                continue
            session_id = state["sessions"][-1]
            handle = self.handles.get((unit_id, session_id))
            store = self.sessions(unit_id)
            record = store.get(session_id)
            if record["state"] == "exited":
                continue  # a crash fell between the exit and the join
            if handle is None:
                self._mark_dead(unit_id, store, record)
                continue
            self._drain(unit_id, store, record, handle)
            done = handle.exit()
            if done is None and not handle.alive():
                self._mark_dead(unit_id, store, record)
            elif done is None and self._over_budget(unit_id, record):
                handle.kill()
                self._end_session(unit_id, store, record, "killed", "killed", None)
                self.units.transition(unit_id, "redispatch", "wall-clock budget exceeded")
            elif done is not None:
                self._on_exit(unit_id, store, record, done)

    def _over_budget(self, unit_id, record):
        return self.now() - parse_iso(record["started_at"]) > self._spec(unit_id)["budget"]["wall_clock_seconds"]

    def _drain(self, unit_id, store, record, handle):
        events = handle.poll()
        if not events:
            return
        store.append_stream(record["session_id"], events)
        usage = handle.usage()
        added = usage.input_tokens + usage.output_tokens - record["input_tokens"] - record["output_tokens"]
        record.update(state="streaming", input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                      context_percent_at_exit=usage.context_percent, cost_usd_list_price=usage.cost_usd)
        store.save(record)
        self.window.add_tokens(added)
        self.ledger.append("session_usage", unit_id=unit_id, session_id=record["session_id"],
                           input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                           context_percent=usage.context_percent, cost=usage.cost_usd)

    def _end_session(self, unit_id, store, record, state, outcome, code):
        store.finish(record, state, outcome, code)
        self.ledger.append("session_exited", unit_id=unit_id, session_id=record["session_id"], code=code,
                           outcome=outcome)
        self.handles.pop((unit_id, record["session_id"]), None)

    def _mark_dead(self, unit_id, store, record):
        self._end_session(unit_id, store, record, "dead", "dead", None)
        self.units.transition(unit_id, "abandoned", "the session died without a return")
        self.units.transition(unit_id, "redispatch", "abandoned, no retry spent")

    def _on_exit(self, unit_id, store, record, done):
        if done.outcome == "handoff":
            self._end_session(unit_id, store, record, "handoff", "handoff", done.code)
            self._spawn(unit_id, self.units.state(unit_id), handoff_from=record["session_id"])
        elif done.outcome == "killed":
            self._end_session(unit_id, store, record, "killed", "killed", done.code)
            self.units.transition(unit_id, "redispatch", "the provider killed the session")
        else:
            self._end_session(unit_id, store, record, "exited", "return", done.code)

    # --- step 4: join returns ---

    def join(self):
        for state in self.units.by_state("running"):
            unit_id = state["unit_id"]
            record = self.sessions(unit_id).get(state["sessions"][-1])
            if record and record["state"] == "exited":
                self.units.transition(unit_id, "returned", "session returned")

    # --- step 5: Check ---

    def check(self):
        for state in self.units.by_state("returned"):
            self.units.transition(state["unit_id"], "checking", "check began")
        for state in self.units.by_state("checking"):
            self._check_one(state)

    def _check_one(self, state):
        unit_id = state["unit_id"]
        session_dir = self.sessions(unit_id).dir(state["sessions"][-1])
        requested = self._raise_requested_gate(unit_id, state["sessions"][-1], session_dir)
        if requested is True:
            return
        if requested:
            # A session that asked for a person and was refused must not pass silently:
            # its question would be lost and the work would go on as if answered.
            self._on_failure(unit_id, state, CheckResult(status="fail", failure_class="request", detail=requested))
            return
        spec = self._spec(unit_id)
        if not agent_has_shell(self.project_path, spec["agent"]):
            # Its role has no shell, so the files it wrote sit uncommitted, and every retry
            # failed the same way. The harness commits them, and Check validates the run store.
            committed = self.worktrees.commit_declared(
                unit_id, spec.get("declared_paths") or [], f"docs: commit what {unit_id} ({spec['agent']}) wrote")
            if committed:
                self.ledger.append("committed_for_unit", unit_id=unit_id, paths=committed)
        result = self._result(unit_id, state, session_dir)
        if result is None:
            return  # the gating commands are still running, and a later tick reads the verdict
        if result.status != "pass":
            self._on_failure(unit_id, state, result)
            return
        if self._spec(unit_id).get("review_of"):
            self._finish_review(unit_id, state, result)
            return
        spec = self._spec(unit_id)
        changed = self.worktrees.changed_paths(unit_id, self._base_for(unit_id))
        if changed:
            # The PR is scored by what it changes, not by what the last session said it
            # touched: a fix retry that annotated lint lines scored a migration PR L1.
            result = dataclasses.replace(result, touched_paths=tuple(sorted({*result.touched_paths, *changed})))
        reason = spec.get("risk_reason")
        level = risk_for(result, spec["risk_baseline"], reason)
        planned = [f"plan:{reason}"] if baseline_for(spec["risk_baseline"], reason) == "L2" else []
        write_json(self.units.unit_dir(unit_id) / "risk.json",
                   {"level": level, "triggers": triggers(result.touched_paths) + planned,
                    "findings": list(result.findings)})
        if self._lands_nothing(unit_id, result):
            # Nothing of its own to land. Its findings are in the run store, and a stacked
            # parent's code is that parent's change, never a second one.
            self.units.transition(unit_id, "done", "no change of its own")
            self._release(unit_id)
            return
        code = [] if result.outcome == "pr" or not self.worktrees.path(unit_id).exists() \
            else self.worktrees.code_paths(unit_id)
        if code and not hasattr(self.source_host, "open"):
            # Reported as an artifact but it changes code, and on GitHub only the session
            # can open the PR. Integrating it would land code with no gate.
            self._on_failure(unit_id, state, CheckResult(
                status="fail", failure_class="defect",
                detail=f"the outcome was an artifact but the branch changes code ({', '.join(code[:5])}). Open a PR."))
            return
        if (result.outcome == "pr" and result.pr) or code:
            pr = self._opened(unit_id, result.pr or {"branch": self.worktrees.branch(unit_id)})
            self.units.transition(unit_id, "gated", f"PR open, risk {level}", pr=pr)
        else:
            self._integrate(unit_id)
            self.units.transition(unit_id, "done", "artifact confirmed")
        self._release(unit_id)

    def _opened(self, unit_id, pr):
        """On GitHub the session opened the PR and reports its number. On the local host
        the harness opens the change, and a retry reuses the change its branch has."""
        if pr.get("number") is not None and hasattr(self.source_host, "push"):
            # The session opened the PR, and a later session's fix is only on the local
            # branch. Unpushed, the PR keeps its old CI result and no approval can merge it.
            self.source_host.push(self.project_slug, pr.get("branch") or self.worktrees.branch(unit_id))
        if pr.get("number") is not None or not hasattr(self.source_host, "open"):
            return pr
        # The harness picks the base. A session reports the branch it started on, which is
        # stale once the parent it stacked on has merged, and a reused change keeps the base
        # it was opened with unless it is moved.
        base, branch = self._base_for(unit_id), pr.get("branch") or self.worktrees.branch(unit_id)
        number = self.source_host.open(self.project_slug, branch, base, self._spec(unit_id)["expected_outcome"][:120])
        if hasattr(self.source_host, "retarget"):
            self.source_host.retarget(self.project_slug, number, base)
        return {"number": number, "branch": branch, "base": base}

    def _result(self, unit_id, state, session_dir):
        """A real provider's session gets the mechanical Check. The mock writes the
        result it was scripted to, so its result.json is the verdict."""
        if not getattr(self.provider, "mechanical", False):
            return read_result(session_dir)
        record = self.sessions(unit_id).get(state["sessions"][-1])
        said = read_result(session_dir)
        gating = self._gating(unit_id, said)
        if gating:
            # The commands run on a thread, because the tick holds the daemon lock and a
            # product check can take minutes. None leaves the unit in checking.
            if said.status == "pass" and needs_gating(said):
                verdict = self.gating_runs.poll((unit_id, state["sessions"][-1]), gating, session_dir,
                                                self.worktrees.path(unit_id), self._baseline(unit_id))
                if verdict is None:
                    return None
                self._record_product_checks(unit_id, gating, session_dir)
                if verdict:
                    return CheckResult(status="fail", failure_class="defect", detail=verdict)
        result = mechanical_check(session_dir, self.worktrees.path(unit_id), self.run_dir, self.project_path,
                                  unit_id, parse_iso(record["started_at"]),
                                  require_receipts=not self._spec(unit_id).get("gating_commands")
                                  and self._ci_signal() in ("receipts", "both"))
        warnings = self.gating_runs.warnings(session_dir) if gating else []
        said = (unit_id, state["sessions"][-1], "; ".join(warnings))
        if warnings and result.status == "pass" and said not in self._warned:
            # A tick that fails after the Check reads the same verdict again on the next.
            self._warned.add(said)
            self.ledger.append("check_warning", unit_id=unit_id, detail=said[2])
        return hold_for_person(result, warnings)

    # --- review ---

    def _reviews(self):
        """A provider that runs real sessions gets a Code Reviewer on every PR. The mock
        opts in per test, so a scripted run is not made to script a reviewer."""
        return getattr(self.provider, "reviews", False)

    def _open_review(self, unit_id):
        """A review unit for the PR the unit just opened. The PR waits on its verdict."""
        state = self.units.state(unit_id)
        spec = self._spec(unit_id)
        pr = state["pr"]
        review_id = self.units.next_id()
        out = self.units.unit_dir(review_id) / "review" / "package.md"
        head = self._branch_head(pr["branch"])
        earlier = self._earlier_review(unit_id, state, head)
        base = earlier["head"] if earlier else pr.get("base") or self.worktrees.default_branch()
        problem = review.cut_package(self.project_path, base, pr["branch"], out,
                                     spec["declared_paths"]) if self._mechanical() else None
        session_dir = self.sessions(unit_id).dir(state["sessions"][-1])
        report = session_dir / "return.txt"
        brief = review.BRIEF.format(number=pr["number"], unit_id=unit_id, branch=pr["branch"], base=pr.get("base"),
                                    expected=spec["expected_outcome"],
                                    package=out if problem is None else f"not cut ({problem}), so read the diff",
                                    report=report.read_text()[-4000:] if report.exists() else "(no report)",
                                    artifacts=self.run_dir / "artifacts")
        if earlier:
            brief += review.DELTA.format(review_id=earlier["review_id"], head=earlier["head"],
                                         findings=earlier["findings"] or "(none listed)")
        self.units.create({"unit_id": review_id, "cycle_id": spec["cycle_id"], "agent": review.REVIEWER,
                           "role_prompt_ref": f".claude/agents/{review.REVIEWER}.md",
                           "model_tier": self._review_tier(unit_id, state),
                           "brief": brief, "input_artifact_refs": [], "expected_outcome": f"A verdict on PR {pr['number']}",
                           "workstream": "review", "declared_paths": [], "allowlist": [], "mcp_config_ref": None,
                           "budget": {"tokens": 200000, "wall_clock_seconds": 1800}, "risk_baseline": "L0",
                           "dependencies": [], "executable_check": None, "review_of": unit_id,
                           "review_session": state["sessions"][-1], "reviewed_head": head})
        self.units.save({**self.units.state(unit_id), "reviews": state.get("reviews", []) + [review_id]})
        self.ledger.append("review_opened", unit_id=unit_id, review_unit=review_id, pr=pr["number"])

    def _review_tier(self, unit_id, state):
        """Sonnet reads the first review of a low-risk PR. A re-review, a PR at L2 or
        above, and a review whose session failed go to Opus (see _tier), so the last
        automated gate before a merge a person does not see is still read by Opus when
        Sonnet asked for changes."""
        if state.get("reviews") or self._level(unit_id) not in ("L0", "L1"):
            return "opus"
        return "sonnet"

    def _branch_head(self, branch):
        for ref in (f"origin/{branch}", branch):
            code, sha = _git_out(self.project_path, "rev-parse", "--verify", "--quiet", ref)
            if code == 0 and sha:
                return sha
        return None

    def _earlier_review(self, unit_id, state, head):
        """The last finished review of this PR, when the new head still contains the head
        it read. A re-review then reads only what changed since and checks the earlier
        findings, instead of the whole PR again. A rebase that dropped the reviewed head
        gets a full review."""
        for review_id in reversed(state.get("reviews") or []):
            verdict = read_json(self.units.unit_dir(unit_id) / "review" / f"{review_id}.json")
            reviewed = self._spec(review_id).get("reviewed_head")
            if not verdict or not reviewed:
                continue
            if not head or reviewed == head:
                return None
            done = subprocess.run(["git", "-C", str(self.project_path), "merge-base", "--is-ancestor", reviewed, head],
                                  capture_output=True, timeout=60)
            if done.returncode != 0:
                return None
            findings = "; ".join(f"{f.get('severity', '')} {f.get('file', '')}: {f.get('detail', '')}".strip()
                                 for f in verdict.get("findings") or [] if isinstance(f, dict))
            return {"review_id": review_id, "head": reviewed, "findings": findings[:4000]}
        return None

    def _mechanical(self):
        return getattr(self.provider, "mechanical", False)

    def _reviewed_head(self, state):
        """True when a review was opened for the PR's current attempt. A retry pushes a
        new head from a new session, so a review of an earlier session does not count."""
        reviews = state.get("reviews") or []
        return bool(reviews) and self._spec(reviews[-1]).get("review_session") == state["sessions"][-1]

    def _review_pending(self, state):
        reviews = state.get("reviews") or []
        return bool(reviews) and not is_terminal(self.units.state(reviews[-1]))

    def _finish_review(self, review_id, state, result):
        """The verdict moves the reviewed unit: approve lets the merge go on with the
        findings attached, request_changes sends it back once, and after the re-review a
        person decides."""
        unit_id = self._spec(review_id)["review_of"]
        if result.verdict not in ("approve", "request_changes"):
            self._on_failure(review_id, state, type(result)(status="fail", failure_class="defect",
                                                            detail="the review left no approve or request_changes verdict"))
            return
        tags = self.units.unit_dir(review_id) / "review" / "package.md.tags.json"
        code_review = result.code_review and str(Path(result.code_review) if Path(result.code_review).is_absolute()
                                                 else self.project_path / result.code_review)
        missing = review.dispositions(self.project_path, tags, code_review) if self._mechanical() else None
        if missing:
            self._on_failure(review_id, state, type(result)(status="fail", failure_class="defect",
                                                            detail=f"incomplete review: {missing}"))
            return
        write_json(self.units.unit_dir(unit_id) / "review" / f"{review_id}.json",
                   {"verdict": result.verdict, "findings": list(result.findings), "code_review": result.code_review})
        self.units.transition(review_id, "done", f"review: {result.verdict}")
        self._release(review_id)
        reviewed = self.units.state(unit_id)
        if reviewed["state"] != "gated":
            return
        risk_path = self.units.unit_dir(unit_id) / "risk.json"
        risk = read_json(risk_path) or {"level": "L0", "triggers": [], "findings": []}
        risk["findings"] = list(risk.get("findings", [])) + list(result.findings)
        risk["review"] = result.verdict
        if result.raised_level and LEVELS.index(result.raised_level) > LEVELS.index(risk["level"]):
            risk["level"] = result.raised_level
        if result.verdict == "request_changes" and len(reviewed.get("reviews", [])) >= review.MAX_REVIEWS:
            # The re-review still asks for changes, so a person decides the merge.
            risk["level"] = max(risk["level"], "L2", key=LEVELS.index)
        write_json(risk_path, risk)
        self.ledger.append("review_finished", unit_id=unit_id, review_unit=review_id, verdict=result.verdict)
        if result.verdict == "request_changes" and len(reviewed.get("reviews", [])) < review.MAX_REVIEWS:
            findings = "; ".join(f"{f.get('severity', '')} {f.get('file', '')}: {f.get('detail', '')}".strip()
                                 for f in result.findings if isinstance(f, dict))
            self._append_note(unit_id, f"The code review requested changes. Fix these and commit to the same branch (push only when your output contract says to): "
                                       f"{findings or result.detail}")
            self.units.transition(unit_id, "retry", "defect: the code review requested changes",
                                  retries_spent=reviewed["retries_spent"] + 1)
            self._retire_merge_gates(unit_id)

    def _integrate(self, unit_id):
        """An artifact unit's commits (a PRD render, design directions) land on the
        default branch at once, so the docs and the design page read them before the
        gate that needs them. Check sends a branch that changes code to a PR instead,
        so nothing here is code and it needs no review."""
        # The merge reads the unit's branch, not its worktree, so a worktree released
        # early (a restart mid-check) never drops the work. A missing branch is reported.
        if subprocess.run(["git", "-C", str(self.project_path), "rev-parse", "--verify", "--quiet",
                           self.worktrees.branch(unit_id)], capture_output=True).returncode:
            self.ledger.append("worktree_kept", unit_id=unit_id, path=str(self.worktrees.path(unit_id)),
                               reason="not integrated: the unit's branch is gone")
            return
        reason = self.worktrees.integrate(unit_id)
        if reason is None:
            self.ledger.append("artifact_integrated", unit_id=unit_id, branch=self.worktrees.branch(unit_id))
            if hasattr(self.source_host, "publish"):
                self.source_host.publish(self.project_slug, self.worktrees.default_branch())
        elif reason != "nothing to integrate":
            self.ledger.append("worktree_kept", unit_id=unit_id, path=str(self.worktrees.path(unit_id)),
                               reason=f"not integrated: {reason}")

    def _raise_requested_gate(self, unit_id, session_id, session_dir):
        """A headless session asks for a person by leaving gate-request.json. Returns True
        when a gate is open, None when there is no request, and the reason when the
        schema would refuse it, which Check treats as a defect. An option written as
        {label} rather than {option} is read as the same thing, because sessions do."""
        path = session_dir / "gate-request.json"
        if not path.exists():
            return None
        request = read_json(path)
        if not isinstance(request, dict):
            return "gate-request.json is not one JSON object"
        options = request.get("options")
        if isinstance(options, list):
            options = [{**o, "option": o.get("option") or o.get("label")} if isinstance(o, dict) else o for o in options]
            options = [{k: v for k, v in o.items() if k in ("option", "consequence", "recommended_because")}
                       if isinstance(o, dict) else o for o in options]
        decisions = request.get("decisions") or []
        problem = None
        if request.get("checkpoint_type") not in REQUESTABLE_GATE_TYPES:
            problem = (f"checkpoint_type {request.get('checkpoint_type')!r} is not one of "
                       f"{sorted(REQUESTABLE_GATE_TYPES)}")
        elif not request.get("decision_prompt"):
            problem = "it has no decision_prompt"
        elif not options or not all(isinstance(o, dict) and o.get("option") and o.get("consequence") for o in options):
            problem = "every option needs an option name and a consequence"
        elif not all(isinstance(d, dict) and d.get("decision_id") and d.get("kind") in DECISION_KINDS and d.get("prompt")
                     for d in decisions):
            problem = f"every decision needs decision_id, prompt, and a kind from {sorted(DECISION_KINDS)}"
        unlock = request.get("unlock_paths") or []
        if not problem and (not isinstance(unlock, list) or not all(
                isinstance(u, dict) and isinstance(u.get("path"), str) and u["path"].strip()
                and str(u.get("reason") or "").strip() for u in unlock)):
            problem = "every unlock_paths entry needs a path and a reason"
        if problem:
            return (f"gate-request.json was refused: {problem}. Write it again as the spgr-notify-human "
                    "skill's step 0 describes, and return.")
        key = f"{unit_id}/{session_id}"
        context = {"gate_request": key}
        if unlock:
            # A config edit the story needs is a ruling the person makes with one answer.
            # The harness, not the session, writes it, because the hook refuses the file
            # to every agent.
            context["unlock_paths"] = [{"path": u["path"].strip(), "reason": str(u["reason"]).strip()} for u in unlock]
            if not any(o["option"] == UNLOCK for o in options):
                named = ", ".join(u["path"] for u in context["unlock_paths"])
                options = [{"option": UNLOCK, "consequence": f"The harness records the ruling for {named}, and the "
                                                             "unit continues with those files editable."}] + options
        # Check runs again after a crash, so the same request must not open two gates.
        if not any(g["content"]["context"].get("gate_request") == key for g in self.gates.all()):
            self.gates.open(request["checkpoint_type"], "L3", [unit_id], request["decision_prompt"], options,
                            artifact_ref=request.get("artifact_ref") or "none", decisions=decisions or None,
                            context=context)
        self.units.transition(unit_id, "blocked", f"waiting on a gate: {request['decision_prompt']}")
        return True

    def _on_failure(self, unit_id, state, result):
        cause = result.failure_class or "defect"
        action = POLICY.get(cause, RETRY)
        if cause in ADDENDA:
            self._append_note(unit_id, ADDENDA[cause])
        if cause == "request":
            # The refusal says how to write the request, and the next session needs it.
            self._append_note(unit_id, f"Check sent the last session back: {result.detail[:RETRY_NOTE_CHARS]}")
        if action == REDISPATCH and self._repeats(state, cause) >= MAX_REDISPATCHES - 1:
            # A redispatch spends no retry, so a cause that does not go away would
            # loop forever. The third in a row asks a person instead.
            self._block(unit_id, state, f"{MAX_REDISPATCHES} {cause} failures in a row: {result.detail}")
        elif action == REDISPATCH:
            self.units.transition(unit_id, "redispatch", f"{cause}: {result.detail}")
        elif action == BLOCK:
            self._block(unit_id, state, f"blocked: {result.detail}")
        elif state["retries_spent"] >= MAX_RETRIES:
            self._block(unit_id, {**state, "retries_spent": state["retries_spent"] + 1},
                        f"retries exhausted: {result.detail}", retries_spent=state["retries_spent"] + 1)
        else:
            # The retry is a fresh session that knows nothing of the last one, so it reads
            # why Check sent it back. Without this a session repeated the same mistake.
            self._append_note(unit_id, f"Check sent the last session back: {result.detail[:RETRY_NOTE_CHARS]}")
            self.units.transition(unit_id, "retry", f"defect: {result.detail}",
                                  retries_spent=state["retries_spent"] + 1)

    def _repeats(self, state, cause):
        """Redispatches for this cause since a person last answered for the unit."""
        count = 0
        for entry in reversed(state["history"]):
            if entry["state"] == "ready" and entry["reason"].startswith("gate "):
                break
            if entry["state"] == "redispatch" and entry["reason"].startswith(f"{cause}:"):
                count += 1
        return count

    def _block(self, unit_id, state, reason, **updates):
        """Blocked always has a card for the human: an escalation and a gate holding it."""
        escalation_id = next_id("E", [p.stem for p in (self.run_dir / "artifacts").glob("E-*.json")])
        artifact = artifact_header(escalation_id, "escalation", "escalation", "v1", self.now())
        artifact["content"] = {"escalation_id": escalation_id, "escalation_type": "blocked", "description": reason,
                               "urgency": "urgent", "routing_target": "human",
                               "originating_agent": self._spec(unit_id)["agent"], "status": "open"}
        write_json(self.run_dir / "artifacts" / f"{escalation_id}.json", artifact)
        self.units.transition(unit_id, "blocked", reason, **updates)
        self.gates.open("scope-change", "L3", [unit_id], f"{unit_id} is blocked: {reason}", ADJUDICATE_OPTIONS,
                        artifact_ref=escalation_id, urgency="urgent")

    def _release(self, unit_id):
        """Released once the unit passes. A failing unit reuses its worktree."""
        if not self.worktrees.path(unit_id).exists():
            return
        reason = self.worktrees.release(unit_id)
        path = str(self.worktrees.path(unit_id))
        if reason is None:
            self.ledger.append("worktree_released", unit_id=unit_id, path=path, branch=self.worktrees.branch(unit_id))
        else:
            self.ledger.append("worktree_kept", unit_id=unit_id, path=path, reason=reason)

    # --- step 6: resolve gates ---

    def _level(self, unit_id):
        """The level Check recorded, raised when the PR's branch now changes a path the
        risk rules flag. A PR scored before Check read the branch diff, or whose branch
        changed after, keeps its gate."""
        recorded = (read_json(self.units.unit_dir(unit_id) / "risk.json") or {}).get("level", "L0")
        pr = self.units.state(unit_id).get("pr") or {}
        if not pr.get("branch") or self._spec(unit_id).get("review_of"):
            return recorded
        if not triggers(self.worktrees.changed_paths(unit_id, pr.get("base") or self._base_for(unit_id))):
            return recorded
        return max(recorded, "L2", key=LEVELS.index)

    def resolve_gates(self):
        self._apply_answers()
        self._retire_orphan_gates()
        # A pause holds merges too, an approval given before it included: a person pauses
        # because something about the run is wrong, and a merge is the one step that
        # lands it on main. The approval stands and the merge goes on resume.
        paused = self.paused()
        for state in self.units.by_state("gated"):
            unit_id = state["unit_id"]
            if (state.get("pr") or {}).get("number") is None:
                # A session that reported a PR without opening it, gated before the host
                # could open one. Open it now, or try again next tick.
                try:
                    state = {**state, "pr": self._opened(unit_id, state.get("pr") or {})}
                except Exception as exc:
                    self.ledger.append("pr_open_failed", unit_id=unit_id, detail=str(exc)[-300:])
                    continue
                if state["pr"].get("number") is None:
                    continue
                self.units.save(state)
                self.ledger.append("pr_opened", unit_id=unit_id, pr=state["pr"]["number"])
            # Opened here rather than at Check, so a crash between the two is repaired
            # on the next tick, and a PR gated before reviews existed gets one too.
            if self._reviews() and not self._reviewed_head(state):
                # The review waits for the host's CI. Opened beside it, a red CI threw
                # away a review already paid for, and the retry bought a second one.
                if self._ci_green(unit_id, state, state["pr"]["number"]):
                    self._open_review(unit_id)
                continue
            if self._review_pending(state):
                continue
            level = self._level(unit_id)
            if level in ("L0", "L1") and self._autopilot():
                if not paused:
                    self._merge(unit_id, state, level)
            else:
                gates = self._merge_gates(unit_id)
                if not gates:
                    self._open_merge_gate(unit_id, state, level)
                elif gates[-1]["content"]["response"] and \
                        gates[-1]["content"]["response"]["option"] == "approve" and not paused:
                    self._merge(unit_id, state, level)

    def _retire_orphan_gates(self):
        """An open gate that holds only units already done or cancelled asks a question
        nobody is waiting on: a cancelled unit left its merge gate in Slack. Retired on
        the tick, so a cancel from any channel, or one before this existed, clears it."""
        for gate in self.gates.open_gates():
            holds = gate["content"]["holds"]
            if holds and all(u in self.units.ids() and self.units.state(u)["state"] in ("done", "cancelled")
                             for u in holds):
                self.gates.retire(gate, "harness", "nothing left to hold")
                self.ledger.append("gate_retired", gate_id=gate["content"]["checkpoint_id"], holds=holds)

    def _autopilot(self):
        """Only autopilot merges a low-risk PR on review alone. Under standard and
        supervised every merge waits for a person, and a brief that cannot be read gates
        too, because an unwanted merge costs more than one tap."""
        try:
            return BriefStore(self.project_path).load()[0].get("autonomy") == "autopilot"
        except Exception:  # noqa: BLE001, an unreadable brief must not merge
            return False

    def _open_merge_gate(self, unit_id, state, level):
        risk = read_json(self.units.unit_dir(unit_id) / "risk.json") or {}
        session_dir = self.sessions(unit_id).dir(state["sessions"][-1])
        response = session_dir / "return.txt"
        context = {"task": self._spec(unit_id)["expected_outcome"], "findings": risk.get("findings", []),
                   "triggers": risk.get("triggers", []),
                   "builder_response": response.read_text() if response.exists() else "",
                   "unit_id": unit_id, "design_session": False, "review": risk.get("review")}
        noun = getattr(self.source_host, "noun", "PR")
        self.gates.open("pr-merge", level, [unit_id], f"Merge {noun} {state['pr']['number']} for {unit_id}?",
                        MERGE_OPTIONS, artifact_ref=f"PR-{state['pr']['number']}", context=context)

    def _merge(self, unit_id, state, level):
        """The harness is the only merger. A stacked unit merges after what it sits on."""
        deps = self._spec(unit_id)["dependencies"]
        if any(self.units.state(d)["state"] != "done" for d in deps):
            return
        state = self.units.state(unit_id)  # a parent merged earlier in this tick may have moved it
        number = state["pr"]["number"]
        if any((self.units.state(d).get("pr") or {}).get("branch") == state["pr"].get("base") for d in deps):
            # The parent merged before this PR existed, so the retarget after that merge
            # missed it. Its base branch is merged work, never where it lands.
            state = self._retarget_to_default(unit_id, state)
        if not self._ci_green(unit_id, state, number):
            return
        try:
            sha = self.source_host.merge(self.project_slug, number)
        except Exception as exc:  # noqa: BLE001, a refused merge must not stop the tick
            self._merge_failed(unit_id, state, number, str(exc))
            return
        self.ledger.append("merge", unit_id=unit_id, pr=number, sha=sha)
        self.units.transition(unit_id, "done", f"merged at {level}", merge={"sha": sha, "at": iso(self.now())})
        self.close_stories()
        if level == "L1":
            self.gates.open("routine-decision", "L1", [], f"{unit_id} merged at L1", [
                {"option": "viewed", "consequence": "Closes this entry."}], artifact_ref=f"PR-{number}", digest=True)
        for other in self.units.by_state("gated", "checking", "running", "retry", "redispatch"):
            if other.get("pr") and other["pr"].get("base") == state["pr"]["branch"]:
                self._retarget_to_default(other["unit_id"], other)

    def _retarget_to_default(self, unit_id, state):
        base = self.worktrees.default_branch()
        if state["state"] == "gated" and getattr(self.source_host, "squashes", True):
            self._restack(unit_id, state)
        self.source_host.retarget(self.project_slug, state["pr"]["number"], base)
        state = {**state, "pr": {**state["pr"], "base": base}}
        self.units.save(state)
        return state

    def _restack(self, unit_id, state):
        """A squash merge leaves a stacked branch carrying its parent's original commits,
        which conflict with the squash. Replay only the unit's own commits onto the base.
        True when the branch moved."""
        for dep in self._spec(unit_id)["dependencies"]:
            parent = self.units.state(dep)
            if parent["state"] != "done" or not parent.get("pr"):
                continue
            problem = self.worktrees.restack(state["pr"]["branch"], parent["pr"]["branch"],
                                             self.worktrees.default_branch())
            if problem is None:
                self.ledger.append("restacked", unit_id=unit_id, pr=state["pr"]["number"], onto=dep)
                return True
            if problem not in ("nothing to restack", "a branch is missing"):
                self.ledger.append("restack_failed", unit_id=unit_id, pr=state["pr"]["number"], detail=problem)
        return False

    def _merge_failed(self, unit_id, state, number, detail):
        """A PR that conflicts with its base goes back to its builder. Any other refusal
        goes to a person. While the host has not computed mergeability yet, the merge
        is tried again on the next tick."""
        mergeable = getattr(self.source_host, "mergeable", lambda *_: "unknown")(self.project_slug, number)
        if mergeable == "unknown":
            return
        if mergeable == "conflicting" and getattr(self.source_host, "squashes", True) and self._restack(unit_id, state):
            return
        detail = detail[-300:]
        self.ledger.append("merge_failed", unit_id=unit_id, pr=number, detail=detail)
        self._retire_merge_gates(unit_id)
        base = state["pr"]["base"]
        if mergeable == "conflicting":
            # The retry merges the local default branch, so bring it up to origin first,
            # or the session resolves against the same stale base and conflicts again.
            if hasattr(self.source_host, "sync"):
                self.source_host.sync(self.project_slug)
            self._append_note(unit_id, f"PR {number} conflicts with {base} after other work merged. Merge {base} "
                                       f"into your branch, resolve every conflict keeping the intent of both sides, "
                                       f"run the tests, and commit to the same branch (push only when your output contract says to). Do not open a new PR.")
            self.units.transition(unit_id, "retry", f"defect: PR {number} conflicts with {base}",
                                  retries_spent=state["retries_spent"] + 1)
        else:
            self._block(unit_id, state, f"merging PR {number} failed: {detail}")

    def _ci_green(self, unit_id, state, number):
        """The merge waits for the project's CI signal. Receipts were verified at Check.
        Actions checks are read from the PR: pending waits, a failure sends the unit
        back as a defect, the same as a reviewer would."""
        if self._ci_signal() not in ("self-hosted-actions", "both") or not hasattr(self.source_host, "checks"):
            return True
        self._label_for_hosted_ci(unit_id, number)
        status, detail = self.source_host.checks(self.project_slug, number)
        if status == "pass":
            return True
        if status == "fail":
            log = getattr(self.source_host, "failure_log", lambda *_: "")(self.project_slug, number) or ""
            if self._rerun_infra_failure(unit_id, state, number, log):
                return False
            tail = f"\nThe failed steps end:\n{log[-3000:]}" if log else ""
            self._append_note(unit_id, f"CI failed on PR {number}: {detail}{tail}")
            self.units.transition(unit_id, "retry", f"defect: CI failed on PR {number}",
                                  retries_spent=state["retries_spent"] + 1)
            self._retire_merge_gates(unit_id)
        elif getattr(self.source_host, "mergeable", lambda *_: "unknown")(self.project_slug, number) == "conflicting":
            # The host runs no checks on a PR that conflicts with its base, so waiting
            # for them never ends. The conflict is handled as a refused merge would be.
            self._merge_failed(unit_id, state, number, f"PR {number} conflicts with its base, so its checks never ran")
        return False

    def _lane(self):
        return ((read_json(self.run_dir / "run-brief.json") or {}).get("content") or {}).get("lane") or "build"

    def _ci_signal(self):
        """The project's CI signal for this run's lane. A lane left out of
        hosted_ci_lanes proves its changes with the project's checks on this machine,
        because hosted CI minutes are kept for polish and maintenance."""
        settings = self.settings()
        signal = settings.get("ci_signal", "receipts")
        lanes = settings.get("hosted_ci_lanes")
        if lanes is not None and signal in ("self-hosted-actions", "both") and self._lane() not in lanes:
            return "receipts"
        return signal

    def _label_for_hosted_ci(self, unit_id, number):
        """When only some lanes use hosted CI, the project's workflow runs on a unit PR
        only with this label, so the harness adds it to the PRs that wait on CI. Once."""
        if self.settings().get("hosted_ci_lanes") is None or not hasattr(self.source_host, "label"):
            return
        marker = self.units.unit_dir(unit_id) / "ci-label.json"
        if (read_json(marker) or {}).get("pr") == number:
            return
        try:
            self.source_host.label(self.project_slug, number, HOSTED_CI_LABEL)
        except Exception as exc:  # noqa: BLE001, a label that fails leaves CI pending, retried next tick
            self.ledger.append("pr_label_failed", unit_id=unit_id, pr=number, detail=str(exc)[-300:])
            return
        write_json(marker, {"pr": number, "label": HOSTED_CI_LABEL})
        self.ledger.append("pr_labeled", unit_id=unit_id, pr=number, label=HOSTED_CI_LABEL)

    def _rerun_infra_failure(self, unit_id, state, number, log):
        """A runner that ran out of memory or lost its connection says nothing about the
        change. Its failed jobs run again once per PR head, with no session spent. 17 of
        20 CI failures in one run were ESLint out of heap, each a builder retry and a
        fresh review."""
        if not INFRA_FAILURE.search(log) or not hasattr(self.source_host, "rerun"):
            return False
        path = self.units.unit_dir(unit_id) / "ci-reruns.json"
        reruns = read_json(path) or []
        head = self._branch_head(state["pr"].get("branch") or "") or f"pr-{number}"
        earlier = next((r for r in reruns if r.get("head") == head), None)
        if earlier:
            # The checks can read as failed for a moment after the rerun starts.
            return self.now() - earlier["at"] < CI_RERUN_GRACE
        runs = self.source_host.rerun(self.project_slug, number)
        write_json(path, reruns + [{"head": head, "at": self.now()}])
        self.ledger.append("ci_rerun", unit_id=unit_id, pr=number, runs=list(runs or []),
                           detail=INFRA_FAILURE.search(log).group(0))
        return True

    def _apply_answers(self):
        """Carry out what each answered gate decided, once."""
        for gate in self.gates.all():
            content = gate["content"]
            response = content["response"]
            if not response or content["digest"] or content["context"].get("retired"):
                continue
            self._resolve_escalation(content)
            for unit_id in content["holds"]:
                state = self.units.state(unit_id)
                option = response["option"]
                if content["checkpoint_type"] == "pr-merge" and not content["context"].get("gate_request"):
                    if option == "send_back" and state["state"] == "gated":
                        self._send_back(unit_id, state, response)
                elif option == "cancel" and state["state"] in ("planned", "ready", "blocked"):
                    self.units.transition(unit_id, "cancelled", f"gate {content['checkpoint_id']} answered cancel",
                                          cancelled_by=response["by"])
                elif state["state"] == "blocked" and self._last_gate(unit_id) == content["checkpoint_id"]:
                    # The next session reads why the unit stopped and what the human said, and
                    # a human retry is a fresh budget: left spent, the first defect would block
                    # again before the session could act on the answer.
                    if option == UNLOCK and content["context"].get("unlock_paths"):
                        self._record_unlock(content["checkpoint_id"], content["context"]["unlock_paths"])
                    self._append_note(unit_id, self._answer_note(content, response))
                    self.units.transition(unit_id, "ready", f"gate {content['checkpoint_id']} answered {option}",
                                          retries_spent=0)

    def _resolve_escalation(self, content):
        """The blocked card's escalation closes with its gate. Left open, run-state listed
        nine escalations a day after every unit they named had merged."""
        ref = content.get("artifact_ref") or ""
        path = self.run_dir / "artifacts" / f"{ref}.json"
        if not ref.startswith("E-") or not path.exists():
            return
        artifact = read_json(path)
        if artifact["content"].get("status") != "open":
            return
        response = content["response"]
        artifact["content"]["status"] = "resolved"
        artifact["content"]["resolution_notes"] = (f"{content['checkpoint_id']} answered {response['option']}"
                                                   + (f": {response['free_text']}" if response.get("free_text") else ""))[:1000]
        write_json(path, artifact)

    def _record_unlock(self, gate_id, entries):
        """Add the approved paths to the project's rulings. The unit's worktree gets a
        copy when it is claimed for the next session."""
        path = self.project_path / RULINGS
        rulings = read_json(path) or {}
        kept = [e for e in rulings.get("paths", []) if isinstance(e, dict)]
        named = {e["path"] for e in entries}
        kept = [e for e in kept if e.get("path") not in named]
        kept += [{"path": e["path"], "reason": f"{e['reason']} Ruled by the human at {gate_id}."} for e in entries]
        write_json(path, {**rulings, "paths": kept})
        self.ledger.append("config_unlocked", gate_id=gate_id, paths=sorted(named))

    def _answer_note(self, content, response):
        """What the next session's brief says about the gate this unit asked for."""
        answered = [d for d in content.get("decisions", []) if d.get("response")]
        if not answered:
            parts = [f"The human answered: {content['decision_prompt']} Answer: {response['option']}."]
        else:
            # The option is a bundle the requesting agent wrote, and it can disagree with
            # the answers. Put first, it once overrode a person's answers in a brief.
            parts = [f"The human answered gate {content['checkpoint_id']} decision by decision. Follow each "
                     f"decision's answer. The option they also picked (\"{response['option']}\") is a summary "
                     "only, and where it differs from a decision's answer, the decision's answer wins."]
            parts += [f"Decision {d['decision_id']}: {d['prompt']} Answer: {d['response']}" for d in answered]
        if response.get("free_text"):
            parts.append(f"Notes: {response['free_text']}")
        return "\n".join(parts)

    def _last_gate(self, unit_id):
        gates = self.gates.holding(unit_id)
        return gates[-1]["content"]["checkpoint_id"] if gates else None

    def _send_back(self, unit_id, state, response):
        if response.get("free_text"):
            self._append_note(unit_id, f"Reviewer note: {response['free_text']}")
        self.units.transition(unit_id, "retry", "human sent the merge back", retries_spent=state["retries_spent"] + 1)
        self._retire_merge_gates(unit_id)

    def _merge_gates(self, unit_id):
        """The merge gates the harness opened for this unit. A session may ask its own
        question under the same type, and that one is answered like any other request:
        read as a merge gate, its answer released nothing and the unit stayed blocked."""
        return [g for g in self.gates.holding(unit_id, "pr-merge") if not g["content"]["context"].get("gate_request")]

    def _retire_merge_gates(self, unit_id):
        """A sent-back unit opens a fresh merge gate when it next returns."""
        for gate in self._merge_gates(unit_id):
            gate["content"]["context"]["retired"] = True
            write_json(self.gates.path(gate["content"]["checkpoint_id"]), gate)

    def close_cycles(self):
        for cycle in self.cycles.all():
            content = cycle["content"]
            if content.get("closed"):
                continue
            unit_ids = [i["unit_id"] for i in content["plan"]["routed_batch"]]
            states = [self.units.state(u) for u in unit_ids]
            if all(is_terminal(s) for s in states):
                self.cycles.close(content["cycle_id"], {s["unit_id"]: s["state"] for s in states})

    # --- step 7: derive the ready queue ---

    def _deps_ready(self, unit_id):
        """True to go, False to wait, None when a dependency can never be satisfied."""
        for dep in self._spec(unit_id)["dependencies"]:
            state = self.units.state(dep)
            if state["state"] == "cancelled" or (state["state"] == "blocked" and is_terminal(state)):
                return None
            if state["state"] != "done" and not (state["state"] == "gated" and state.get("pr")):
                return False
        return True

    def _busy_paths(self):
        return [self._spec(s["unit_id"])["declared_paths"] for s in self.units.by_state("running", "ready")]

    def derive_ready(self):
        for state in self.units.by_state("planned", "retry", "redispatch"):
            unit_id = state["unit_id"]
            spec = self._spec(unit_id)
            if spec["risk_baseline"] == "L3" and state["state"] == "planned" and not self.gates.holding(unit_id):
                self.gates.open("provisioning-required", "L3", [unit_id],
                                f"{unit_id} needs a decision or an input before it starts.", START_OPTIONS)
            if self.gates.held_at_start(unit_id):
                continue
            verdict = self._deps_ready(unit_id)
            if verdict is None:
                self._block(unit_id, state, "a dependency was cancelled or exhausted its retries")
                continue
            if verdict is False:
                continue
            if any(overlaps(spec["declared_paths"], paths) for paths in self._busy_paths()):
                continue
            self.units.transition(unit_id, "ready", "dependencies, WIP, and paths clear")

    # --- step 8: Plan ---

    def plan(self):
        states = self.open_units()
        in_flight = sum(1 for s in states if s["state"] == "running")
        ready = sum(1 for s in states if s["state"] == "ready")
        room = self.window.read()["dispatch_rate"] - self.in_flight_total()
        if ready or room <= 0:
            return
        moving = ("planned", "ready", "running", "returned", "checking", "retry", "redispatch")
        snapshot = Snapshot(in_flight=in_flight, nonterminal=sum(1 for s in states if not is_terminal(s)),
                            open_gates=sum(1 for g in self.gates.open_gates() if not g["content"]["digest"]),
                            active=sum(1 for s in states if s["state"] in moving
                                       and not self.gates.held_at_start(s["unit_id"])))
        batch = self.planner.next_batch(snapshot)
        if batch is not None:
            self._write_batch(batch)

    def _write_batch(self, batch):
        cycle_id = self.cycles.next_id()
        routed = []
        new_keys = {}
        for draft in batch.units:
            unit_id = next_id("U", self.units.folders() + list(new_keys.values()))
            new_keys[draft.key] = unit_id
            self.keys[draft.key] = unit_id
            spec = {"unit_id": unit_id, "cycle_id": cycle_id, "agent": draft.agent,
                    "role_prompt_ref": f".claude/agents/{draft.agent}.md", "model_tier": draft.model_tier,
                    "brief": draft.brief, "input_artifact_refs": [], "expected_outcome": draft.expected_outcome,
                    "workstream": draft.workstream, "declared_paths": list(draft.declared_paths), "allowlist": [],
                    "mcp_config_ref": None, "budget": {"tokens": 200000, "wall_clock_seconds": draft.wall_clock_seconds},
                    "risk_baseline": draft.risk_baseline, "risk_reason": draft.risk_reason,
                    "dependencies": [self.keys[k] for k in draft.depends_on],
                    "executable_check": draft.executable_check,
                    "gating_commands": [dict(g) for g in draft.gating_commands],
                    "story_ids": list(draft.story_ids)}
            self.units.create(spec)
            routed.append({"agent": draft.agent, "unit_id": unit_id, "expected_outcome": draft.expected_outcome,
                           "workstream": draft.workstream, "input_artifact_refs": []})
        write_json(self._keys_path(), self.keys)
        self.cycles.plan(cycle_id, batch.phase, routed, batch.rationale, batch.next_phase)
        for draft in batch.gates:
            self.gates.open(draft.checkpoint_type, draft.level, [self.keys[k] for k in draft.holds], draft.prompt,
                            [dict(o) for o in draft.options] or START_OPTIONS,
                            artifact_ref=draft.artifact_ref, decisions=[dict(d) for d in draft.decisions] or None,
                            context={"design_session": draft.checkpoint_type in ("direction-review", "taste-review",
                                                                                 "structure-confirmation")})

    # --- step 9: dispatch ---

    def dispatch(self):
        room = self.window.read()["dispatch_rate"] - self.in_flight_total()
        for state in self.units.by_state("ready"):
            if room <= 0:
                return
            if self.gates.held_at_start(state["unit_id"]):
                continue
            self._claim(state)
            room -= 1

    def _claim(self, state):
        unit_id = state["unit_id"]
        if getattr(self.provider, "mechanical", False) and not getattr(self, "_venv_ready", False):
            problem = self.worktrees.ensure_venv()
            if problem:
                self.ledger.append("environment_degraded", detail=f"no venv for schemas/validate.py: {problem}")
            self._venv_ready = problem is None
        path, branch = self.worktrees.claim(unit_id, self._base_for(unit_id))
        self.ledger.append("worktree_claimed", unit_id=unit_id, path=str(path), branch=branch)
        self.units.transition(unit_id, "running", "claimed")
        self._spawn(unit_id, self.units.state(unit_id))

    def _gating(self, unit_id, result=None):
        """The plan's gating commands for the unit, then the project's checks, which run on
        every unit that changes code (lint and typecheck, say), whatever the plan named.
        A review unit writes no code and gets none, and neither does a unit whose result
        shows it lands nothing of its own, such as an audit stacked on an open change."""
        spec = self._spec(unit_id)
        planned = [dict(g) for g in spec.get("gating_commands") or []]
        if spec.get("review_of") or (result is not None and self._lands_nothing(unit_id, result)):
            return planned
        named = {g["command"].strip() for g in planned}
        checks = [{"name": f"project-check-{i}", "command": command, "kind": "check"}
                  for i, command in enumerate(self.settings().get("project_checks") or [], 1)
                  if command.strip() not in named]
        return planned + checks

    def _baseline(self, unit_id):
        """What fails_at says for a gating command on the unit's base, kept per base
        commit so a retry or a sibling unit does not run a slow check twice. None when
        the base cannot be resolved, and then a failure is the unit's, as before."""
        done = subprocess.run(["git", "-C", str(self.project_path), "rev-parse", "--verify", "--quiet",
                               f"{self._base_for(unit_id)}^{{commit}}"], capture_output=True, text=True)
        sha = done.stdout.strip()
        if done.returncode or not sha:
            return None
        cache = self.worktrees.root / "_base" / f"{sha}.json"
        worktrees, own = self.worktrees, self.worktrees.path(unit_id)

        def at_base(command):
            known = read_json(cache)
            known = known if isinstance(known, dict) else {}
            key = command["command"]
            if key not in known:
                path = worktrees.scratch_at(sha, also=(own,))
                if path is None:
                    return None
                try:
                    said = fails_at(command, cache.parent / sha / command["name"], path)
                finally:
                    worktrees.drop_scratch(path)
                if said is not None and cannot_run(None, said):
                    return said  # the base tree lacked something, which the next look may have
                known[key] = said
                write_json(cache, known)
            return known[key]
        return at_base

    def _lands_nothing(self, unit_id, result):
        """True for a unit that is not a pull request and has no commits past its base."""
        return result.outcome != "pr" and self.worktrees.path(unit_id).exists() \
            and not self.worktrees.own_commits(unit_id, self._base_for(unit_id))

    PRODUCT_RECORDED = ".product-recorded"

    def _record_product_checks(self, unit_id, gating, session_dir):
        """One product_check line per product command the gating run reached, so the
        outcome figure counts the checks the harness runs, not only product-check.py.
        A command after the first failure never ran and has no line. Once per run."""
        check = Path(session_dir) / "check"
        marker = check / self.PRODUCT_RECORDED
        if marker.exists():
            return
        for command in gating:
            if command.get("kind") != "product":
                continue
            receipt = read_json(check / "receipts" / f"{command['name']}.json")
            if not isinstance(receipt, dict):
                continue
            self.ledger.append("product_check", unit_id=unit_id, cycle_id=self._spec(unit_id).get("cycle_id"),
                               check_id=command["name"], result="pass" if receipt.get("result") == "pass" else "fail",
                               duration_s=receipt.get("duration_s"), source="gating")
        if check.is_dir():
            marker.write_text("")

    def _spawn(self, unit_id, state, handoff_from=None):
        spec = self._spec(unit_id)
        store = self.sessions(unit_id)
        tier = self._tier(unit_id, state)
        session_id = next_id("S", store.ids())
        brief = spec["brief"] + gating_note(self._gating(unit_id)) + \
            criteria_note(self.project_path, spec.get("story_ids") or ())
        notes = self._notes(unit_id)
        if notes:
            brief += "\n\n" + notes
        handoff = self._previous_handoff(unit_id, handoff_from)
        if handoff:
            brief += "\n\nContinue from this handoff:\n" + handoff
        request = SpawnRequest(unit_id=unit_id, session_id=session_id, agent=spec["agent"],
                               role_prompt_ref=spec["role_prompt_ref"], model_tier=tier, brief=brief,
                               allowlist=tuple(spec["allowlist"]), mcp_config_ref=spec["mcp_config_ref"],
                               cwd=self.worktrees.path(unit_id), session_dir=store.dir(session_id),
                               env={"SPRINGER_PROJECT_DIR": str(self.project_path), "SPRINGER_RUN_ID": self.run_id,
                                    "SPRINGER_SESSION_DIR": str(store.dir(session_id)),
                                    "SPRINGER_BRANCH": self.worktrees.branch(unit_id), "SPRINGER_BASE": self._base_for(unit_id),
                                    "SPRINGER_SOURCE_HOST": getattr(self.source_host, "name", "github")})
        handle = self.provider.spawn(request)
        self.handles[(unit_id, session_id)] = handle
        store.create(self.provider.name, handle.model, tier, handle.pid, handle.provider_session_id, session_id)
        self.units.save({**state, "sessions": state["sessions"] + [session_id]})
        self.ledger.append("session_started", unit_id=unit_id, session_id=session_id, provider=self.provider.name,
                           pid=handle.pid, model=handle.model, tier=tier)

    def _previous_handoff(self, unit_id, explicit=None):
        """The newest handoff the unit's sessions left, so a redispatch carries it."""
        store = self.sessions(unit_id)
        for session_id in ([explicit] if explicit else reversed(store.ids())):
            path = store.dir(session_id) / "handoff.md"
            if path.exists():
                return path.read_text()
        return None

    # --- finishing ---

    def finish_if_done(self):
        states = self.open_units()
        open_gates = [g for g in self.gates.open_gates() if not g["content"]["digest"]]
        if not states and not open_gates and not self.cycles.ids() and self.planner.finished():
            # The first plan found nothing to route. With no unit and no cycle there was
            # nothing to finish, so the run sat silent and held the project.
            self._complete_with_no_work()
            return
        if states and self.planner.finished() and not open_gates and all(is_terminal(s) for s in states) \
                and all(c["content"].get("closed") for c in self.cycles.all()):
            self.close_stories()
            if self._held_for_release():
                return
            self.cycles.complete_run()

    def ask_when_idle(self):
        """A plan that routes nothing and is not done leaves the run with nothing moving
        and nobody asked. One gate puts the planner's reasons in front of the person, and
        the answer changes the run state, so the planner is asked again and reads it."""
        plan = getattr(self.planner, "idle", lambda: None)()
        if not plan or not self.units.ids():
            return
        # A gated unit no open gate holds is a PR waiting on CI, its review, or a restack,
        # and merges on its own. One a person holds is caught by the open-gate test below.
        moving = ("planned", "ready", "running", "returned", "checking", "retry", "redispatch", "gated")
        if any(s["state"] in moving for s in self.open_units()):
            return
        gates = self.gates.all()
        if any(g["content"]["response"] is None and not g["content"]["digest"] for g in gates):
            return
        if any(g["content"]["context"].get("idle_plan") == plan for g in gates):
            return
        latest = getattr(self.planner, "latest_rationale", lambda: None)() or "The plan gave no reason."
        gate = self.gates.open(
            "scope-review", "L3", [], f"The plan routed nothing and the run is not done. {latest}"[:3000],
            [{"option": "plan again", "consequence": "The planner is asked again and reads your note.",
              "recommended_because": "Name what it missed, or what you have unblocked, in the note."},
             {"option": "leave idle", "consequence": "The run waits until something else changes."}],
            context={"idle_plan": plan})
        self.ledger.append("plan_idle", gate_id=gate["content"]["checkpoint_id"], plan=plan)

    def _complete_with_no_work(self):
        latest = getattr(self.planner, "latest_rationale", lambda: None)()
        why = f"The plan found nothing to route: {latest}" if latest else "The plan found nothing to route."
        cycle_id = self.cycles.next_id()
        no_work = {"agent": "spgr-agent-orchestrator", "expected_outcome": "no work, the plan found nothing to route"}
        self.cycles.plan(cycle_id, "complete", [no_work], why)
        self.cycles.close(cycle_id, {})
        self.cycles.complete_run()
        self.ledger.append("run_completed_with_no_work", detail=why[:600])

    def close_stories(self):
        """Close the backlog stories whose units in this run are all done. The board's read
        once did this alone, so a run driven only from Slack left its stories open."""
        try:
            BacklogStore(self.project_path).view(self.units, self.ledger.head(), self.run_id, now=iso(self.now()))
        except Exception as exc:  # noqa: BLE001, the backlog must never stop a merge or a run's end
            self.ledger.append("backlog_close_failed", detail=f"{type(exc).__name__}: {exc}"[:300])

    # --- cleaning up ---

    def clean_up(self):
        """After the run: every unit's worktree released, and the branch of every unit
        that merged deleted here and on origin. A stacked child replays its own commits
        off its parent's branch, so branches go only once nothing is left to merge. A
        cancelled unit's branch is its unmerged work and stays. Safe to repeat."""
        released, kept, deleted, unlanded = [], [], [], []
        integrated = {e.line.get("unit_id") for e in self.ledger.read() if e.line.get("event") == "artifact_integrated"}
        for unit_id in self.units.ids():
            state = self.units.state(unit_id)
            if self.worktrees.path(unit_id).exists():
                reason = self.worktrees.release(unit_id)
                (kept if reason else released).append(unit_id)
            branch = (state.get("pr") or {}).get("branch") or self.worktrees.branch(unit_id)
            if state["state"] != "done":
                continue
            if self._landed(unit_id, state, branch, integrated):
                deleted += self.worktrees.delete_branch(branch)
            else:
                unlanded.append(branch)
        if released or kept or deleted or unlanded:
            self.ledger.append("cleaned_up", released=released, kept=kept, branches=deleted, unlanded=unlanded)
        return {"released": released, "kept": kept, "branches": deleted, "unlanded": unlanded}

    def _landed(self, unit_id, state, branch, integrated):
        """A done unit's branch goes only once its work is on the default branch. A PR
        unit is done only when its PR merged (a squash, so its commits are not ancestors).
        An artifact unit landed when it was integrated, or when its branch is already in
        the default branch. Otherwise the branch is the only copy of the work and stays."""
        if (state.get("pr") or {}).get("number") is not None or unit_id in integrated:
            return True
        def git(*args):
            return subprocess.run(["git", "-C", str(self.project_path), *args], capture_output=True).returncode == 0
        ref = next((r for r in (branch, f"origin/{branch}") if git("rev-parse", "--verify", "--quiet", r)), None)
        return ref is None or git("merge-base", "--is-ancestor", ref, self.worktrees.default_branch())

    # --- the production release ---

    RELEASE_OPTIONS = [
        {"option": "go", "consequence": "Runs the project's deploy command at the merged head and reports the "
                                        "result in the run thread. The run completes after it.",
         "recommended_because": "Every merge in this run passed Check, review, and your merge gate."},
        {"option": "no_go", "consequence": "Ships nothing. The run completes, and /springer release deploys later."},
    ]

    def _held_for_release(self):
        """True while the release gate or the deploy it started holds the run open. A run
        opens the gate when the project has a release command and the run merged work."""
        command = self.settings().get("release_command")
        if not command or self.release is None:
            return False
        # Only the gate the harness opened, which carries the command. A production-release
        # gate from an older plan answers in its own words and is not the release.
        gates = [g for g in self.gates.all() if g["content"]["checkpoint_type"] == "production-release"
                 and (g["content"].get("context") or {}).get("command")]
        if not gates:
            merged = sum(1 for e in self.ledger.read() if e.line.get("event") == "merge")
            if not merged:
                return False
            _, sha = _git_out(self.project_path, "rev-parse", "--short", "HEAD")
            self.gates.open("production-release", "L3", [], f"Deploy {sha or 'the merged head'} to production? "
                            f"{merged} change{'s' if merged != 1 else ''} merged in {self.run_id}. The command is: "
                            f"{command}", self.RELEASE_OPTIONS, context={"command": command, "sha": sha})
            return True
        content = gates[-1]["content"]
        response = content["response"]
        if response is None:
            return True
        if response["option"] != "go":
            if not any(e.line.get("event") == "release_declined" for e in self.ledger.read()):
                self.ledger.append("release_declined", gate_id=content["checkpoint_id"], by=response["by"])
            return False
        marker = self.run_dir / "release" / f"{content['checkpoint_id']}.json"
        started = read_json(marker)
        if started is None:
            out_dir, why_not = self.release(response["by"], content["checkpoint_id"])
            write_json(marker, {"out_dir": str(out_dir) if out_dir else None, "error": why_not})
            if why_not:
                self.ledger.append("release_failed", sha=None, by=response["by"], exit_code=None, detail=why_not)
            return out_dir is not None
        if not started.get("out_dir"):
            return False
        return not (Path(started["out_dir"]) / "result.json").exists()

    # --- interventions ---

    def cancel_unit(self, unit_id, by):
        state = self.units.state(unit_id)
        if state["state"] == "running":
            self._kill_session(unit_id, state)
        self.units.transition(unit_id, "cancelled", f"cancelled by {by}", cancelled_by=by)
        self._release(unit_id)

    def cancel_run(self, by):
        """Stop everything and end the run, so a new one can start. An open PR is left
        open for the human, because closing it is a decision about the code."""
        for state in self.open_units():
            if state["state"] not in ("done", "cancelled"):
                self.cancel_unit(state["unit_id"], by)
        self.gates.close_for_cancelled_run(by)
        self.close_cycles()
        cycle_id = self.cycles.next_id()
        no_work = {"agent": "spgr-agent-orchestrator", "expected_outcome": "no further work, the run was cancelled"}
        self.cycles.plan(cycle_id, "cancelled", [no_work], f"Cancelled by {by}.")
        self.cycles.close(cycle_id, {})
        self.cycles.complete_run()
        self.project()

    def redispatch_unit(self, unit_id):
        state = self.units.state(unit_id)
        if state["state"] == "running":
            self._kill_session(unit_id, state)
        if state["state"] == "abandoned" or state["state"] in ("running", "retry", "blocked"):
            self.units.transition(unit_id, "redispatch", "a human re-dispatched it")
        elif state["state"] != "redispatch":
            raise IllegalTransition(f"{unit_id} cannot be re-dispatched from {state['state']}")

    def _kill_session(self, unit_id, state):
        session_id = state["sessions"][-1]
        handle = self.handles.get((unit_id, session_id))
        if handle:
            handle.kill()
        store = self.sessions(unit_id)
        self._end_session(unit_id, store, store.get(session_id), "killed", "killed", None)

    # --- crash recovery ---

    def _stop_orphan(self, record):
        """A real session runs in its own process group and outlives a daemon that
        stopped. Left alone it would keep writing the worktree its redispatch reuses."""
        if not getattr(self.provider, "mechanical", False) or not record.get("pid"):
            return
        try:
            os.killpg(record["pid"], signal.SIGTERM)
            self.ledger.append("session_orphan_stopped", unit_id=record.get("unit_id"),
                               session_id=record["session_id"], pid=record["pid"])
        except (ProcessLookupError, PermissionError):
            pass

    def recover(self):
        """Run at daemon start, and asks no human. Everything it decides is an event."""
        self.units.repair_from_ledger()
        if self.lock.externally_held():
            self.project()
            return "held"
        self.lock.refresh()
        for state in self.units.by_state("running"):
            unit_id = state["unit_id"]
            store = self.sessions(unit_id)
            record = store.get(state["sessions"][-1]) if state["sessions"] else None
            if record is not None and record["state"] not in ("exited", "handoff", "killed", "dead"):
                self._stop_orphan(record)
                self._mark_dead(unit_id, store, record)
            elif record is not None and record["state"] == "exited":
                continue  # join on the next tick reads what it left
            else:
                self.units.transition(unit_id, "abandoned", "no live session at recovery")
                self.units.transition(unit_id, "redispatch", "abandoned, no retry spent")
        for state in self.units.by_state("gated"):
            unit_id = state["unit_id"]
            number = (state.get("pr") or {}).get("number")
            if number is None:
                continue  # never opened, so resolve_gates opens it on the next tick
            pr_state = self.source_host.pr_state(self.project_slug, number)
            if pr_state == "merged":
                self.units.transition(unit_id, "done", "merged while the daemon was down")
            elif pr_state == "closed":
                self._block(unit_id, state, "the PR was closed unmerged")
        # A returned or checking unit's worktree is still read by its Check and its
        # integration, so a restart mid-check keeps it.
        keep = {s["unit_id"] for s in self.units.by_state("running", "retry", "redispatch", "ready", "returned", "checking")}
        for unit_id in self.worktrees.claimed():
            if unit_id not in keep:
                self._release(unit_id)
        self.project()
        return "recovered"

