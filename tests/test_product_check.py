"""product-check.py: the real product on real inputs, recorded as outcomes."""

import contextlib
import io
import json
import os
import tempfile
import unittest

from helpers import SCRIPTS, load_script

pc = load_script(SCRIPTS / "product-check.py")


class ProductCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.runs = os.path.join(self.root, "runs")
        self.run_dir = os.path.join(self.runs, "r1")
        os.makedirs(self.run_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def write_config(self, checks):
        with open(os.path.join(self.runs, "_product-check.json"), "w") as fh:
            json.dump({"checks": checks}, fh)

    def run_cmd(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = pc.main(["product-check.py", self.run_dir, *args])
        return code, out.getvalue()

    def events(self):
        path = os.path.join(self.run_dir, "events.jsonl")
        if not os.path.exists(path):
            return []
        with open(path) as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def two_checks(self):
        self.write_config([
            {"id": "ok", "flow": "open the page", "expect": "it renders",
             "command": "echo rendered", "touches": ["web/"]},
            {"id": "bad", "flow": "upload", "expect": "names appear",
             "command": "echo no names >&2; exit 1", "touches": ["worker/"]},
        ])

    def test_pass_and_fail_are_recorded_as_events_and_a_results_file(self):
        self.two_checks()
        code, out = self.run_cmd("--cycle", "CYCLE-0007")
        self.assertEqual(code, 1)
        self.assertIn("PASS  ok", out)
        self.assertIn("FAIL  bad", out)
        self.assertIn("no names", out)
        events = self.events()
        self.assertEqual([e["event"] for e in events], ["product_check", "product_check"])
        self.assertEqual({e["check_id"]: e["result"] for e in events}, {"ok": "pass", "bad": "fail"})
        self.assertTrue(all(e["cycle_id"] == "CYCLE-0007" and e["run_id"] == "r1" for e in events))
        results_dir = os.path.join(self.run_dir, "product-checks")
        files = os.listdir(results_dir)
        self.assertEqual(len(files), 1)
        with open(os.path.join(results_dir, files[0])) as fh:
            body = json.load(fh)
        self.assertEqual(body["cycle_id"], "CYCLE-0007")
        self.assertEqual(body["results"][0]["output_tail"].strip(), "rendered")
        self.assertEqual(body["results"][1]["exit_code"], 1)

    def test_touches_selects_only_the_checks_that_watch_the_changed_paths(self):
        self.two_checks()
        code, out = self.run_cmd("--touches", "web/src/App.tsx")
        self.assertEqual(code, 0)
        self.assertEqual([e["check_id"] for e in self.events()], ["ok"])
        code, out = self.run_cmd("--touches", "docs/readme.md")
        self.assertEqual(code, 0)
        self.assertIn("nothing to run", out)
        self.assertEqual(len(self.events()), 1)

    def test_a_check_with_no_touches_runs_on_any_change(self):
        self.write_config([{"id": "always", "expect": "x", "command": "true"}])
        code, _ = self.run_cmd("--touches", "anything/at/all")
        self.assertEqual(code, 0)
        self.assertEqual([e["check_id"] for e in self.events()], ["always"])

    def test_only_selects_by_id(self):
        self.two_checks()
        code, _ = self.run_cmd("--only", "bad")
        self.assertEqual(code, 1)
        self.assertEqual([e["check_id"] for e in self.events()], ["bad"])

    def test_missing_config_is_unverified_exit_three(self):
        code, out = self.run_cmd()
        self.assertEqual(code, 3)
        self.assertIn("unverified", out)
        self.assertEqual(self.events(), [])

    def test_malformed_config_is_a_usage_error(self):
        self.write_config([{"id": "x", "command": "true"}])
        code, out = self.run_cmd()
        self.assertEqual(code, 2)
        self.assertIn("expect", out)

    def test_command_runs_from_the_project_root_with_the_check_id_in_env(self):
        self.write_config([{"id": "env", "expect": "env set",
                            "command": "test \"$PRODUCT_CHECK_ID\" = env && test -d runs"}])
        code, _ = self.run_cmd()
        self.assertEqual(code, 0)

    def test_timeout_is_an_error_not_a_hang(self):
        self.write_config([{"id": "slow", "expect": "fast", "command": "sleep 5"}])
        code, out = self.run_cmd("--timeout", "1")
        self.assertEqual(code, 1)
        self.assertEqual(self.events()[0]["result"], "error")
        self.assertIn("timed out", out)

    def test_list_marks_the_selected_checks(self):
        self.two_checks()
        code, out = self.run_cmd("--list", "--touches", "worker/x.ts")
        self.assertEqual(code, 0)
        self.assertIn("* bad", out)
        self.assertIn("  ok", out)
        self.assertEqual(self.events(), [])


if __name__ == "__main__":
    unittest.main()
