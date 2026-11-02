"""The Claude Code provider, the mechanical Check, the orchestrator planner, the GitHub
source host, and onboard and doctor, each against a fake claude or gh on PATH, so the
suite spends no tokens and touches no account."""

import json
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

from harness_support import REPO, git_project

sys.path.insert(0, str(REPO / "harness"))

from springer_harness.check.mechanical import mechanical_check  # noqa: E402
from springer_harness.providers.claude_code import ClaudeCodeProvider, signal_from  # noqa: E402
from springer_harness.providers.coding_agent import SpawnRequest  # noqa: E402
from springer_harness.providers.github import GitHubSourceHost  # noqa: E402
from springer_harness.scheduler.orchestrator import OrchestratorPlanner  # noqa: E402
from springer_harness.scheduler.plan import Snapshot  # noqa: E402
from springer_harness import setup  # noqa: E402

FAKE_CLAUDE = r'''#!{python}
import json, os, sys
args = sys.argv[1:]
log = os.environ.get("FAKE_LOG")
if log:
    with open(log, "a") as fh:
        fh.write(json.dumps({{"args": args, "api_key": os.environ.get("ANTHROPIC_API_KEY")}}) + "\n")
if args[:2] == ["auth", "status"]:
    print(json.dumps({{"loggedIn": True, "authMethod": os.environ.get("FAKE_AUTH", "claude.ai"),
                      "subscriptionType": "max"}}))
    sys.exit(0)
if args == ["--version"]:
    print("9.9.9 (Claude Code)"); sys.exit(0)
fmt = args[args.index("--output-format") + 1]
if fmt == "json":
    print(json.dumps({{"type": "result", "is_error": False, "result": "ok", "total_cost_usd": 0.02,
                      "structured_output": json.load(open(os.environ["FAKE_PLAN"]))}}))
    sys.exit(0)
session = os.environ["SPRINGER_SESSION_DIR"]
def emit(e): print(json.dumps(e), flush=True)
emit({{"type": "system", "subtype": "init", "session_id": "real-1", "model": "claude-sonnet-x"}})
emit({{"type": "rate_limit_event", "rate_limit_info": {{"status": "allowed", "resetsAt": 1793640000,
      "unifiedWindows": {{"five_hour": {{"utilization": 0.42, "resetsAt": 1793640000, "status": "allowed"}}}}}}}})
emit({{"type": "assistant", "message": {{"usage": {{"input_tokens": 1000, "cache_read_input_tokens": 99000,
      "output_tokens": 50}}, "content": [{{"type": "tool_use", "name": "Edit"}}, {{"type": "text", "text": "Edited."}}]}}}})
mode = os.environ.get("FAKE_MODE", "pass")
if mode == "pass":
    json.dump({{"status": "pass", "outcome": "artifact", "detail": "wrote the PRD"}}, open(os.path.join(session, "result.json"), "w"))
elif mode == "handoff":
    open(os.path.join(session, "handoff.md"), "w").write("Continue at step 3.")
emit({{"type": "result", "subtype": "success", "is_error": mode == "limit", "total_cost_usd": 0.31,
      "result": "Claude AI usage limit reached|1793640000" if mode == "limit" else "DONE"}})
'''

FAKE_GH = r'''#!{python}
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write(json.dumps(args) + "\n")
if args[:2] == ["auth", "status"]:
    print("github.com\n  Logged in to github.com account octo (keyring)"); sys.exit(0)
if args[:2] == ["pr", "view"] and "state" in args:
    print(json.dumps({{"state": "MERGED"}})); sys.exit(0)
if args[:2] == ["pr", "view"] and "mergeCommit" in args:
    print(json.dumps({{"mergeCommit": {{"oid": "abc123"}}}})); sys.exit(0)
if args[:2] == ["pr", "diff"]:
    print("diff --git a/x b/x"); sys.exit(0)
sys.exit(0)
'''


def install(folder, name, body):
    path = Path(folder) / name
    path.write_text(body.format(python=sys.executable))
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


class FakeBinCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.claude = install(self.bin, "claude", FAKE_CLAUDE)
        install(self.bin, "gh", FAKE_GH)
        self.log = self.root / "calls.jsonl"
        env = {"PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", "FAKE_LOG": str(self.log),
               "ANTHROPIC_API_KEY": "sk-should-not-reach-a-session"}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def calls(self):
        return [json.loads(l) for l in self.log.read_text().splitlines()] if self.log.exists() else []


class ProviderTest(FakeBinCase):
    def request(self, mode="pass"):
        os.environ["FAKE_MODE"] = mode
        session_dir = self.root / "unit" / "sessions" / "S-0001"
        return SpawnRequest(unit_id="U-0001", session_id="S-0001", agent="spgr-agent-product-manager",
                            role_prompt_ref=".claude/agents/spgr-agent-product-manager.md", model_tier="opus",
                            brief="Write the PRD from docs/brief.md.", allowlist=(), mcp_config_ref=None, cwd=self.root,
                            session_dir=session_dir, env={"SPRINGER_SESSION_DIR": str(session_dir),
                                                          "SPRINGER_RUN_ID": "acme-1", "SPRINGER_PROJECT_DIR": str(self.root)})

    def finish(self, handle):
        deadline = time.time() + 10
        while handle.exit() is None and time.time() < deadline:
            time.sleep(0.05)
        return handle.exit()

    def test_a_session_runs_as_its_agent_on_the_subscription_and_streams(self):
        provider = ClaudeCodeProvider(str(self.claude))
        request = self.request()
        handle = provider.spawn(request)
        done = self.finish(handle)
        self.assertEqual((done.outcome, done.code), ("return", 0))
        call = self.calls()[-1]
        self.assertIsNone(call["api_key"], "a session never sees the API key")
        args = call["args"]
        self.assertEqual(args[args.index("--agent") + 1], "spgr-agent-product-manager")
        self.assertEqual(args[args.index("--model") + 1], "opus")
        self.assertIn("AskUserQuestion", args)

        brief = (request.session_dir / "brief.md").read_text()
        self.assertIn("Write the PRD", brief)
        self.assertIn("result.json", brief, "the brief carries the output contract")
        events = handle.poll()
        self.assertIn({"type": "tool_use", "name": "Edit"}, events)
        usage = handle.usage()
        self.assertEqual((usage.context_percent, usage.cost_usd), (50.0, 0.31))
        self.assertEqual(handle.provider_session_id, "real-1")
        self.assertEqual(provider.usage_signal(), {"used_fraction": 0.42, "resets_at": "2026-11-02T17:20:00Z"})
        self.assertEqual((request.session_dir / "return.txt").read_text(), "DONE")
        self.assertTrue((request.session_dir / "stream.jsonl").read_text().count("\n") >= 4)

    def test_the_project_allowlist_goes_in_as_flags(self):
        (self.root / ".claude").mkdir()
        (self.root / ".claude/settings.json").write_text(json.dumps(
            {"permissions": {"allow": ["Bash(pnpm test:*)"], "deny": ["Bash(git push --force:*)"]}}))
        args = ClaudeCodeProvider(str(self.claude)).command(self.request())
        self.assertEqual(args[args.index("--allowedTools") + 1], "Bash(pnpm test:*)")
        self.assertIn("Bash(git push --force:*)", args[args.index("--disallowedTools"):])

    def test_a_handoff_with_no_result_is_a_handoff(self):
        handle = ClaudeCodeProvider(str(self.claude)).spawn(self.request("handoff"))
        self.assertEqual(self.finish(handle).outcome, "handoff")

    def test_a_rejected_window_reads_as_full(self):
        self.assertEqual(signal_from({"status": "rejected", "resetsAt": 1793640000})["used_fraction"], 1.0)
        self.assertIsNone(signal_from({}))


class MechanicalCheckTest(FakeBinCase):
    def setUp(self):
        super().setUp()
        self.project = git_project(self.root / "acme")
        scripts = self.project / ".claude/skills/spgr-run-harness/scripts"
        scripts.mkdir(parents=True)
        for name in ("receipt.py", "classify-failure.py"):
            (scripts / name).write_text((REPO / "runtime/skills/spgr-run-harness/scripts" / name).read_text())
        self.session = self.root / "session"
        self.session.mkdir()
        self.run_dir = self.project / "runs" / "acme-1"
        (self.run_dir / "artifacts").mkdir(parents=True)

    def check(self):
        return mechanical_check(self.session, self.project, self.run_dir, self.project, "U-0001", time.time() - 60)

    def write(self, **result):
        (self.session / "result.json").write_text(json.dumps(result))

    def test_a_usage_limit_is_transient_whatever_the_session_said(self):
        (self.session / "return.txt").write_text("Claude AI usage limit reached|1793640000")
        self.assertEqual(self.check().failure_class, "transient")

    def test_no_result_is_classified_from_the_return(self):
        (self.session / "return.txt").write_text("Status: BLOCKED. The brief names no PRD.")
        result = self.check()
        self.assertEqual((result.status, result.failure_class), ("fail", "blocked"))
        self.assertIn("no result.json", result.detail)

    def test_a_pr_with_no_receipt_fails_as_a_defect(self):
        self.write(status="pass", outcome="pr", pr={"number": 3, "branch": "unit/U-0001", "base": "main"},
                   touched_paths=["apps/web/page.tsx"])
        result = self.check()
        self.assertEqual((result.status, result.failure_class), ("fail", "defect"))
        self.assertIn("receipts do not hold", result.detail)

    def test_a_docs_only_pr_needs_no_receipt(self):
        self.write(status="pass", outcome="pr", pr={"number": 3, "branch": "b", "base": "main"},
                   touched_paths=["docs/prd.md"])
        self.assertEqual(self.check().status, "pass")

    def test_an_artifact_that_fails_its_schema_fails_the_unit(self):
        (self.project / "schemas").mkdir()
        (self.project / "schemas/validate.py").write_text("import sys\nprint('missing field: title')\nsys.exit(1)\n")
        (self.run_dir / "artifacts" / "prd.json").write_text("{}")
        self.write(status="pass", outcome="artifact")
        result = self.check()
        self.assertEqual(result.failure_class, "defect")
        self.assertIn("prd.json", result.detail)


class OrchestratorTest(FakeBinCase):
    PLAN = {"done": False, "phase": "requirements", "next_phase": "direction", "rationale": "Start with the PRD.",
            "units": [{"key": "prd", "agent": "spgr-agent-product-manager", "expected_outcome": "a PRD",
                       "brief": "Read docs/brief.md.", "declared_paths": ["docs/"], "depends_on": [],
                       "risk_baseline": "L0", "model_tier": "opus"}], "gates": []}

    def setUp(self):
        super().setUp()
        self.project = self.root / "acme"
        (self.project / ".claude/agents").mkdir(parents=True)
        (self.project / ".claude/agents/spgr-agent-product-manager.md").write_text("---\n---\n")
        (self.project / "runs/acme-1").mkdir(parents=True)
        self.plan_file = self.root / "plan.json"
        os.environ["FAKE_PLAN"] = str(self.plan_file)
        self.planner = OrchestratorPlanner(self.project, "acme-1", "build", str(self.claude))

    def ask(self, snapshot=Snapshot(0, 0, 0, active=0)):
        self.assertIsNone(self.planner.next_batch(snapshot), "the first ask starts the call")
        deadline = time.time() + 10
        while time.time() < deadline:
            time.sleep(0.05)
            if not (self.planner._thread and self.planner._thread.is_alive()):
                return self.planner.next_batch(snapshot)
        self.fail("the plan call never finished")

    def test_the_orchestrator_names_the_batch(self):
        self.plan_file.write_text(json.dumps(self.PLAN))
        batch = self.ask()
        self.assertEqual([(u.key, u.agent, u.model_tier) for u in batch.units],
                         [("prd", "spgr-agent-product-manager", "opus")])
        args = self.calls()[-1]["args"]
        self.assertNotIn("--agent", args, "an agent's tool list would hide the structured output tool")
        self.assertIn("--json-schema", args)
        self.assertTrue((self.project / "runs/acme-1/plan/plan-001.json").exists())
        self.assertFalse(self.planner.finished())

    def test_nothing_is_asked_while_work_can_move(self):
        self.assertIsNone(self.planner.next_batch(Snapshot(1, 1, 0, active=1)))
        self.assertEqual(self.calls(), [])

    def test_an_empty_answer_is_not_asked_again_until_the_state_changes(self):
        self.plan_file.write_text(json.dumps({**self.PLAN, "units": []}))
        self.assertIsNone(self.ask())
        before = len(self.calls())
        self.assertIsNone(self.planner.next_batch(Snapshot(0, 0, 1, active=0)))
        time.sleep(0.2)
        self.assertEqual(len(self.calls()), before)

    def test_a_batch_naming_an_unknown_agent_is_refused_and_logged(self):
        self.plan_file.write_text(json.dumps({**self.PLAN, "units": [{**self.PLAN["units"][0], "agent": "nobody"}]}))
        self.assertIsNone(self.ask())
        error = json.loads((self.project / "runs/acme-1/plan/error-001.json").read_text())
        self.assertIn("nobody is not an agent", error["error"])

    def test_a_batch_written_as_text_is_read_with_defaults(self):
        from springer_harness.providers.claude_code import json_from_text
        from springer_harness.scheduler.orchestrator import normalize
        text = 'Here:\n```json\n{"units": [{"key": "prd", "agent": "a", "brief": "b"}], "done": false}\n```\nPRD first.'
        found = normalize(json_from_text(text), text)
        self.assertEqual((found["phase"], found["rationale"], found["units"][0]["model_tier"]),
                         ("planning", "PRD first.", "sonnet"))

    def test_done_with_no_units_finishes_the_run(self):
        self.plan_file.write_text(json.dumps({**self.PLAN, "done": True, "units": []}))
        self.ask()
        self.assertTrue(self.planner.finished())


class GitHubTest(FakeBinCase):
    def test_merge_reads_the_sha_and_retarget_and_state_go_through_gh(self):
        project = git_project(self.root / "acme")
        host = GitHubSourceHost(lambda slug: project)
        self.assertEqual(host.merge("acme", 7), "abc123")
        self.assertEqual(host.pr_state("acme", 7), "merged")
        host.retarget("acme", 8, "main")
        calls = [c for c in self.calls() if isinstance(c, list)]
        self.assertIn(["pr", "merge", "7", "--squash"], calls)
        self.assertIn(["pr", "edit", "8", "--base", "main"], calls)


class SetupTest(FakeBinCase):
    def test_doctor_passes_with_a_subscription_login_and_names_the_api_key(self):
        found = {f.name: f for f in setup.checks(dict(setup.DEFAULTS))}
        self.assertTrue(found["claude login"].ok)
        self.assertIn("subscription", found["claude login"].detail)
        self.assertIn("still run on the subscription", found["api key"].detail)
        self.assertTrue(found["gh login"].ok)

    def test_an_api_key_login_fails_the_check(self):
        os.environ["FAKE_AUTH"] = "api_key"
        self.addCleanup(os.environ.pop, "FAKE_AUTH", None)
        found = {f.name: f for f in setup.checks(dict(setup.DEFAULTS))}
        self.assertFalse(found["claude login"].ok)

    def test_onboard_saves_the_config_and_a_daemon_reads_it(self):
        home = self.root / "home"
        with mock.patch("springer_harness.cli.ensure_daemon", return_value={"port": 1}), \
                mock.patch("springer_harness.cli.stop_daemon"):
            self.assertEqual(setup.onboard(home, assume_yes=True), 0)
        self.assertEqual(setup.load_config(home)["provider"], "claude-code")
        from springer_harness.cli import build_daemon
        daemon = build_daemon(home)
        self.assertEqual((daemon.provider.name, daemon.source_host.name), ("claude-code", "github"))

    def test_without_onboarding_the_daemon_runs_the_mock(self):
        from springer_harness.cli import build_daemon
        self.assertEqual(build_daemon(self.root / "fresh").provider.name, "mock")

    def test_doctor_removes_a_stale_daemon_record(self):
        home = self.root / "home"
        home.mkdir()
        (home / "daemon.json").write_text(json.dumps({"port": 1, "pid": 999999}))
        self.assertEqual(setup.repair(home, {}), ["removed a stale daemon record"])


if __name__ == "__main__":
    unittest.main()
