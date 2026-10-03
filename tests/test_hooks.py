"""The two instance hooks, run as subprocesses with the stdin payload Claude
Code sends. log-agent-events.py feeds the dashboard and the un-joined
dispatch barrier. session-usage.py is the main-session sensor."""

import json
import tempfile
import unittest
from pathlib import Path

from helpers import REPO, RunStore, read_events, run_hook

REVIEWER = REPO / ".claude" / "agents" / "spgr-agent-code-reviewer.md"


def dispatch_payload(hook_event, project, tool_use_id="tu-1", agent="spgr-agent-code-reviewer",
                     description="review runs/demo/ PR", background=False, response=None,
                     model=None, prompt="read runs/demo/artifacts/prd.json"):
    tool_input = {"subagent_type": agent, "description": description, "prompt": prompt}
    if background:
        tool_input["run_in_background"] = True
    if model:
        tool_input["model"] = model
    payload = {"hook_event_name": hook_event, "session_id": "s", "tool_use_id": tool_use_id,
               "cwd": str(project), "tool_input": tool_input}
    if response is not None:
        payload["tool_response"] = response
    return payload


class LogAgentEventsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        self.store = RunStore(self.project)
        self.store.set_state()
        agents = self.project / ".claude" / "agents"
        agents.mkdir(parents=True)
        (agents / "spgr-agent-code-reviewer.md").write_text(REVIEWER.read_text())

    def tearDown(self):
        self.tmp.cleanup()

    def test_dispatch_and_completion_are_logged_with_model_and_metrics(self):
        code, out, err = run_hook("log-agent-events.py", dispatch_payload("PreToolUse", self.project), self.project)
        self.assertEqual(code, 0)
        response = {"totalTokens": 1200, "usage": {"input_tokens": 1000, "output_tokens": 200},
                    "totalDurationMs": 5000}
        run_hook("log-agent-events.py", dispatch_payload("PostToolUse", self.project, response=response), self.project)
        events = read_events(self.store.run_dir)
        self.assertEqual([e["event"] for e in events], ["agent_dispatched", "agent_completed"])
        self.assertEqual(events[0]["model"], "opus")
        self.assertEqual(events[1]["metrics"], {"total_tokens": 1200, "input_tokens": 1000,
                                                 "output_tokens": 200, "duration_ms": 5000})
        self.assertEqual(events[1]["tool_use_id"], "tu-1")

    def test_per_dispatch_model_override_wins(self):
        run_hook("log-agent-events.py", dispatch_payload("PreToolUse", self.project, model="haiku"), self.project)
        self.assertEqual(read_events(self.store.run_dir)[0]["model"], "haiku")

    def test_unknown_agent_has_no_model(self):
        run_hook("log-agent-events.py", dispatch_payload("PreToolUse", self.project, agent="nobody"), self.project)
        self.assertIsNone(read_events(self.store.run_dir)[0]["model"])

    def test_background_dispatch_is_logged_as_backgrounded_with_agent_id(self):
        response = {"content": [{"text": "Async agent launched. agentId: ab12cd"}]}
        run_hook("log-agent-events.py",
                 dispatch_payload("PostToolUse", self.project, background=True, response=response),
                 self.project)
        ev = read_events(self.store.run_dir)[0]
        self.assertEqual(ev["event"], "agent_backgrounded")
        self.assertEqual(ev["agent_id"], "ab12cd")
        self.assertNotIn("metrics", ev)

    def test_subagent_stop_is_logged(self):
        payload = {"hook_event_name": "SubagentStop", "session_id": "s", "agent_id": "ab12cd",
                   "cwd": str(self.project), "agent_transcript_path": "/x/y.jsonl"}
        run_hook("log-agent-events.py", payload, self.project)
        ev = read_events(self.store.run_dir)[0]
        self.assertEqual(ev["event"], "agent_stopped")
        self.assertEqual(ev["agent_id"], "ab12cd")
        self.assertNotIn("model", ev)

    def test_unattributable_event_goes_to_the_dashboard_feed(self):
        (self.store.run_dir / "run-state.json").unlink()
        run_hook("log-agent-events.py",
                 dispatch_payload("PreToolUse", self.project, description="no run here",
                                  prompt="no run path here either"), self.project)
        self.assertEqual(read_events(self.store.run_dir), [])
        self.assertEqual(len(read_events(self.project / "runs" / "_dashboard")), 1)

    def test_hook_never_fails_the_tool_call(self):
        code, _, _ = run_hook("log-agent-events.py", {"hook_event_name": "PreToolUse"}, self.project)
        self.assertEqual(code, 0)


class SessionUsageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        (self.project / "runs").mkdir()
        self.transcript = self.project / "transcript.jsonl"
        self.transcript.write_text("")

    def tearDown(self):
        self.tmp.cleanup()

    def append(self, inp, read, write, out, model="claude-sonnet-5-5", sidechain=False, kind="assistant"):
        entry = {"type": kind, "isSidechain": sidechain,
                 "message": {"model": model, "usage": {
                     "input_tokens": inp, "cache_read_input_tokens": read,
                     "cache_creation_input_tokens": write, "output_tokens": out}}}
        with open(self.transcript, "a") as fh:
            fh.write(json.dumps(entry) + "\n")

    def call(self, event="PostToolUse"):
        payload = {"hook_event_name": event, "session_id": "sess", "cwd": str(self.project),
                   "transcript_path": str(self.transcript)}
        code, out, _ = run_hook("session-usage.py", payload, self.project)
        self.assertEqual(code, 0)
        return json.loads(out) if out.strip() else None

    def state(self):
        return json.loads((self.project / "runs" / "_dashboard" / "sessions" / "sess.json").read_text())

    def test_sums_assistant_usage_and_skips_sidechains(self):
        self.append(100, 50_000, 20_000, 1_500)
        self.append(5, 500_000, 0, 900, sidechain=True)
        self.append(0, 0, 0, 0, kind="user")
        self.assertIsNone(self.call())
        s = self.state()
        self.assertEqual(s["context_tokens"], 70_100)
        self.assertEqual(s["output_tokens"], 1_500)
        self.assertEqual(s["turns"], 1)
        self.assertEqual(s["model"], "claude-sonnet-5-5")
        self.assertEqual(s["window"], 1_000_000)

    def test_reads_incrementally_from_the_last_offset(self):
        self.append(10, 1000, 0, 100)
        self.call()
        first_offset = self.state()["offset"]
        self.append(10, 2000, 0, 100)
        self.call()
        s = self.state()
        self.assertGreater(s["offset"], first_offset)
        self.assertEqual(s["turns"], 2)
        self.assertEqual(s["output_tokens"], 200)

    def test_advisory_then_critical_each_fire_once(self):
        self.append(10, 640_000, 12_000, 2_200)
        out = self.call()
        self.assertIn("60 percent", out["hookSpecificOutput"]["additionalContext"])
        self.append(10, 650_000, 0, 10)
        self.assertIsNone(self.call())
        self.append(10, 830_000, 1_000, 300)
        out = self.call()
        self.assertIn("80 percent", out["hookSpecificOutput"]["additionalContext"])
        self.append(10, 840_000, 0, 10)
        self.assertIsNone(self.call())
        self.assertEqual(self.state()["warned"], ["advisory", "critical"])

    def test_stop_event_records_but_never_warns(self):
        self.append(10, 900_000, 0, 10)
        self.assertIsNone(self.call(event="Stop"))
        self.assertEqual(self.state()["context_tokens"], 900_010)
        self.assertEqual(self.state().get("warned", []), [])

    def test_haiku_window_is_200k(self):
        self.append(10, 150_000, 0, 10, model="claude-haiku-4-5")
        out = self.call()
        self.assertEqual(self.state()["window"], 200_000)
        self.assertIn("60 percent", out["hookSpecificOutput"]["additionalContext"])

    def test_rewritten_transcript_resets_the_sums(self):
        self.append(10, 1000, 0, 100)
        self.append(10, 1000, 0, 100)
        self.call()
        self.transcript.write_text("")
        self.append(10, 500, 0, 7)
        self.call()
        s = self.state()
        self.assertEqual(s["turns"], 1)
        self.assertEqual(s["output_tokens"], 7)

    def test_partial_last_line_is_left_for_next_time(self):
        self.append(10, 1000, 0, 100)
        with open(self.transcript, "a") as fh:
            fh.write('{"type":"assistant","message":{"usage":{"output_tokens":5')
        self.call()
        self.assertEqual(self.state()["turns"], 1)

    def test_missing_transcript_is_a_noop(self):
        payload = {"hook_event_name": "PostToolUse", "session_id": "sess", "cwd": str(self.project),
                   "transcript_path": str(self.project / "nope.jsonl")}
        code, out, _ = run_hook("session-usage.py", payload, self.project)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
