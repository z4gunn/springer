"""spgr-run-harness/scripts/run-unattended.py: the loop that runs fresh
sessions until the run completes or a human gate holds everything, sleeps
through usage limits, and stops a stuck run instead of burning a night."""

import contextlib
import datetime
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import SCRIPTS, RunStore, load_script

ru = load_script(SCRIPTS / "run-unattended.py")

# A stand-in for `claude -p`. Each call takes the next action from plan.json
# in the project and leaves what a harness session would leave.
FAKE = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
project = Path.cwd()
plan = json.loads((project / "plan.json").read_text())
n_path = project / "calls"
n = int(n_path.read_text()) if n_path.exists() else 0
n_path.write_text(str(n + 1))
(project / "argv.json").write_text(json.dumps(sys.argv[1:]))
(project / "env.json").write_text(json.dumps({"unattended": os.environ.get("SPRINGER_UNATTENDED")}))
action = plan[min(n, len(plan) - 1)]
run = project / "runs" / "r1"
def cycle(transition):
    k = len(list((run / "artifacts").glob("CYCLE-*.json"))) + 1
    obj = {"artifact_id": f"CYCLE-{k:04d}", "artifact_type": "pdca-cycle", "schema_version": "v1",
           "producing_agent": "spgr-agent-orchestrator", "timestamp": "2026-06-02T12:00:00Z",
           "parent_artifact_ref": None, "version": "v0.1-draft", "version_type": "draft",
           "confidence_map": {"cycle": "confirmed"}, "decision_log": [],
           "content": {"cycle_id": f"CYCLE-{k:04d}", "cycle_number": k, "run_id": "r1", "phase": "development",
                       "plan": {}, "do": {}, "check": {"verdict": "pass"},
                       "act": {"transition": transition}, "next_phase": "development"}}
    (run / "artifacts" / f"CYCLE-{k:04d}.json").write_text(json.dumps(obj))
def result(text, error=False):
    print(json.dumps({"type": "result", "subtype": "error" if error else "success", "is_error": error,
                      "result": text}))
if action == "cycle":
    cycle("advance"); result("one tick done")
elif action == "complete":
    cycle("complete"); result("run complete")
elif action == "limit":
    result("Claude usage limit reached. Your limit will reset at 5pm", error=True); sys.exit(1)
elif action == "dispatch":
    with open(run / "events.jsonl", "a") as fh:
        fh.write(json.dumps({"event": "agent_dispatched", "tool_use_id": "toolu_dead", "agent": "x"}) + "\n")
    cycle("advance"); result("died mid dispatch")
elif action == "error":
    print("boom", file=sys.stderr); sys.exit(1)
else:
    result("nothing to do")
'''


class LimitWaitTest(unittest.TestCase):
    def test_parses_epoch_clock_and_default(self):
        current = datetime.datetime(2026, 10, 24, 15, 0, tzinfo=datetime.timezone.utc)
        epoch = int(current.timestamp()) + 3600
        self.assertEqual(ru.limit_wait(f"Claude AI usage limit reached|{epoch}", current), 3600 + 120)
        wait = ru.limit_wait("5-hour limit reached, resets 3am", current)
        self.assertTrue(120 < wait <= 24 * 3600 + 120)
        self.assertEqual(ru.limit_wait("You've hit your limit", current), ru.DEFAULT_LIMIT_WAIT)
        self.assertIsNone(ru.limit_wait("all tests passed", current))


class DriveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        self.store = RunStore(self.project, run_id="r1", profile="saas", autonomy="autopilot")
        self.fake = self.project / "fake-claude"
        self.fake.write_text(FAKE)
        self.fake.chmod(self.fake.stat().st_mode | stat.S_IEXEC)
        self.slept = []
        self.saved = (ru.sleep, os.environ.get(ru.WEBHOOK_ENV))
        ru.sleep = self.slept.append
        os.environ.pop(ru.WEBHOOK_ENV, None)
        self.saved_which = ru.shutil.which
        ru.shutil.which = lambda name: None if name == "osascript" else self.saved_which(name)

    def tearDown(self):
        ru.sleep = self.saved[0]
        ru.shutil.which = self.saved_which
        if self.saved[1]:
            os.environ[ru.WEBHOOK_ENV] = self.saved[1]
        self.tmp.cleanup()

    def drive(self, plan, **kw):
        (self.project / "plan.json").write_text(json.dumps(plan))
        args = dict(max_sessions=10, max_hours=1, model=None)
        args.update(kw)
        with contextlib.redirect_stderr(io.StringIO()):
            return ru.drive("r1", self.project, args["model"], args["max_sessions"], args["max_hours"],
                            str(self.fake))

    def status(self):
        return (self.store.run_dir / "unattended-status.md").read_text()

    def sessions(self):
        return [json.loads(l) for l in (self.store.run_dir / "events.jsonl").read_text().splitlines()
                if '"unattended_session"' in l]

    def test_runs_sessions_until_complete(self):
        self.assertEqual(self.drive(["cycle", "cycle", "complete"]), 0)
        self.assertEqual((self.project / "calls").read_text(), "3")
        self.assertIn("run complete", self.status())
        argv = json.loads((self.project / "argv.json").read_text())
        self.assertIn("AskUserQuestion", argv[argv.index("--disallowedTools") + 1])
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "acceptEdits")
        self.assertEqual(json.loads((self.project / "env.json").read_text())["unattended"], "1")

    def test_usage_limit_sleeps_and_continues(self):
        self.assertEqual(self.drive(["cycle", "limit", "complete"]), 0)
        self.assertEqual(len(self.slept), 1)
        self.assertGreater(self.slept[0], 0)
        self.assertEqual([s["outcome"] for s in self.sessions()], ["ok", "usage-limit", "ok"])

    def test_a_gate_holding_all_work_stops_and_notifies(self):
        self.store.add_gate("HIL-0007", "pr-merge", holds=["all"])
        self.assertEqual(self.drive(["cycle"]), 0)
        self.assertFalse((self.project / "calls").exists())
        self.assertIn("HIL-0007", self.status())

    def test_a_gate_holding_some_work_does_not_stop_the_loop(self):
        self.store.add_gate("HIL-0008", "pr-merge", holds=["STORY-1"])
        self.assertEqual(self.drive(["cycle", "complete"]), 0)
        self.assertEqual((self.project / "calls").read_text(), "2")

    def test_dead_dispatches_are_abandoned_so_the_next_session_can_plan(self):
        self.assertEqual(self.drive(["dispatch", "complete"]), 0)
        events = (self.store.run_dir / "events.jsonl").read_text()
        self.assertIn('"agent_abandoned"', events)
        self.assertIn("toolu_dead", events)

    def test_no_progress_and_repeated_errors_stop_with_exit_one(self):
        self.assertEqual(self.drive(["idle"]), 1)
        self.assertIn("no progress", self.status())
        (self.project / "calls").unlink()
        self.assertEqual(self.drive(["error"]), 1)
        self.assertIn("errors", self.status())

    def test_session_cap(self):
        self.assertEqual(self.drive(["cycle"], max_sessions=2), 1)
        self.assertIn("cap", self.status())

    def test_slack_webhook_from_dotenv(self):
        (self.project / ".env").write_text(f"OTHER=1\n{ru.WEBHOOK_ENV}='https://hooks.example/x'\n")
        self.assertEqual(ru.read_env_value(self.project, ru.WEBHOOK_ENV), "https://hooks.example/x")
        sent = []

        class Resp:
            def read(self):
                return b"ok"
        saved = ru.urllib.request.urlopen
        ru.urllib.request.urlopen = lambda req, timeout=0: sent.append(json.loads(req.data)) or Resp()
        try:
            self.assertEqual(ru.notify(self.project, self.store.run_dir, "run complete", "3 cycles"), "slack")
        finally:
            ru.urllib.request.urlopen = saved
        self.assertIn("run complete", sent[0]["text"])

    def test_usage(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ru.main(["run-unattended.py"]), 2)
            self.assertEqual(ru.main(["run-unattended.py", "r1", "--bogus", "x"]), 2)
            self.assertEqual(ru.drive("missing", self.project, None, 1, 1, str(self.fake)), 2)


if __name__ == "__main__":
    unittest.main()
