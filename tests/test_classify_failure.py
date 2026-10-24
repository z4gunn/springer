"""spgr-run-harness/scripts/classify-failure.py: a retry is spent only on a
defect. Platform, context, block, and environment failures each get their
own policy."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from helpers import SCRIPTS, load_script

cf = load_script(SCRIPTS / "classify-failure.py")


class ClassifyFailureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.unit = Path(self.tmp.name) / "runs" / "r1" / "dispatch" / "C1" / "U1"
        self.unit.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        (self.unit / name).write_text(text)

    def receipt(self, name, result, tail=""):
        (self.unit / "receipts").mkdir(exist_ok=True)
        (self.unit / "receipts" / f"{name}.json").write_text(
            json.dumps({"name": name, "result": result, "output_tail": tail}))

    def test_each_class_from_its_signal(self):
        cases = [
            ("return.txt", "API Error: 529 Overloaded", "transient"),
            ("return.txt", "Claude usage limit reached. Your limit will reset at 5pm", "transient"),
            ("return.txt", "Error: prompt is too long: 210000 tokens > 200000 maximum", "context"),
            ("return.txt", "Status: BLOCKED\nThe API spec has no endpoint for exports.", "blocked"),
            ("result.md", "NEEDS_CONTEXT: which tenant model applies?", "blocked"),
            ("result.md", "bash: pnpm: command not found", "environment"),
            ("result.md", "To get started with GitHub CLI, please run:  gh auth login", "environment"),
        ]
        for name, text, expected in cases:
            for f in self.unit.glob("*.*"):
                f.unlink()
            self.write(name, text)
            self.assertEqual(cf.classify(self.unit)[0], expected, text)

    def test_failed_or_zero_run_receipt_is_a_defect_that_spends_a_retry(self):
        self.write("return.txt", "DONE\n3 files changed")
        self.receipt("unit", "zero-run", "collected 0 items")
        cls, evidence = cf.classify(self.unit)
        self.assertEqual(cls, "defect")
        self.assertIn("zero-run", evidence)
        self.assertTrue(cf.POLICY[cls][1])

    def test_platform_failure_beats_a_failed_receipt(self):
        self.receipt("unit", "fail", "AssertionError")
        self.write("return.txt", "rate limit exceeded, retry after 60s")
        self.assertEqual(cf.classify(self.unit)[0], "transient")

    def test_a_word_inside_prose_does_not_block(self):
        self.write("result.md", "The story was blocked on nothing. Every test passed.")
        self.assertEqual(cf.classify(self.unit)[0], "defect")

    def test_main_prints_and_appends_an_event(self):
        run_dir = Path(self.tmp.name) / "runs" / "r1"
        self.write("return.txt", "overloaded_error")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cf.main(["classify-failure.py", str(self.unit), "--run-dir", str(run_dir)]), 0)
        result = json.loads(out.getvalue())
        self.assertEqual((result["class"], result["spends_retry"]), ("transient", False))
        event = json.loads((run_dir / "events.jsonl").read_text().splitlines()[-1])
        self.assertEqual((event["event"], event["class"], event["unit_id"]), ("unit_failure", "transient", "U1"))

    def test_usage(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cf.main(["classify-failure.py"]), 2)
            self.assertEqual(cf.main(["classify-failure.py", str(self.unit / "nope")]), 2)


if __name__ == "__main__":
    unittest.main()
