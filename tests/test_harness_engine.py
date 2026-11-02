"""The scheduler against the mock provider. Covers the list in the state model's
Validation section: every unit transition, overlapping cycles with a disjointness
conflict, a handoff, a dead session, a restart with units in each state, a parked
window, and a stale lock takeover, plus one canned run from plan to complete."""

import json
import shutil
import unittest

from harness_support import HAVE_JSONSCHEMA, OWNER, EngineCase, registry, schema_errors

from springer_harness.check.risk import level_for
from springer_harness.common import iso
from springer_harness.errors import IllegalTransition
from springer_harness.providers.mock import Attempt, MockProvider, fail_result, pr_result
from springer_harness.scheduler.engine import overlaps
from springer_harness.scheduler.plan import GateDraft, PlanBatch, UnitDraft
from springer_harness.state.units import TRANSITIONS, is_terminal


def batch(*units, gates=(), phase="development", barrier=True):
    return PlanBatch(phase=phase, rationale="test", units=list(units), gates=list(gates), barrier=barrier)


def unit(key, agent="spgr-agent-backend-developer", **fields):
    return UnitDraft(key=key, agent=agent, **fields)


class TransitionTest(EngineCase):
    def test_every_edge_is_allowed_and_every_other_is_refused(self):
        engine = self.engine()
        counter = 0
        for start, targets in TRANSITIONS.items():
            for to in TRANSITIONS:
                counter += 1
                unit_id = f"U-{counter:04d}"
                engine.units.create({"unit_id": unit_id, "budget": {"wall_clock_seconds": 1}})
                engine.units.save({**engine.units.state(unit_id), "state": start})
                if to in targets:
                    self.assertEqual(engine.units.transition(unit_id, to, "test")["state"], to)
                else:
                    with self.assertRaises(IllegalTransition):
                        engine.units.transition(unit_id, to, "test")

    def test_a_crash_between_ledger_and_state_file_is_repaired_from_the_ledger(self):
        engine = self.engine()
        engine.units.create({"unit_id": "U-0001"})
        engine.ledger.append("unit_state", unit_id="U-0001", **{"from": "planned"}, to="ready", reason="crashed after")
        self.assertEqual(engine.units.repair_from_ledger(), ["U-0001"])
        self.assertEqual(engine.units.state("U-0001")["state"], "ready")

    def test_terminal_means_done_cancelled_or_exhausted(self):
        self.assertTrue(is_terminal({"state": "done", "retries_spent": 0}))
        self.assertTrue(is_terminal({"state": "blocked", "retries_spent": 3}))
        self.assertFalse(is_terminal({"state": "blocked", "retries_spent": 0}))


class SessionLifecycleTest(EngineCase):
    def test_handoff_spawns_the_next_session_with_the_handoff_in_its_brief(self):
        self.provider.script["spgr-agent-backend-developer"] = [Attempt(end="handoff"), Attempt()]
        engine = self.engine([batch(unit("a"))])
        self.tick_until(engine, lambda: self.states(engine).get("U-0001") == "done")
        state = engine.units.state("U-0001")
        self.assertEqual(state["sessions"], ["S-0001", "S-0002"])
        self.assertEqual(state["retries_spent"], 0)
        self.assertIn("Continue U-0001", self.provider.spawned[1].brief)
        self.assertEqual(engine.sessions("U-0001").get("S-0001")["state"], "handoff")

    def test_a_dead_session_redispatches_and_spends_no_retry(self):
        self.provider.script["spgr-agent-backend-developer"] = [Attempt(end="die"), Attempt()]
        engine = self.engine([batch(unit("a"))])
        self.tick_until(engine, lambda: self.states(engine).get("U-0001") == "done")
        record = engine.units.state("U-0001")
        self.assertEqual(record["retries_spent"], 0)
        self.assertIn("abandoned", [h["state"] for h in record["history"]])
        self.assertEqual(engine.sessions("U-0001").get("S-0001")["outcome"], "dead")

    def test_a_session_over_its_wall_clock_is_killed_and_redispatched(self):
        self.provider.script["spgr-agent-backend-developer"] = [Attempt(ticks=1000), Attempt()]
        engine = self.engine([batch(unit("a", wall_clock_seconds=60))])
        engine.tick()
        self.clock.advance(61)
        self.tick_until(engine, lambda: self.states(engine).get("U-0001") == "done")
        self.assertEqual(engine.sessions("U-0001").get("S-0001")["outcome"], "killed")


class GateRequestTest(EngineCase):
    """A headless session has nobody to ask, so it leaves a file and returns."""

    REQUEST = {"checkpoint_type": "scope-change", "decision_prompt": "Drop the export feature?",
               "options": [{"option": "drop", "consequence": "It goes."}, {"option": "keep", "consequence": "It stays."}],
               "decisions": [{"decision_id": "D1", "kind": "question", "prompt": "Which format?"}]}

    def run_until_blocked(self, request=None):
        engine = self.engine([batch(unit("a"))])
        self.provider.script["spgr-agent-backend-developer"] = [Attempt(ticks=2), Attempt()]
        engine.tick()
        session_dir = engine.sessions("U-0001").dir("S-0001")
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "gate-request.json").write_text(json.dumps(request or self.REQUEST))
        return engine

    def test_it_opens_an_l3_gate_holding_the_unit_and_the_answer_reaches_the_next_brief(self):
        engine = self.run_until_blocked()
        self.tick_until(engine, lambda: self.states(engine)["U-0001"] == "blocked")
        gate = engine.gates.open_gates()[0]["content"]
        self.assertEqual((gate["level"], gate["holds"], gate["checkpoint_type"]), ("L3", ["U-0001"], "scope-change"))
        self.assertEqual(list((engine.run_dir / "artifacts").glob("E-*.json")), [], "asking is not an escalation")
        self.assertEqual(engine.units.state("U-0001")["retries_spent"], 0)
        engine.gates.answer(gate["checkpoint_id"], "keep", "human", free_text="Users asked for it.",
                            decisions=[{"decision_id": "D1", "response": "CSV"}])
        self.tick_until(engine, lambda: self.states(engine)["U-0001"] == "done")
        brief = self.provider.spawned[-1].brief
        for needle in ("Drop the export feature?", "keep", "Users asked for it.", "Which format? CSV"):
            self.assertIn(needle, brief)

    def test_check_running_again_after_a_crash_opens_one_gate(self):
        engine = self.run_until_blocked()
        self.tick_until(engine, lambda: self.states(engine)["U-0001"] == "blocked")
        state = engine.units.state("U-0001")
        engine.units.save({**state, "state": "checking"})
        engine.check()
        self.assertEqual(len(engine.gates.all()), 1)

    def test_a_malformed_request_is_a_defect_not_a_gate(self):
        for bad in ({"checkpoint_type": "made-up", "decision_prompt": "x", "options": [{"option": "a", "consequence": "b"}]},
                    {"checkpoint_type": "scope-change", "decision_prompt": "x", "options": []},
                    {"checkpoint_type": "scope-change", "decision_prompt": "x", "options": [{"option": "a"}]},
                    {**self.REQUEST, "decisions": [{"decision_id": "D1", "kind": "nope", "prompt": "x"}]}):
            with self.subTest(bad):
                shutil.rmtree(self.project / "runs", ignore_errors=True)
                engine = self.run_until_blocked(bad)
                self.tick_until(engine, lambda: len(engine.units.state("U-0001")["sessions"]) > 1
                                or self.states(engine)["U-0001"] == "done")
                self.assertEqual(engine.gates.all(), [])

    @unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed in this interpreter")
    def test_the_gate_it_opens_validates(self):
        engine = self.run_until_blocked()
        self.tick_until(engine, lambda: self.states(engine)["U-0001"] == "blocked")
        self.assertEqual(schema_errors("hil-checkpoint-v2", engine.gates.all()[0]), [])

    def test_a_session_learns_where_the_run_store_is(self):
        engine = self.engine([batch(unit("a"))])
        engine.tick()
        env = self.provider.spawned[0].env
        self.assertEqual(env["SPRINGER_PROJECT_DIR"], str(self.project))
        self.assertEqual(env["SPRINGER_RUN_ID"], "demo")
        self.assertEqual(env["SPRINGER_SESSION_DIR"], str(engine.sessions("U-0001").dir("S-0001")))


class FailureTest(EngineCase):
    def test_defect_spends_retries_goes_one_tier_up_then_blocks_with_a_gate(self):
        self.provider.script["spgr-agent-backend-developer"] = [Attempt(result=fail_result("defect"))]
        engine = self.engine([batch(unit("a"))])
        self.tick_until(engine, lambda: self.states(engine).get("U-0001") == "blocked")
        self.assertEqual([r.model_tier for r in self.provider.spawned], ["sonnet", "sonnet", "opus"])
        self.assertEqual(engine.units.state("U-0001")["retries_spent"], 3)
        self.assertTrue(is_terminal(engine.units.state("U-0001")))
        gate = engine.gates.open_gates()[0]["content"]
        self.assertEqual((gate["level"], gate["holds"]), ("L3", ["U-0001"]))
        self.assertTrue(list((engine.run_dir / "artifacts").glob("E-*.json")))

    def test_answering_retry_on_a_blocked_unit_runs_it_again(self):
        self.provider.script["spgr-agent-backend-developer"] = [Attempt(result=fail_result("blocked")), Attempt()]
        engine = self.engine([batch(unit("a"))])
        self.tick_until(engine, lambda: self.states(engine).get("U-0001") == "blocked")
        engine.gates.answer(engine.gates.open_gates()[0]["content"]["checkpoint_id"], "retry", "human")
        self.tick_until(engine, lambda: self.states(engine)["U-0001"] == "done")

    def test_transient_and_environment_spend_no_retry(self):
        for cause in ("transient", "environment", "context"):
            with self.subTest(cause):
                provider = MockProvider({"spgr-agent-backend-developer": [Attempt(result=fail_result(cause)), Attempt()]})
                shutil.rmtree(self.project / "runs", ignore_errors=True)
                engine = self.engine([batch(unit(cause))], provider=provider)
                self.tick_until(engine, lambda: self.states(engine).get("U-0001") == "done")
                self.assertEqual(engine.units.state("U-0001")["retries_spent"], 0)
                self.assertEqual(len(engine.units.state("U-0001")["sessions"]), 2)

    def test_a_cause_that_does_not_go_away_asks_a_person_on_the_third_time(self):
        """A redispatch spends no retry, so without a bound an environment problem loops
        for as long as the window allows. The first real run did this 26 times."""
        self.provider.script["spgr-agent-backend-developer"] = [Attempt(result=fail_result("environment", "no venv"))]
        engine = self.engine([batch(unit("a"))])
        self.tick_until(engine, lambda: self.states(engine).get("U-0001") == "blocked")
        self.assertEqual(len(engine.units.state("U-0001")["sessions"]), 3)
        gate = engine.gates.open_gates()[0]["content"]
        self.assertIn("3 environment failures in a row", gate["decision_prompt"])
        engine.gates.answer(gate["checkpoint_id"], "retry", "human")
        self.tick_until(engine, lambda: len(engine.units.state("U-0001")["sessions"]) == 4)

    def test_a_builder_that_stops_to_ask_is_told_to_take_the_default(self):
        self.provider.script["spgr-agent-backend-developer"] = [Attempt(result=fail_result("question")), Attempt()]
        engine = self.engine([batch(unit("a"))])
        self.tick_until(engine, lambda: self.states(engine).get("U-0001") == "done")
        self.assertEqual(engine.units.state("U-0001")["retries_spent"], 0)
        self.assertIn("Do not stop to ask", self.provider.spawned[1].brief)

    def test_a_session_with_no_result_file_is_a_defect(self):
        self.provider.script["spgr-agent-backend-developer"] = [Attempt(result=None), Attempt()]
        engine = self.engine([batch(unit("a"))])
        self.tick_until(engine, lambda: self.states(engine).get("U-0001") == "done")
        self.assertEqual(engine.units.state("U-0001")["retries_spent"], 1)


class SchedulingTest(EngineCase):
    def test_overlap_is_by_path_containment(self):
        self.assertTrue(overlaps(["packages/api/"], ["packages/api/orders.ts"]))
        self.assertTrue(overlaps(["a.ts"], ["a.ts"]))
        self.assertFalse(overlaps(["packages/api/"], ["packages/apiary/"]))
        self.assertFalse(overlaps([], ["anything"]))

    def test_overlapping_cycles_run_together_and_a_path_conflict_waits(self):
        self.provider.script["slow"] = [Attempt(ticks=4)]
        engine = self.engine([
            batch(unit("a", agent="slow", declared_paths=("packages/api/",))),
            batch(unit("b", declared_paths=("packages/ui/",)), barrier=False, phase="second"),
            batch(unit("c", declared_paths=("packages/api/orders.ts",)), barrier=False, phase="third"),
        ], maximum=3)
        engine.tick()
        engine.tick()
        engine.tick()
        states = self.states(engine)
        self.assertEqual(len(engine.cycles.ids()), 3, "cycles overlap while the first is in flight")
        self.assertEqual(states["U-0003"], "planned", "c waits on a path a is writing")
        self.assertNotEqual(states["U-0001"], "done")
        self.tick_until(engine, lambda: self.states(engine)["U-0003"] == "done")

    def test_concurrency_stays_within_the_limit(self):
        self.provider.default = Attempt(ticks=3)
        engine = self.engine([batch(*[unit(f"k{i}", declared_paths=(f"p{i}/",)) for i in range(5)])], maximum=2)
        seen = 0
        for _ in range(30):
            engine.tick()
            seen = max(seen, len(engine.units.by_state("running")))
        self.assertEqual(seen, 2)
        self.assertTrue(all(s == "done" for s in self.states(engine).values()))

    def test_a_dependency_waits_and_a_cancelled_one_blocks(self):
        self.provider.default = Attempt(ticks=2)
        engine = self.engine([batch(unit("a"), unit("b", depends_on=("a",)))])
        engine.tick()
        engine.tick()
        self.assertEqual(self.states(engine)["U-0002"], "planned")
        engine.cancel_unit("U-0001", "human")
        engine.tick()
        self.assertEqual(self.states(engine)["U-0002"], "blocked")

    def test_pause_stops_dispatch_while_in_flight_work_finishes(self):
        self.provider.default = Attempt(ticks=2)
        engine = self.engine([batch(unit("a", declared_paths=("a/",)), unit("b", declared_paths=("b/",)),
                                    unit("c", declared_paths=("c/",)))])
        engine.tick()
        engine.ledger.append("operation_applied", op_id="1", type="run.pause", actor="tui", args={"reason": "t"})
        for _ in range(6):
            engine.tick()
        states = self.states(engine)
        self.assertEqual((states["U-0001"], states["U-0002"]), ("done", "done"))
        self.assertIn(states["U-0003"], ("planned", "ready"))
        self.assertEqual(len(self.provider.spawned), 2)
        engine.ledger.append("operation_applied", op_id="2", type="run.resume", actor="tui", args={})
        self.tick_until(engine, lambda: self.states(engine)["U-0003"] == "done")

    def test_redispatch_raises_the_tier_a_human_asked_for(self):
        self.provider.script["spgr-agent-backend-developer"] = [Attempt(ticks=100), Attempt()]
        engine = self.engine([batch(unit("a"))])
        engine.tick()
        engine.ledger.append("operation_applied", op_id="1", type="unit.redispatch", actor="tui",
                             args={"unit_id": "U-0001", "model_tier": "opus"})
        engine.redispatch_unit("U-0001")
        self.tick_until(engine, lambda: self.states(engine)["U-0001"] == "done")
        self.assertEqual(self.provider.spawned[-1].model_tier, "opus")
        self.assertEqual(engine.units.state("U-0001")["retries_spent"], 0)


class MergePolicyTest(EngineCase):
    def setUp(self):
        super().setUp()
        self.provider.script.update({
            "routine": [Attempt(result=pr_result(1, touched=("packages/ui/button.tsx",)))],
            "notable": [Attempt(result=pr_result(2, touched=("packages/ui/x.tsx",), raised_level="L1"))],
            "risky": [Attempt(result=pr_result(3, touched=("packages/auth/session.ts",),
                                               findings=[{"vertical": "spgr-agent-auth", "rule": "R1", "detail": "d"}]))],
            "stacked": [Attempt(result=pr_result(4, branch="unit/U-0002", base="unit/U-0001", touched=("x/y.ts",)))],
        })

    def test_risk_rules_raise_and_never_lower(self):
        self.assertEqual(level_for(["src/ok.ts"], "L0"), "L0")
        self.assertEqual(level_for(["src/auth/x.ts"], "L0"), "L2")
        self.assertEqual(level_for(["src/ok.ts"], "L2", "L1"), "L2")
        self.assertEqual(level_for(["pnpm-lock.yaml"], "L1"), "L2")

    def test_l0_merges_alone_and_writes_no_gate(self):
        engine = self.engine([batch(unit("a", agent="routine"))])
        self.tick_until(engine, lambda: self.states(engine).get("U-0001") == "done")
        self.assertEqual(self.host.merged, [1])
        self.assertEqual(engine.gates.all(), [])

    def actions_engine(self, deployed=None):
        engine = self.engine([batch(unit("a", agent="routine"))])
        engine.settings = lambda: {"ci_signal": "self-hosted-actions", "staging": None}
        engine.deployer = (lambda e: deployed.append(e.run_id)) if deployed is not None else None
        return engine

    def test_with_actions_as_the_ci_signal_the_merge_waits_for_green_checks(self):
        self.host.check_states = {1: ("pending", "checks still running")}
        deployed = []
        engine = self.actions_engine(deployed)
        self.tick_until(engine, lambda: self.states(engine).get("U-0001") == "gated")
        for _ in range(3):
            engine.tick()
        self.assertEqual((self.states(engine)["U-0001"], self.host.merged), ("gated", []))
        self.host.check_states = {1: ("pass", "2 check(s) green")}
        self.tick_until(engine, lambda: self.states(engine)["U-0001"] == "done")
        self.assertEqual((self.host.merged, deployed), ([1], [engine.run_id]), "a merge hands off to the deploy")

    def test_a_failed_check_sends_the_unit_back_as_a_defect(self):
        self.host.check_states = {1: ("fail", "failed: conformance")}
        engine = self.actions_engine()
        self.tick_until(engine, lambda: "U-0001" in engine.units.ids() and engine.units.state("U-0001")["retries_spent"] == 1)
        self.assertEqual(self.host.merged, [])
        notes = (engine.units.unit_dir("U-0001") / "redispatch-notes.txt").read_text()
        self.assertIn("CI failed on PR 1: failed: conformance", notes)

    def test_l1_merges_alone_and_leaves_a_digest_entry_that_holds_nothing(self):
        engine = self.engine([batch(unit("a", agent="notable"))])
        self.tick_until(engine, lambda: self.states(engine).get("U-0001") == "done")
        gate = engine.gates.all()[0]["content"]
        self.assertEqual((gate["digest"], gate["holds"], gate["pipeline_status"]), (True, [], "resumed"))
        self.assertEqual(engine.project()["content"]["open_gates"], [])

    def test_l2_holds_the_merge_and_the_dependent_runs_stacked_then_merges_after(self):
        engine = self.engine([batch(unit("a", agent="risky"), unit("b", agent="stacked", depends_on=("a",)))])
        self.tick_until(engine, lambda: self.states(engine).get("U-0002") == "gated")
        self.assertEqual(self.states(engine)["U-0001"], "gated")
        self.assertEqual(self.host.merged, [], "an L2 hold merges nothing")
        request = self.provider.spawned[-1]
        self.assertEqual(request.unit_id, "U-0002", "the dependent ran while its parent is held")
        for _ in range(3):
            engine.tick()
        self.assertEqual(self.host.merged, [], "the stacked child waits for its parent")
        gate = engine.gates.open_gates()[0]["content"]
        self.assertEqual((gate["level"], gate["holds"]), ("L2", ["U-0001"]))
        self.assertEqual(gate["context"]["findings"][0]["rule"], "R1")
        engine.gates.answer(gate["checkpoint_id"], "approve", "human")
        self.tick_until(engine, lambda: self.states(engine)["U-0002"] == "done")
        self.assertEqual(self.host.merged, [3, 4])
        self.assertEqual(self.host.retargeted, [(4, "main")])

    def test_sending_a_merge_back_spends_a_retry_and_opens_a_fresh_gate(self):
        self.provider.script["risky"].append(self.provider.script["risky"][0])
        engine = self.engine([batch(unit("a", agent="risky"))])
        self.tick_until(engine, lambda: engine.gates.open_gates())
        first = engine.gates.open_gates()[0]["content"]["checkpoint_id"]
        engine.gates.answer(first, "send_back", "human", free_text="Fix the session expiry.")
        self.tick_until(engine, lambda: [g for g in engine.gates.open_gates()
                                         if g["content"]["checkpoint_id"] != first])
        self.assertEqual(engine.units.state("U-0001")["retries_spent"], 1)
        self.assertIn("Fix the session expiry.", self.provider.spawned[-1].brief)
        self.assertEqual(self.host.merged, [])

    def test_an_l3_baseline_never_starts_before_its_gate_is_answered(self):
        engine = self.engine([batch(unit("a", risk_baseline="L3", agent="routine"))])
        for _ in range(4):
            engine.tick()
        self.assertEqual(self.states(engine)["U-0001"], "planned")
        self.assertEqual(self.provider.spawned, [])
        engine.gates.answer(engine.gates.open_gates()[0]["content"]["checkpoint_id"], "proceed", "human")
        self.tick_until(engine, lambda: self.provider.spawned)

    def test_answering_cancel_on_a_start_gate_cancels_the_unit(self):
        engine = self.engine([batch(unit("a", risk_baseline="L3"))])
        engine.tick()
        engine.gates.answer(engine.gates.open_gates()[0]["content"]["checkpoint_id"], "cancel", "human")
        engine.tick()
        self.assertEqual(self.states(engine)["U-0001"], "cancelled")
        self.assertEqual(engine.units.state("U-0001")["cancelled_by"], "human")


class WindowTest(EngineCase):
    def test_an_exhausted_window_parks_then_resumes_after_the_reset(self):
        resets = iso(self.clock() + 600)
        self.provider.signals = [{"used_fraction": 1.0, "resets_at": resets}]
        engine = self.engine([batch(unit("a"))])
        self.assertEqual(engine.tick(), "parked")
        self.assertEqual(self.provider.spawned, [])
        self.assertEqual(engine.project()["content"]["waiting_on"], "usage_window")
        self.clock.advance(601)
        self.provider.signals = [{"used_fraction": 0.1, "resets_at": iso(self.clock() + 18000)}]
        self.assertNotEqual(engine.tick(), "parked")
        self.tick_until(engine, lambda: self.states(engine).get("U-0001") == "done")

    def test_concurrency_falls_as_the_window_fills(self):
        self.provider.default = Attempt(ticks=20)
        self.provider.signals = [{"used_fraction": 0.95, "resets_at": iso(self.clock() + 9000)}]
        engine = self.engine([batch(*[unit(f"k{i}", declared_paths=(f"p{i}/",)) for i in range(4)])], maximum=4)
        for _ in range(3):
            engine.tick()
        self.assertEqual(len(engine.units.by_state("running")), 1)

    def test_a_window_sample_reaches_the_ledger_only_with_work_in_flight(self):
        self.provider.default = Attempt(ticks=3)
        engine = self.engine([batch(unit("a"))])
        engine.tick()
        self.assertEqual(self.events(engine, "window_sample"), [])
        engine.tick()
        self.assertTrue(self.events(engine, "window_sample"))


class LockTest(EngineCase):
    def test_a_live_foreign_lock_leaves_the_run_alone(self):
        engine = self.engine([batch(unit("a"))])
        engine.lock.path.parent.mkdir(parents=True, exist_ok=True)
        engine.lock.path.write_text(json.dumps({"session_id": "claude-session", "claimed_at": iso(self.clock())}))
        self.assertEqual(engine.tick(), "held")
        self.assertEqual(self.provider.spawned, [])
        self.assertEqual(json.loads(engine.lock.path.read_text())["session_id"], "claude-session")

    def test_a_stale_foreign_lock_is_taken_over(self):
        engine = self.engine([batch(unit("a"))])
        engine.lock.path.parent.mkdir(parents=True, exist_ok=True)
        engine.lock.path.write_text(json.dumps({"session_id": "claude-session", "claimed_at": iso(self.clock() - 1801)}))
        self.assertNotEqual(engine.tick(), "held")
        self.assertEqual(json.loads(engine.lock.path.read_text())["session_id"], OWNER)

    def test_a_previous_daemons_lock_is_taken_over_even_when_fresh(self):
        engine = self.engine()
        engine.lock.path.parent.mkdir(parents=True, exist_ok=True)
        engine.lock.path.write_text(json.dumps({"session_id": "daemon:old:9", "claimed_at": iso(self.clock())}))
        self.assertEqual(engine.recover(), "recovered")
        self.assertEqual(json.loads(engine.lock.path.read_text())["session_id"], OWNER)

    def test_the_lock_format_is_the_one_claim_run_reads(self):
        from helpers import SCRIPTS, load_script
        claim = load_script(SCRIPTS / "claim-run.py")
        engine = self.engine([batch(unit("a"))])
        self.clock.t = __import__("time").time()
        engine.tick()
        lock = claim.read_lock(engine.run_dir) if hasattr(claim, "read_lock") else json.loads(engine.lock.path.read_text())
        self.assertEqual(lock["session_id"], OWNER)
        self.assertEqual(claim.main(["claim-run.py", str(engine.run_dir), "claim", "other-session"]), 1)


class RecoveryTest(EngineCase):
    """A fresh engine stands for a fresh daemon: same files, no memory, no handles."""

    def restart(self, engine, batches=()):
        fresh = self.engine(batches, owner="daemon:new:2")
        self.assertEqual(fresh.recover(), "recovered")
        return fresh

    def test_a_running_unit_is_dead_and_redispatched_with_no_retry_spent(self):
        self.provider.default = Attempt(ticks=50)
        engine = self.engine([batch(unit("a"))])
        engine.tick()
        fresh = self.restart(engine)
        self.assertEqual(self.states(fresh)["U-0001"], "redispatch")
        self.assertEqual(fresh.units.state("U-0001")["retries_spent"], 0)
        self.assertEqual(fresh.sessions("U-0001").get("S-0001")["outcome"], "dead")
        self.assertEqual(self.events(fresh, "session_exited")[-1]["outcome"], "dead")
        self.provider.default = Attempt()
        self.tick_until(fresh, lambda: self.states(fresh)["U-0001"] == "done")

    def test_a_redispatch_carries_the_handoff_the_dead_session_left(self):
        self.provider.default = Attempt(ticks=50)
        engine = self.engine([batch(unit("a"))])
        engine.tick()
        (engine.sessions("U-0001").dir("S-0001") / "handoff.md").write_text("Pick up at step 4.\n")
        fresh = self.restart(engine)
        self.provider.default = Attempt()
        self.tick_until(fresh, lambda: self.states(fresh)["U-0001"] == "done")
        self.assertIn("Pick up at step 4.", self.provider.spawned[-1].brief)

    def test_a_checking_unit_runs_check_again_from_disk(self):
        engine = self.engine([batch(unit("a"))])
        self.tick_until(engine, lambda: self.states(engine).get("U-0001") == "done")
        state = engine.units.state("U-0001")
        engine.units.save({**state, "state": "checking"})
        fresh = self.restart(engine)
        fresh.check()
        self.assertEqual(self.states(fresh)["U-0001"], "done")

    def _gated(self):
        self.provider.script["risky"] = [Attempt(result=pr_result(9, touched=("src/auth/a.ts",)))]
        engine = self.engine([batch(unit("a", agent="risky"))])
        self.tick_until(engine, lambda: self.states(engine).get("U-0001") == "gated")
        return engine

    def test_a_gated_unit_with_an_open_pr_stays_gated(self):
        fresh = self.restart(self._gated())
        self.assertEqual(self.states(fresh)["U-0001"], "gated")

    def test_a_gated_unit_whose_pr_merged_is_done(self):
        engine = self._gated()
        self.host.prs[9] = "merged"
        self.assertEqual(self.states(self.restart(engine))["U-0001"], "done")

    def test_a_gated_unit_whose_pr_closed_is_blocked_with_an_escalation(self):
        engine = self._gated()
        self.host.prs[9] = "closed"
        fresh = self.restart(engine)
        self.assertEqual(self.states(fresh)["U-0001"], "blocked")
        self.assertTrue(list((fresh.run_dir / "artifacts").glob("E-*.json")))

    def test_an_orphan_worktree_is_removed_and_a_retrying_one_is_kept(self):
        self.provider.script["spgr-agent-backend-developer"] = [Attempt(result=fail_result("defect")), Attempt()]
        engine = self.engine([batch(unit("a"))])
        engine.tick()
        engine.reconcile()
        engine.join()
        engine.check()
        self.assertEqual(self.states(engine)["U-0001"], "retry")
        self.assertTrue(engine.worktrees.path("U-0001").exists(), "a retry reuses its worktree")
        orphan, _ = engine.worktrees.claim("U-0099", "main")
        fresh = self.restart(engine)
        self.assertFalse(orphan.exists())
        self.assertTrue(fresh.worktrees.path("U-0001").exists())

    def test_a_worktree_git_refuses_to_remove_is_logged_and_kept(self):
        engine = self.engine()
        path, _ = engine.worktrees.claim("U-0099", "main")
        (path / "uncommitted.txt").write_text("work\n")
        fresh = self.restart(engine)
        self.assertTrue(path.exists())
        self.assertEqual(self.events(fresh, "worktree_kept")[0]["unit_id"], "U-0099")

    def test_recovery_leaves_a_run_a_live_session_holds(self):
        engine = self.engine()
        engine.lock.path.parent.mkdir(parents=True, exist_ok=True)
        engine.lock.path.write_text(json.dumps({"session_id": "claude-session", "claimed_at": iso(self.clock())}))
        self.assertEqual(self.engine(owner="daemon:new:2").recover(), "held")

    def test_a_tick_interrupted_after_exit_joins_on_restart(self):
        engine = self.engine([batch(unit("a"))])
        engine.tick()
        engine.reconcile()
        record = engine.sessions("U-0001").get("S-0001")
        if record["state"] != "exited":
            self.fail(f"the mock session should have exited, found {record['state']}")
        fresh = self.restart(engine)
        fresh.tick()
        self.assertEqual(self.states(fresh)["U-0001"], "done")


def canned_batches():
    return [
        batch(unit("prd", agent="spgr-agent-product-manager", model_tier="sonnet"), phase="requirements"),
        batch(unit("design", agent="spgr-agent-design", declared_paths=("docs/design/",)),
              unit("arch", agent="spgr-agent-architect", model_tier="opus", declared_paths=("docs/adr/",)),
              gates=[GateDraft("direction-review", "Pick a direction.", holds=("design",), level="L3",
                               options=({"option": "accept", "consequence": "Structure freezes.",
                                         "recommended_because": "Reads best."},),
                               decisions=({"decision_id": "D1", "kind": "design-direction-selection",
                                           "prompt": "Which direction?"},))],
              phase="direction"),
        batch(unit("skeleton", agent="routine", declared_paths=("apps/web/",)), phase="skeleton"),
        batch(unit("notable-1", agent="notable", declared_paths=("packages/ui/",)),
              unit("auth", agent="risky", declared_paths=("packages/auth/",)),
              unit("after-auth", agent="stacked", depends_on=("auth",), declared_paths=("apps/web/login/",)),
              phase="development"),
    ]


class CannedRunTest(EngineCase):
    def setUp(self):
        super().setUp()
        self.provider.script.update({
            "routine": [Attempt(ticks=2, result=pr_result(1, touched=("apps/web/page.tsx",)))],
            "notable": [Attempt(result=pr_result(2, touched=("packages/ui/b.tsx",), raised_level="L1"))],
            "risky": [Attempt(ticks=2, result=pr_result(3, touched=("packages/auth/session.ts",)))],
            "stacked": [Attempt(result=pr_result(4, base="unit/U-0005", touched=("apps/web/login/p.tsx",)))],
        })

    def drive(self, engine):
        """Answer gates as a person would, one per pass, until the run completes."""
        for _ in range(80):
            if engine.tick() == "complete":
                return
            for gate in engine.gates.open_gates():
                content = gate["content"]
                if not content["digest"]:
                    engine.gates.answer(content["checkpoint_id"], content["options"][0]["option"], "human",
                                        decisions=[{"decision_id": d["decision_id"], "response": "A"}
                                                   for d in content.get("decisions", [])])
        self.fail(f"run did not complete: {self.states(engine)}")

    def test_the_run_goes_from_plan_to_complete(self):
        engine = self.engine(canned_batches())
        self.drive(engine)
        self.assertTrue(all(s == "done" for s in self.states(engine).values()), self.states(engine))
        self.assertEqual(len(engine.units.ids()), 7)
        self.assertCountEqual(self.host.merged, [1, 2, 3, 4])
        self.assertEqual(engine.worktrees.claimed(), [])
        self.assertTrue(engine.cycles.is_complete())
        self.assertTrue(all(c["content"]["closed"] for c in engine.cycles.all()))

    def test_repeated_crashes_still_complete_with_no_retry_spent(self):
        """A crash every fourth tick, because a session needs a tick to spawn and a
        tick per poll to return. A crash on every tick can make no progress."""
        engine = self.engine(canned_batches())
        for count in range(1, 400):
            result = engine.tick()
            for gate in engine.gates.open_gates():
                content = gate["content"]
                if not content["digest"]:
                    engine.gates.answer(content["checkpoint_id"], content["options"][0]["option"], "human")
            if result == "complete":
                break
            if count % 4:
                continue
            planner = engine.planner
            engine = self.engine(owner="daemon:new:2")
            engine.planner = planner
            engine.recover()
        self.assertTrue(engine.cycles.is_complete(), self.states(engine))
        self.assertTrue(all(engine.units.state(u)["retries_spent"] == 0 for u in engine.units.ids()))

    @unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed in this interpreter")
    def test_everything_the_daemon_wrote_validates_against_its_schema(self):
        engine = self.engine(canned_batches())
        self.drive(engine)
        reg = registry()
        checked = 0
        for unit_id in engine.units.ids():
            for name, obj in (("unit-spec-v1", engine.units.spec(unit_id)), ("unit-state-v1", engine.units.state(unit_id))):
                self.assertEqual(schema_errors(name, obj, reg), [], f"{name} {unit_id}")
                checked += 1
            for record in engine.sessions(unit_id).all():
                self.assertEqual(schema_errors("session-v1", record, reg), [], unit_id)
                checked += 1
        for gate in engine.gates.all():
            self.assertEqual(schema_errors("hil-checkpoint-v2", gate, reg), [], gate["artifact_id"])
            checked += 1
        for cycle in engine.cycles.all():
            self.assertEqual(schema_errors("pdca-cycle-v1", cycle, reg), [], cycle["artifact_id"])
            checked += 1
        self.assertEqual(schema_errors("run-state-v2", engine.project(), reg), [])
        self.assertEqual(schema_errors("usage-window-v1", engine.window.read(), reg), [])
        for line in self.events(engine):
            self.assertEqual(schema_errors("events-v1", line, reg), [], line)
            checked += 1
        self.assertGreater(checked, 50)
        seqs = [line["seq"] for line in self.events(engine)]
        self.assertEqual(seqs, sorted(set(seqs)), "seq is monotonic")

    @unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed in this interpreter")
    def test_records_validate_while_the_run_is_in_progress_too(self):
        """A crash can leave any tick's files as the last word, so open records count."""
        engine = self.engine(canned_batches())
        reg = registry()
        for _ in range(12):
            engine.tick()
            for cycle in engine.cycles.all():
                self.assertEqual(schema_errors("pdca-cycle-v1", cycle, reg), [], cycle["artifact_id"])
            for gate in engine.gates.all():
                self.assertEqual(schema_errors("hil-checkpoint-v2", gate, reg), [], gate["artifact_id"])
                if not gate["content"]["response"] and not gate["content"]["digest"]:
                    engine.gates.answer(gate["content"]["checkpoint_id"], gate["content"]["options"][0]["option"], "human")
            self.assertEqual(schema_errors("run-state-v2", engine.project(), reg), [])

    def test_a_cycle_records_its_units_and_reads_pending_until_act(self):
        engine = self.engine([batch(unit("a"))])
        engine.tick()
        content = engine.cycles.all()[0]["content"]
        self.assertEqual(content["plan"]["routed_batch"][0]["unit_id"], "U-0001")
        self.assertEqual(content["do"]["dispatched"][0]["status"], "pending")

    def test_the_projection_rebuilds_the_same_from_files_alone(self):
        engine = self.engine(canned_batches())
        self.drive(engine)
        first = engine.project()["content"]
        second = self.engine(owner="daemon:new:2").project()["content"]
        self.assertEqual(first, second)
        self.assertEqual(first["units"], {"done": 7})


if __name__ == "__main__":
    unittest.main()
