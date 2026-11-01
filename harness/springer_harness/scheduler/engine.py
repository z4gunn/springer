"""One run's scheduler: the ten-step tick from the state model, and crash recovery.

Every step is idempotent against the files on disk, so a tick interrupted anywhere
is safe to run again. The engine keeps nothing durable in memory. Session handles are
the only in-memory state, and losing them is what a crash is.
"""

from pathlib import Path

from ..check.risk import triggers
from ..check.verdict import ADDENDA, BLOCK, POLICY, REDISPATCH, RETRY, read_result, risk_for
from ..common import artifact_header, iso, next_id, parse_iso, read_json, write_json
from ..errors import IllegalTransition, RunExternallyHeld
from ..providers.coding_agent import SpawnRequest
from ..state.cycles import CycleStore
from ..state.gates import GateStore
from ..state.ledger import Ledger
from ..state.lock import RunLock
from ..state.projection import is_paused, rebuild
from ..state.sessions import SessionStore
from ..state.units import MAX_RETRIES, TIERS, UnitStore, is_terminal
from .plan import Snapshot

MERGE_OPTIONS = [
    {"option": "approve", "consequence": "The PR merges and work stacked on it can merge after.",
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


class RunEngine:
    def __init__(self, project_slug, project_path, run_id, provider, planner, source_host, worktrees, window, owner,
                 now, in_flight_total=None):
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

    def _notes(self, unit_id):
        path = self.units.unit_dir(unit_id) / "redispatch-notes.txt"
        return path.read_text() if path.exists() else ""

    def _tier(self, unit_id, state):
        """The spec's tier, one up on the second retry, or the tier a human raised to."""
        spec_tier = self._spec(unit_id)["model_tier"]
        index = TIERS.index(spec_tier)
        if state["retries_spent"] >= 2:
            index = min(index + 1, len(TIERS) - 1)
        for entry in self.ledger.read():
            line = entry.line
            if line.get("event") == "operation_applied" and line.get("type") == "unit.redispatch" \
                    and line["args"].get("unit_id") == unit_id and line["args"].get("model_tier"):
                index = max(index, TIERS.index(line["args"]["model_tier"]))
        return TIERS[index]

    def _base_for(self, unit_id):
        """Main, or the open PR branch of a dependency for a stacked unit."""
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
        result = read_result(session_dir)
        if result.status != "pass":
            self._on_failure(unit_id, state, result)
            return
        level = risk_for(result, self._spec(unit_id)["risk_baseline"])
        write_json(self.units.unit_dir(unit_id) / "risk.json",
                   {"level": level, "triggers": triggers(result.touched_paths), "findings": list(result.findings)})
        if result.outcome == "pr" and result.pr:
            self.units.transition(unit_id, "gated", f"PR open, risk {level}", pr=result.pr)
        else:
            self.units.transition(unit_id, "done", "artifact confirmed")
        self._release(unit_id)

    def _on_failure(self, unit_id, state, result):
        cause = result.failure_class or "defect"
        action = POLICY.get(cause, RETRY)
        if cause in ADDENDA:
            self._append_note(unit_id, ADDENDA[cause])
        if action == REDISPATCH:
            self.units.transition(unit_id, "redispatch", f"{cause}: {result.detail}")
        elif action == BLOCK:
            self._block(unit_id, state, f"blocked: {result.detail}")
        elif state["retries_spent"] >= MAX_RETRIES:
            self._block(unit_id, {**state, "retries_spent": state["retries_spent"] + 1},
                        f"retries exhausted: {result.detail}", retries_spent=state["retries_spent"] + 1)
        else:
            self.units.transition(unit_id, "retry", f"defect: {result.detail}",
                                  retries_spent=state["retries_spent"] + 1)

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
            self.ledger.append("worktree_released", unit_id=unit_id, path=path, branch=f"unit/{unit_id}")
        else:
            self.ledger.append("worktree_kept", unit_id=unit_id, path=path, reason=reason)

    # --- step 6: resolve gates ---

    def _level(self, unit_id):
        return (read_json(self.units.unit_dir(unit_id) / "risk.json") or {}).get("level", "L0")

    def resolve_gates(self):
        self._apply_answers()
        for state in self.units.by_state("gated"):
            unit_id = state["unit_id"]
            level = self._level(unit_id)
            if level in ("L0", "L1"):
                self._merge(unit_id, state, level)
            else:
                gates = self.gates.holding(unit_id, "pr-merge")
                if not gates:
                    self._open_merge_gate(unit_id, state, level)
                elif gates[-1]["content"]["response"] and \
                        gates[-1]["content"]["response"]["option"] == "approve":
                    self._merge(unit_id, state, level)

    def _open_merge_gate(self, unit_id, state, level):
        risk = read_json(self.units.unit_dir(unit_id) / "risk.json") or {}
        session_dir = self.sessions(unit_id).dir(state["sessions"][-1])
        response = session_dir / "return.txt"
        context = {"task": self._spec(unit_id)["expected_outcome"], "findings": risk.get("findings", []),
                   "triggers": risk.get("triggers", []),
                   "builder_response": response.read_text() if response.exists() else "",
                   "unit_id": unit_id, "design_session": False}
        self.gates.open("pr-merge", level, [unit_id], f"Merge PR {state['pr']['number']} for {unit_id}?",
                        MERGE_OPTIONS, artifact_ref=f"PR-{state['pr']['number']}", context=context)

    def _merge(self, unit_id, state, level):
        """The harness is the only merger. A stacked unit merges after what it sits on."""
        deps = self._spec(unit_id)["dependencies"]
        if any(self.units.state(d)["state"] != "done" for d in deps):
            return
        number = state["pr"]["number"]
        sha = self.source_host.merge(self.project_slug, number)
        self.ledger.append("merge", unit_id=unit_id, pr=number, sha=sha)
        self.units.transition(unit_id, "done", f"merged at {level}", merge={"sha": sha, "at": iso(self.now())})
        if level == "L1":
            self.gates.open("routine-decision", "L1", [], f"{unit_id} merged at L1", [
                {"option": "viewed", "consequence": "Closes this entry."}], artifact_ref=f"PR-{number}", digest=True)
        for other in self.units.by_state("gated", "checking", "running", "retry", "redispatch"):
            if other.get("pr") and other["pr"].get("base") == state["pr"]["branch"]:
                base = self.worktrees.default_branch()
                self.source_host.retarget(self.project_slug, other["pr"]["number"], base)
                self.units.save({**other, "pr": {**other["pr"], "base": base}})

    def _apply_answers(self):
        """Carry out what each answered gate decided, once."""
        for gate in self.gates.all():
            content = gate["content"]
            response = content["response"]
            if not response or content["digest"] or content["context"].get("retired"):
                continue
            for unit_id in content["holds"]:
                state = self.units.state(unit_id)
                option = response["option"]
                if content["checkpoint_type"] == "pr-merge":
                    if option == "send_back" and state["state"] == "gated":
                        self._send_back(unit_id, state, response)
                elif option == "cancel" and state["state"] in ("planned", "ready", "blocked"):
                    self.units.transition(unit_id, "cancelled", f"gate {content['checkpoint_id']} answered cancel",
                                          cancelled_by=response["by"])
                elif state["state"] == "blocked" and self._last_gate(unit_id) == content["checkpoint_id"]:
                    self.units.transition(unit_id, "ready", f"gate {content['checkpoint_id']} answered {option}")

    def _last_gate(self, unit_id):
        gates = self.gates.holding(unit_id)
        return gates[-1]["content"]["checkpoint_id"] if gates else None

    def _send_back(self, unit_id, state, response):
        if response.get("free_text"):
            self._append_note(unit_id, f"Reviewer note: {response['free_text']}")
        self.units.transition(unit_id, "retry", "human sent the merge back", retries_spent=state["retries_spent"] + 1)
        self._retire_merge_gates(unit_id)

    def _retire_merge_gates(self, unit_id):
        """A sent-back unit opens a fresh merge gate when it next returns."""
        for gate in self.gates.holding(unit_id, "pr-merge"):
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
        snapshot = Snapshot(in_flight=in_flight, nonterminal=sum(1 for s in states if not is_terminal(s)),
                            open_gates=sum(1 for g in self.gates.open_gates() if not g["content"]["digest"]))
        batch = self.planner.next_batch(snapshot)
        if batch is not None:
            self._write_batch(batch)

    def _write_batch(self, batch):
        cycle_id = self.cycles.next_id()
        routed = []
        new_keys = {}
        for draft in batch.units:
            unit_id = next_id("U", self.units.ids() + list(new_keys.values()))
            new_keys[draft.key] = unit_id
            self.keys[draft.key] = unit_id
            spec = {"unit_id": unit_id, "cycle_id": cycle_id, "agent": draft.agent,
                    "role_prompt_ref": f".claude/agents/{draft.agent}.md", "model_tier": draft.model_tier,
                    "brief": draft.brief, "input_artifact_refs": [], "expected_outcome": draft.expected_outcome,
                    "workstream": draft.workstream, "declared_paths": list(draft.declared_paths), "allowlist": [],
                    "mcp_config_ref": None, "budget": {"tokens": 200000, "wall_clock_seconds": draft.wall_clock_seconds},
                    "risk_baseline": draft.risk_baseline, "dependencies": [self.keys[k] for k in draft.depends_on],
                    "executable_check": draft.executable_check}
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
        path, branch = self.worktrees.claim(unit_id, self._base_for(unit_id))
        self.ledger.append("worktree_claimed", unit_id=unit_id, path=str(path), branch=branch)
        self.units.transition(unit_id, "running", "claimed")
        self._spawn(unit_id, self.units.state(unit_id))

    def _spawn(self, unit_id, state, handoff_from=None):
        spec = self._spec(unit_id)
        store = self.sessions(unit_id)
        tier = self._tier(unit_id, state)
        session_id = next_id("S", store.ids())
        brief = spec["brief"]
        notes = self._notes(unit_id)
        if notes:
            brief += "\n\n" + notes
        handoff = self._previous_handoff(unit_id, handoff_from)
        if handoff:
            brief += "\n\nContinue from this handoff:\n" + handoff
        request = SpawnRequest(unit_id=unit_id, session_id=session_id, agent=spec["agent"],
                               role_prompt_ref=spec["role_prompt_ref"], model_tier=tier, brief=brief,
                               allowlist=tuple(spec["allowlist"]), mcp_config_ref=spec["mcp_config_ref"],
                               cwd=self.worktrees.path(unit_id), session_dir=store.dir(session_id))
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
        if states and self.planner.finished() and not open_gates and all(is_terminal(s) for s in states) \
                and all(c["content"].get("closed") for c in self.cycles.all()):
            self.cycles.complete_run()

    # --- interventions ---

    def cancel_unit(self, unit_id, by):
        state = self.units.state(unit_id)
        if state["state"] == "running":
            self._kill_session(unit_id, state)
        self.units.transition(unit_id, "cancelled", f"cancelled by {by}", cancelled_by=by)
        self._release(unit_id)

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
                self._mark_dead(unit_id, store, record)
            elif record is not None and record["state"] == "exited":
                continue  # join on the next tick reads what it left
            else:
                self.units.transition(unit_id, "abandoned", "no live session at recovery")
                self.units.transition(unit_id, "redispatch", "abandoned, no retry spent")
        for state in self.units.by_state("gated"):
            unit_id = state["unit_id"]
            pr_state = self.source_host.pr_state(self.project_slug, state["pr"]["number"])
            if pr_state == "merged":
                self.units.transition(unit_id, "done", "merged while the daemon was down")
            elif pr_state == "closed":
                self._block(unit_id, state, "the PR was closed unmerged")
        keep = {s["unit_id"] for s in self.units.by_state("running", "retry", "redispatch", "ready")}
        for unit_id in self.worktrees.claimed():
            if unit_id not in keep:
                self._release(unit_id)
        self.project()
        return "recovered"

