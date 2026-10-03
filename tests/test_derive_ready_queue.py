"""derive-ready-queue.py: the readiness snapshot is a pure function of the
store. Each test states one fact in the store and checks one field of the
snapshot, so a regression names the rule it broke."""

import json
import tempfile
import unittest
from pathlib import Path

from helpers import SCRIPTS, RunStore, load_script

drq = load_script(SCRIPTS / "derive-ready-queue.py")


class DeriveReadyQueueTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = RunStore(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def snapshot(self, session_id=None):
        return drq.derive(self.store.run_dir, session_id)

    def test_empty_store_is_not_blocked(self):
        snap = self.snapshot()
        self.assertFalse(snap["blocked"])
        self.assertEqual(snap["cycle_counter"], 0)
        self.assertIsNone(snap["latest_phase"])
        self.assertEqual(snap["profile"], "brochure")

    def test_latest_phase_comes_from_the_last_cycle(self):
        self.store.add_cycle(phase="requirements", next_phase="architecture")
        self.store.add_cycle(phase="architecture", next_phase="design")
        snap = self.snapshot()
        self.assertEqual(snap["cycle_counter"], 2)
        self.assertEqual(snap["latest_phase"], "design")

    def test_gate_with_no_holds_blocks_all_work(self):
        self.store.add_gate("HIL-0001", "prd-approval")
        snap = self.snapshot()
        self.assertTrue(snap["blocked"])
        self.assertIn("HIL-0001", snap["blocking_reason"])
        self.assertEqual(snap["open_gates"], ["HIL-0001"])
        self.assertEqual(snap["held"], [])

    def test_gate_holding_some_work_reports_held_and_does_not_block(self):
        self.store.add_gate("HIL-0002", "pr-merge", holds=["S-3", "development"])
        snap = self.snapshot()
        self.assertFalse(snap["blocked"])
        self.assertEqual(snap["open_gates"], ["HIL-0002"])
        self.assertEqual(snap["held"], ["S-3", "development"])
        self.assertEqual(snap["open_gate_detail"][0]["holds"], ["S-3", "development"])

    def test_gate_holding_all_explicitly_blocks(self):
        self.store.add_gate("HIL-0003", "scope-change", holds=["all"])
        self.assertTrue(self.snapshot()["blocked"])

    def test_answered_gate_is_reported_and_releases_the_block(self):
        self.store.add_gate("HIL-0004", "direction-review", answered=True)
        snap = self.snapshot()
        self.assertFalse(snap["blocked"])
        self.assertEqual(snap["answered_gates"], ["HIL-0004"])
        self.assertEqual(snap["open_gates"], [])

    def test_resumed_gate_is_not_open(self):
        self.store.add_gate("HIL-0005", "pr-merge", status="resumed")
        snap = self.snapshot()
        self.assertEqual(snap["open_gates"], [])
        self.assertEqual(snap["answered_gates"], [])

    def test_archived_gate_cannot_resurrect_a_block(self):
        self.store.add_gate("HIL-0006", "prd-approval", subdir="archive")
        self.assertFalse(self.snapshot()["blocked"])

    def test_gate_in_artifacts_dir_counts_the_same(self):
        self.store.add_gate("HIL-0007", "prd-approval", subdir="artifacts")
        self.assertTrue(self.snapshot()["blocked"])

    def test_open_escalation_blocks(self):
        self.store.add_escalation("ESC-0001", status="open")
        snap = self.snapshot()
        self.assertTrue(snap["blocked"])
        self.assertEqual(snap["open_escalations"], ["ESC-0001"])

    def test_resolved_escalation_does_not_block(self):
        self.store.add_escalation("ESC-0002", status="resolved")
        snap = self.snapshot()
        self.assertFalse(snap["blocked"])
        self.assertEqual(snap["open_escalations"], [])

    def test_unjoined_foreground_dispatch_blocks(self):
        self.store.add_event("agent_dispatched", tool_use_id="tu-1")
        snap = self.snapshot()
        self.assertTrue(snap["blocked"])
        self.assertEqual(snap["unjoined_dispatches"][0]["tool_use_id"], "tu-1")

    def test_completed_dispatch_is_joined(self):
        self.store.add_event("agent_dispatched", tool_use_id="tu-1")
        self.store.add_event("agent_completed", tool_use_id="tu-1")
        self.assertEqual(self.snapshot()["unjoined_dispatches"], [])

    def test_backgrounded_is_not_a_join(self):
        self.store.add_event("agent_dispatched", tool_use_id="tu-2")
        self.store.add_event("agent_backgrounded", tool_use_id="tu-2", agent_id="ag-9")
        self.assertTrue(self.snapshot()["blocked"])

    def test_backgrounded_joins_when_the_agent_stops(self):
        self.store.add_event("agent_dispatched", tool_use_id="tu-2")
        self.store.add_event("agent_backgrounded", tool_use_id="tu-2", agent_id="ag-9")
        self.store.add_event("agent_stopped", agent_id="ag-9")
        self.assertEqual(self.snapshot()["unjoined_dispatches"], [])

    def test_abandoned_dispatch_is_released(self):
        self.store.add_event("agent_dispatched", tool_use_id="tu-3")
        self.store.add_event("agent_abandoned", tool_use_id="tu-3")
        self.assertFalse(self.snapshot()["blocked"])

    def test_malformed_event_line_is_skipped(self):
        self.store.add_event("agent_dispatched", tool_use_id="tu-4")
        with open(self.store.run_dir / "events.jsonl", "a") as fh:
            fh.write("{not json\n")
        self.store.add_event("agent_completed", tool_use_id="tu-4")
        self.assertFalse(self.snapshot()["blocked"])

    def test_live_lock_from_another_session_blocks(self):
        self.store.set_lock("other-session")
        snap = self.snapshot(session_id="me")
        self.assertTrue(snap["blocked"])
        self.assertIn("other-session", snap["blocking_reason"])

    def test_own_live_lock_does_not_block(self):
        self.store.set_lock("me")
        self.assertFalse(self.snapshot(session_id="me")["blocked"])

    def test_stale_lock_does_not_block(self):
        self.store.set_lock("other-session", seconds_ago=31 * 60)
        snap = self.snapshot(session_id="me")
        self.assertFalse(snap["blocked"])
        self.assertFalse(snap["lock"]["alive"])

    def test_autonomy_defaults_by_profile(self):
        self.assertEqual(self.snapshot()["autonomy"], "standard")
        saas = RunStore(self.tmp.name, run_id="saas", profile="saas")
        self.assertEqual(drq.derive(saas.run_dir)["autonomy"], "supervised")

    def test_autopilot_falls_back_to_standard_outside_brochure_and_small(self):
        store = RunStore(self.tmp.name, run_id="big", profile="saas", autonomy="autopilot")
        self.assertEqual(drq.derive(store.run_dir)["autonomy"], "standard")
        small = RunStore(self.tmp.name, run_id="sm", profile="small", autonomy="autopilot")
        self.assertEqual(drq.derive(small.run_dir)["autonomy"], "autopilot")

    def test_missing_brief_means_supervised_and_no_profile(self):
        store = RunStore(self.tmp.name, run_id="nobrief", profile=None)
        snap = drq.derive(store.run_dir)
        self.assertIsNone(snap["profile"])
        self.assertEqual(snap["autonomy"], "supervised")

    def test_open_defaults_counts_only_open_lines(self):
        self.store.set_defaults([
            "- DEF-001 | copy | took default | alt | low | prd | open",
            "- DEF-002 | layout | took default | alt | low | ia | accepted",
            "DEF-003 | tone | took default | alt | low | prd | open",
            "- note: not a default line, open or not",
        ])
        self.assertEqual(self.snapshot()["open_defaults"], 2)

    def test_inventory_marks_fully_confirmed_artifacts(self):
        self.store.add_artifact("prd-demo", "prd", confirmed=True)
        self.store.add_artifact("nfr-demo", "nfr", confirmed=False)
        inv = {i["artifact_id"]: i for i in self.snapshot()["artifact_inventory"]}
        self.assertTrue(inv["prd-demo"]["all_confirmed"])
        self.assertFalse(inv["nfr-demo"]["all_confirmed"])
        self.assertNotIn("run-brief-demo", inv)

    def test_malformed_artifact_is_a_read_error_not_a_block(self):
        self.store.write_raw("artifacts/broken.json", "{")
        snap = self.snapshot()
        self.assertEqual(len(snap["read_errors"]), 1)
        self.assertFalse(snap["blocked"])

    def test_main_prints_json_and_rejects_a_missing_store(self):
        import io
        import contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = drq.main(["derive-ready-queue.py", str(self.store.run_dir), "--session", "me"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["run_id"], "demo")
        self.assertEqual(drq.main(["derive-ready-queue.py", str(Path(self.tmp.name) / "nope")]), 1)


if __name__ == "__main__":
    unittest.main()
