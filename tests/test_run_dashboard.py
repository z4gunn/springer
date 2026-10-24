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


if __name__ == "__main__":
    unittest.main()
