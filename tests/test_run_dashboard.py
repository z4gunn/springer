"""spgr-run-harness/scripts/run-dashboard.py: the project roll-up counts the
outcome figure and the failure mix from the run event feeds."""

import json
import re
import tempfile
import unittest
from pathlib import Path

from helpers import SCRIPTS, load_script

rd = load_script(SCRIPTS / "run-dashboard.py")
ANSI = re.compile(r"\x1b\[[0-9;]*m")


class DashboardRollupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        run = self.root / "runs" / "r1"
        run.mkdir(parents=True)
        events = [
            {"event": "agent_dispatched", "agent": "a"},
            {"event": "agent_dispatched", "agent": "b"},
            {"event": "product_check", "result": "pass"},
            {"event": "unit_failure", "class": "transient"},
            {"event": "unit_failure", "class": "transient"},
            {"event": "unit_failure", "class": "defect"},
        ]
        (run / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))

    def tearDown(self):
        self.tmp.cleanup()

    def test_failure_mix_and_outcomes(self):
        stats = rd.aggregate_project(str(self.root))
        self.assertEqual(stats["failures"], {"transient": 2, "defect": 1})
        self.assertEqual((stats["outcomes_passed"], stats["dispatches"]), (1, 2))
        line = ANSI.sub("", rd.failure_line(stats))
        self.assertIn("failures 3", line)
        self.assertIn("defect 1, transient 2", line)
        self.assertIn("50.0 per 100 dispatches", ANSI.sub("", rd.outcome_line(stats)))

    def test_no_failures_means_no_line(self):
        (self.root / "runs" / "r1" / "events.jsonl").write_text("")
        self.assertIsNone(rd.failure_line(rd.aggregate_project(str(self.root))))



class LatestCycleTest(unittest.TestCase):
    def test_latest_cycle_is_found_by_type_and_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            art = Path(tmp) / "artifacts"
            art.mkdir()
            for n in (3, 12, 7):
                (art / f"pdca-cycle-{n:04d}-r1.json").write_text(json.dumps(
                    {"artifact_type": "pdca-cycle", "content": {"cycle_number": n}}))
            (art / "prd-v1.json").write_text(json.dumps({"artifact_type": "prd", "content": {"cycle_number": 99}}))
            self.assertEqual(rd.latest_cycle(tmp)["content"]["cycle_number"], 12)
            self.assertIsNone(rd.latest_cycle(str(Path(tmp) / "nope")))


if __name__ == "__main__":
    unittest.main()
