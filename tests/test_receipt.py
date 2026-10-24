"""spgr-run-harness/scripts/receipt.py: evidence a script can hold a gate on.
A test command that ran nothing is zero-run, never pass, and a receipt that
names another commit or tree is stale."""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import SCRIPTS, load_script

rc = load_script(SCRIPTS / "receipt.py")
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@x", "PATH": "/usr/bin:/bin:/usr/local/bin"}


def sh(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
                          env=dict(GIT_ENV, HOME=str(repo)))


def say(text, code=0):
    """A shell command that prints text and exits with code."""
    return f"{sys.executable} -c \"import sys; print({text!r}); sys.exit({code})\""


class CountTest(unittest.TestCase):
    def test_runner_summaries(self):
        cases = {
            "Ran 12 tests in 0.3s\n\nOK": 12,
            "===== 7 passed, 1 skipped in 2.1s =====": 7,
            "Tests:       2 failed, 40 passed, 42 total": 42,
            "  9 passing (30ms)": 9,
            "# tests 5\n# pass 5": 5,
            "test result: ok. 3 passed; 0 failed": 3,
            "14 examples, 0 failures": 14,
            "--- PASS: TestA (0.00s)\n--- PASS: TestB (0.00s)\nok  pkg": 2,
            " Test Files  1 passed (1)\n      Tests  6 passed (6)": 6,
        }
        for output, expected in cases.items():
            self.assertEqual(rc.count_tests(output), expected, output)

    def test_zero_and_unknown(self):
        self.assertEqual(rc.count_tests("collected 0 items\n\nno tests ran in 0.01s"), 0)
        self.assertEqual(rc.count_tests("?   pkg/x  [no test files]"), 0)
        self.assertIsNone(rc.count_tests("all good"))
        self.assertEqual(rc.count_tests("cases: 4 ok", r"cases: (\d+) ok"), 4)


class ReceiptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "app"
        self.repo.mkdir()
        sh(self.repo, "init", "-q", "-b", "main")
        (self.repo / "a.py").write_text("x = 1\n")
        sh(self.repo, "add", "a.py")
        sh(self.repo, "commit", "-q", "-m", "base")
        self.unit = self.repo / "runs" / "r1" / "dispatch" / "C1" / "U1"

    def tearDown(self):
        self.tmp.cleanup()

    def run_receipt(self, name, command, kind="test", *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = rc.main(["receipt.py", "run", str(self.unit), "--name", name, "--kind", kind,
                            "--cwd", str(self.repo), *extra, "--", command])
        return code, json.loads((self.unit / "receipts" / f"{name}.json").read_text())

    def verify(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = rc.main(["receipt.py", "verify", str(self.unit), "--cwd", str(self.repo), *extra])
        return code, out.getvalue()

    def test_passing_suite_with_a_count_holds(self):
        code, r = self.run_receipt("unit", say("Ran 4 tests in 0.1s"))
        self.assertEqual((code, r["result"], r["tests_ran"]), (0, "pass", 4))
        self.assertEqual(r["head"], sh(self.repo, "rev-parse", "HEAD").stdout.strip())
        self.assertEqual(self.verify("--require", "test")[0], 0)

    def test_green_exit_with_no_tests_is_zero_run(self):
        code, r = self.run_receipt("unit", say("collected 0 items"))
        self.assertEqual((code, r["result"]), (1, "zero-run"))
        code, out = self.verify()
        self.assertEqual(code, 1)
        self.assertIn("zero-run", out)

    def test_unreadable_count_fails_until_a_regex_is_given(self):
        self.assertEqual(self.run_receipt("unit", say("all good"))[1]["result"], "unknown-count")
        code, r = self.run_receipt("unit", say("cases: 3 ok"), "test", "--count-regex", r"cases: (\d+) ok")
        self.assertEqual((code, r["result"], r["tests_ran"]), (0, "pass", 3))

    def test_check_kind_needs_only_the_exit_code(self):
        code, r = self.run_receipt("lint", say("clean"), "check")
        self.assertEqual((code, r["result"], r["tests_ran"]), (0, "pass", None))

    def test_failing_command_keeps_its_exit_code(self):
        code, r = self.run_receipt("unit", say("Ran 2 tests\nFAILED (failures=1)", 3))
        self.assertEqual((code, r["result"]), (3, "fail"))

    def test_a_new_commit_or_an_edited_tree_makes_the_receipt_stale(self):
        self.run_receipt("unit", say("Ran 4 tests"))
        (self.repo / "a.py").write_text("x = 2\n")
        code, out = self.verify()
        self.assertEqual(code, 1)
        self.assertIn("stale tree", out)
        sh(self.repo, "commit", "-q", "-am", "more")
        code, out = self.verify()
        self.assertIn("stale commit", out)

    def test_run_store_writes_do_not_stale_the_receipt(self):
        self.run_receipt("unit", say("Ran 4 tests"))
        (self.repo / "runs" / "r1" / "events.jsonl").write_text("{}\n")
        self.assertEqual(self.verify()[0], 0)

    def test_missing_receipts_and_required_kinds_fail(self):
        code, out = self.verify()
        self.assertEqual(code, 1)
        self.assertIn("no receipts", out)
        self.run_receipt("lint", say("clean"), "check")
        code, out = self.verify("--require", "test")
        self.assertIn("no passing test receipt", out)

    def test_usage(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(rc.main(["receipt.py"]), 2)
            self.assertEqual(rc.main(["receipt.py", "run", str(self.unit), "--", "true"]), 2)
            self.assertEqual(rc.main(["receipt.py", "verify", str(self.unit), "--require", "vibes"]), 2)


if __name__ == "__main__":
    unittest.main()
