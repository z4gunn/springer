"""The Claude Code provider, the mechanical Check, the orchestrator planner, the GitHub
source host, and onboard and doctor, each against a fake claude or gh on PATH, so the
suite spends no tokens and touches no account."""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

from harness_support import HAVE_JSONSCHEMA, REPO, git_project

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
if args[:2] == ["pr", "view"] and "mergeable" in args:
    print(json.dumps({{"mergeable": "CONFLICTING"}})); sys.exit(0)
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
        self.assertIn("including a decision-log", brief, "a session may amend its own artifacts in the run store")
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

    def test_a_directory_prefix_rule_becomes_one_rule_per_script(self):
        """Claude Code matches a prefix rule on whole words, so a directory prefix never
        matched a script inside it, and every receipt.py run was denied."""
        scripts = self.root / ".claude/skills/spgr-run-harness/scripts"
        scripts.mkdir(parents=True)
        for name in ("receipt.py", "classify-failure.py"):
            (scripts / name).write_text("")
        (self.root / ".claude/settings.json").write_text(json.dumps({"permissions": {"allow": [
            "Bash(python3 .claude/skills/spgr-run-harness/scripts/:*)", "Bash(npm:*)"]}}))
        from springer_harness.providers.claude_code import permissions
        allow, _ = permissions(self.root)
        self.assertEqual(allow, ["Bash(python3 .claude/skills/spgr-run-harness/scripts/classify-failure.py:*)",
                                 "Bash(python3 .claude/skills/spgr-run-harness/scripts/receipt.py:*)", "Bash(npm:*)"])

    def test_a_handoff_with_no_result_is_a_handoff(self):
        handle = ClaudeCodeProvider(str(self.claude)).spawn(self.request("handoff"))
        self.assertEqual(self.finish(handle).outcome, "handoff")

    def test_a_rejected_window_reads_as_full(self):
        self.assertEqual(signal_from({"status": "rejected", "resetsAt": 1793640000})["used_fraction"], 1.0)
        self.assertIsNone(signal_from({}))


class CostEstimateTest(unittest.TestCase):
    def test_a_running_session_shows_a_list_price_estimate(self):
        from springer_harness.providers.claude_code import estimate_cost
        usage = {"input_tokens": 1_000_000, "output_tokens": 100_000, "cache_read_input_tokens": 1_000_000}
        self.assertAlmostEqual(estimate_cost("claude-sonnet-5-5", usage), 2.0 + 1.0 + 0.2)
        self.assertAlmostEqual(estimate_cost("claude-haiku-5-5", {"output_tokens": 1_000_000}), 0.5)
        self.assertAlmostEqual(estimate_cost(None, {"input_tokens": 1_000_000}), 4.0, msg="unknown prices as opus")


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

    def check(self, gating=None):
        return mechanical_check(self.session, self.project, self.run_dir, self.project, "U-0001", time.time() - 60,
                                gating=gating)

    PR = {"status": "pass", "outcome": "pr", "pr": {"number": 3, "branch": "unit/U-0001", "base": "main"},
          "touched_paths": ["src/app.ts"]}

    def test_the_harness_runs_the_gating_commands_itself_at_the_head(self):
        """The reference run's retries were receipts a session took before a later commit,
        and checks recorded as tests. The harness now runs the unit's commands itself,
        so a session that wrote no receipt at all passes when its code does."""
        self.write(**self.PR)
        gating = [{"name": "unit", "command": "python3 -c \"print('Ran 3 tests')\"", "kind": "test"},
                  {"name": "lint", "command": "python3 -c \"print('clean')\"", "kind": "check"},
                  {"name": "parity", "command": "python3 -c \"print('equal')\"", "kind": "product"}]
        self.assertEqual(self.check(gating).status, "pass")
        receipt = json.loads((self.session / "check" / "receipts" / "unit.json").read_text())
        head = subprocess.run(["git", "-C", str(self.project), "rev-parse", "HEAD"], capture_output=True,
                              text=True).stdout.strip()
        self.assertEqual((receipt["tests_ran"], receipt["head"]), (3, head))

    def test_a_failing_gating_command_is_a_defect_that_names_it_and_its_output(self):
        self.write(**self.PR)
        gating = [{"name": "lint", "command": "python3 -c \"import sys; print('rule no-floating'); sys.exit(3)\"",
                   "kind": "check"}]
        result = self.check(gating)
        self.assertEqual((result.status, result.failure_class), ("fail", "defect"))
        for needle in ("gating command lint", "failed with exit 3", "rule no-floating"):
            self.assertIn(needle, result.detail)

    def test_an_unreadable_count_on_exit_0_holds_the_merge_instead_of_a_retry(self):
        """The polish run's one retry: a passing self-test whose output the planner's
        count_regex did not match. The command's shape is the plan's, so the session
        is not sent back. The pass is raised to L2, so a person sees why at the merge."""
        self.write(**self.PR)
        result = self.check([{"name": "unit", "command": "python3 -c \"print('all good')\"", "kind": "test"}])
        self.assertEqual((result.status, result.raised_level), ("pass", "L2"))
        self.assertIn("printed no test count", result.findings[-1]["detail"])
        failed = self.check([{"name": "unit", "command": "python3 -c \"import sys; print('x'); sys.exit(1)\"",
                              "kind": "test"}])
        self.assertEqual((failed.status, failed.failure_class), ("fail", "defect"))
        zero = self.check([{"name": "unit", "command": "python3 -c \"print('Ran 0 tests')\"", "kind": "test"}])
        self.assertIn("ran no tests", zero.detail)
        per_line = self.check([{"name": "unit", "command": "python3 -c \"print('PASS a\\nPASS b')\"",
                                "kind": "test", "count_regex": r"(\d+) fixtures"}])
        self.assertEqual((per_line.status, per_line.raised_level), ("pass", None))
        counted = self.check([{"name": "unit", "command": "python3 -c \"print('ok 7 checks')\"", "kind": "test",
                               "count_regex": r"ok (\d+) checks"}])
        self.assertEqual(counted.status, "pass")

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

    def test_a_unit_names_the_stories_it_builds(self):
        unit = {**self.PLAN["units"][0], "story_ids": ["STORY-2026-001"]}
        self.plan_file.write_text(json.dumps({**self.PLAN, "units": [unit]}))
        self.assertEqual(self.ask().units[0].story_ids, ("STORY-2026-001",))
        self.plan_file.write_text(json.dumps(self.PLAN))

    def test_the_prompt_lets_work_stack_on_an_open_pr(self):
        from springer_harness.scheduler.orchestrator import PROMPT
        self.assertIn("depends_on its key", PROMPT)
        self.assertIn("starts from the open PR's branch", PROMPT)

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

    def test_a_build_unit_without_a_test_command_is_refused_and_the_next_ask_says_why(self):
        """The reference run's scaffold had no test runner, so its unit failed Check twice.
        The plan is refused instead, and the planner reads why when it is asked again."""
        (self.project / ".claude/agents/spgr-agent-frontend-developer.md").write_text("---\n---\n")
        build = {**self.PLAN["units"][0], "key": "skeleton", "agent": "spgr-agent-frontend-developer",
                 "gating_commands": [{"name": "build", "command": "npm run build", "kind": "check"}]}
        self.plan_file.write_text(json.dumps({**self.PLAN, "units": [build]}))
        self.assertIsNone(self.ask())
        error = json.loads((self.project / "runs/acme-1/plan/error-001.json").read_text())
        self.assertIn("names no test gating command", error["error"])
        fixed = {**build, "gating_commands": build["gating_commands"] + [
            {"name": "unit", "command": "npm test", "kind": "test"}]}
        self.plan_file.write_text(json.dumps({**self.PLAN, "units": [fixed]}))
        self.planner._error_at = 0
        batch = self.ask()
        self.assertEqual([g["name"] for g in batch.units[0].gating_commands], ["build", "unit"])
        prompt = " ".join(self.calls()[-1]["args"])
        self.assertIn("Your last answer was refused", prompt)
        self.assertIn("names no test gating command", prompt)

    def test_a_gating_command_needs_a_kebab_name_a_command_and_a_kind(self):
        for bad in ({"name": "Unit Tests", "command": "npm test", "kind": "test"},
                    {"name": "unit", "command": "", "kind": "test"},
                    {"name": "unit", "command": "npm test", "kind": "suite"}):
            with self.subTest(bad):
                output = {**self.PLAN, "units": [{**self.PLAN["units"][0], "gating_commands": [bad]}]}
                problems = self.planner.problems(output, {"keys_used": {}})
                self.assertTrue(any("gating command" in p for p in problems), problems)

    def test_a_batch_written_as_text_is_read_with_defaults(self):
        from springer_harness.providers.claude_code import json_from_text
        from springer_harness.scheduler.orchestrator import normalize
        text = 'Here:\n```json\n{"units": [{"key": "prd", "agent": "a", "brief": "b"}], "done": false}\n```\nPRD first.'
        found = normalize(json_from_text(text), text)
        self.assertEqual((found["phase"], found["rationale"], found["units"][0]["model_tier"]),
                         ("planning", "PRD first.", "sonnet"))

    def test_a_gate_may_name_work_not_planned_yet(self):
        gate = {"checkpoint_type": "direction-review", "prompt": "Pick a direction.", "holds": ["skeleton"],
                "options": [{"option": "accept", "consequence": "The skeleton is planned next."}]}
        self.plan_file.write_text(json.dumps({**self.PLAN, "units": [], "gates": [gate]}))
        batch = self.ask()
        self.assertEqual([(g.checkpoint_type, g.holds) for g in batch.gates], [("direction-review", ())])

    def test_done_with_no_units_finishes_the_run(self):
        self.plan_file.write_text(json.dumps({**self.PLAN, "done": True, "units": []}))
        self.ask()
        self.assertTrue(self.planner.finished())


class RestackTest(unittest.TestCase):
    """A stacked branch keeps only its own commits after its parent is squash-merged."""

    ENV = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.project = git_project(root / "acme")
        from springer_harness.scheduler.worktrees import Worktrees
        self.trees = Worktrees(root / "home", "acme", self.project)

    def git(self, cwd, *args):
        return subprocess.run(["git", "-C", str(cwd), *self.ENV, *args], capture_output=True, text=True)

    def commit(self, cwd, files):
        for rel, text in files.items():
            (cwd / rel).write_text(text)
        self.git(cwd, "add", "-A")
        self.git(cwd, "commit", "-qm", "work")

    def test_a_ruling_reaches_every_worktree_and_a_withdrawn_one_leaves(self):
        """The hook reads runs/_config-unlock.json from the session's own tree, and git
        does not carry the run store, so a ruling the human made once reached no unit."""
        self.commit(self.project, {"f.txt": "a\n"})
        rulings = self.project / "runs" / "_config-unlock.json"
        rulings.parent.mkdir(parents=True)
        rulings.write_text('{"paths": [{"path": "tsconfig.json", "reason": "ruled at G-0002"}]}')
        tree, _ = self.trees.claim("U-0001", "main")
        self.assertEqual((tree / "runs" / "_config-unlock.json").read_text(), rulings.read_text())
        rulings.write_text('{"paths": []}')
        tree, _ = self.trees.claim("U-0001", "main")
        self.assertEqual((tree / "runs" / "_config-unlock.json").read_text(), '{"paths": []}', "a retry reads the latest")
        rulings.unlink()
        tree, _ = self.trees.claim("U-0001", "main")
        self.assertFalse((tree / "runs" / "_config-unlock.json").exists())

    def test_a_worktree_gets_the_project_node_modules_when_the_lockfile_matches(self):
        """git carries no node_modules, so every session of a polish run either ran npm ci
        or failed its checks with tsc not found and was redispatched."""
        self.commit(self.project, {".gitignore": "node_modules/\n", "package-lock.json": '{"v": 1}\n'})
        (self.project / "node_modules" / ".bin").mkdir(parents=True)
        (self.project / "node_modules" / ".bin" / "tsc").write_text("#!/bin/sh\n")
        tree, _ = self.trees.claim("U-0001", "main")
        self.assertTrue((tree / "node_modules" / ".bin" / "tsc").is_file())
        self.assertFalse((tree / "node_modules").is_symlink(), "a copy the unit can change without touching the person's")
        self.assertEqual(self.git(tree, "status", "--porcelain").stdout, "")

    def test_a_different_lockfile_leaves_the_install_to_the_session(self):
        self.commit(self.project, {".gitignore": "node_modules/\n", "package-lock.json": '{"v": 1}\n'})
        (self.project / "node_modules").mkdir()
        self.git(self.project, "switch", "-qc", "deps")
        self.commit(self.project, {"package-lock.json": '{"v": 2}\n'})
        self.git(self.project, "switch", "-q", "main")
        tree, _ = self.trees.claim("U-0001", "deps")
        self.assertFalse((tree / "node_modules").exists())

    def test_the_carried_rulings_never_keep_a_worktree_but_a_session_s_work_does(self):
        """Every reference-run worktree was kept because the rulings copy sat untracked in it."""
        self.commit(self.project, {"f.txt": "a\n"})
        rulings = self.project / "runs" / "_config-unlock.json"
        rulings.parent.mkdir(parents=True)
        rulings.write_text('{"paths": []}')
        tree, _ = self.trees.claim("U-0001", "main")
        self.assertIsNone(self.trees.release("U-0001"))
        self.assertFalse(tree.exists())
        tree, _ = self.trees.claim("U-0002", "main")
        (tree / "notes.txt").write_text("half done")
        self.assertIsNotNone(self.trees.release("U-0002"), "a session's loose work keeps its worktree")
        self.assertTrue(tree.exists())

    def test_a_merged_branch_is_deleted_here_and_on_origin(self):
        origin = Path(self.tmp.name) / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
        self.git(self.project, "remote", "add", "origin", str(origin))
        self.git(self.project, "branch", "unit/U-0001")
        self.git(self.project, "push", "-q", "origin", "main", "unit/U-0001")
        self.assertEqual(self.trees.delete_branch("unit/U-0001"), ["unit/U-0001", "origin/unit/U-0001"])
        self.assertEqual(self.git(self.project, "ls-remote", "--heads", "origin", "unit/U-0001").stdout, "")
        self.assertEqual(self.trees.delete_branch("unit/U-0001"), [], "a second pass finds nothing")

    def test_the_default_branch_fast_forwards_from_origin_when_clean(self):
        origin = Path(self.tmp.name) / "origin.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(self.project), str(origin)], check=True)
        self.git(self.project, "remote", "add", "origin", str(origin))
        other = Path(self.tmp.name) / "other"
        subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True)
        self.commit(other, {"pushed.txt": "from another machine\n"})
        self.git(other, "push", "-q", "origin", "main")
        (self.project / "README.md").write_text("edited\n")
        self.assertIn("uncommitted", self.trees.sync_default())
        self.git(self.project, "checkout", "-q", "--", "README.md")
        (self.project / "runs").mkdir(exist_ok=True)
        (self.project / "runs" / "loose.json").write_text("{}")
        self.assertIsNone(self.trees.sync_default(), "the run store does not block it")
        self.assertTrue((self.project / "pushed.txt").exists())

    def test_each_run_names_its_own_branches_and_worktrees(self):
        """Unit ids restart at U-0001 in every run, and a later run's U-0001 shared the
        earlier run's branch and worktree."""
        from springer_harness.scheduler.worktrees import Worktrees
        root = Path(self.tmp.name)
        first = Worktrees(root / "home", "acme", self.project, "acme-1")
        second = Worktrees(root / "home", "acme", self.project, "acme-2")
        a, _ = first.claim("U-0001", "main")
        self.commit(a, {"one.txt": "first run\n"})
        b, _ = second.claim("U-0001", "main")
        self.assertNotEqual(a, b)
        self.assertEqual((first.branch("U-0001"), second.branch("U-0001")), ("unit/acme-1/U-0001", "unit/acme-2/U-0001"))
        self.assertFalse((b / "one.txt").exists(), "the second run starts from main, not the first run's branch")
        self.assertEqual(first.claimed(), ["U-0001"])

    @unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed in this interpreter")
    def test_a_run_folder_links_the_project_venv(self):
        """validate.py looks for .venv in a worktree's parent, which is now the run folder."""
        from springer_harness.scheduler.worktrees import Worktrees
        trees = Worktrees(Path(self.tmp.name) / "home", "acme", self.project, "acme-1")
        (trees.base / ".venv" / "bin").mkdir(parents=True)
        (trees.base / ".venv" / "bin" / "python").symlink_to(sys.executable)
        self.assertIsNone(trees.ensure_venv())
        self.assertEqual((trees.root / ".venv").resolve(), (trees.base / ".venv").resolve())

    def test_a_run_begun_on_the_old_names_keeps_them(self):
        from springer_harness.daemon import _legacy_names
        units = self.project / "runs" / "acme-1" / "units" / "U-0001"
        units.mkdir(parents=True)
        (units / "state.json").write_text('{"pr": {"branch": "unit/U-0001"}}')
        self.assertTrue(_legacy_names(self.project, "acme-1"))
        self.assertFalse(_legacy_names(self.project, "acme-2"))

    def test_a_stacked_branch_merges_cleanly_after_its_parent_was_squashed(self):
        self.commit(self.project, {"f.txt": "a\nb\n"})
        parent, _ = self.trees.claim("U-0001", "main")
        self.commit(parent, {"f.txt": "A\nb\n"})
        child, _ = self.trees.claim("U-0002", "unit/U-0001")
        self.commit(child, {"f.txt": "A\nB\n", "g.txt": "child"})
        self.git(self.project, "merge", "--squash", "unit/U-0001")
        self.git(self.project, "commit", "-qm", "squash of U-0001")
        probe = self.git(self.project, "merge-tree", "--write-tree", "main", "unit/U-0002")
        self.assertNotEqual(probe.returncode, 0, "without a restack the squash conflicts")
        self.trees.release("U-0002")
        self.assertIsNone(self.trees.restack("unit/U-0002", "unit/U-0001", "main"))
        self.assertEqual(self.git(self.project, "merge", "--no-edit", "unit/U-0002").returncode, 0)
        self.assertEqual(((self.project / "f.txt").read_text(), (self.project / "g.txt").read_text()),
                         ("A\nB\n", "child"))
        self.assertEqual(self.trees.restack("unit/U-0002", "unit/U-0001", "main"), "nothing to restack")

    def test_a_restack_that_conflicts_leaves_the_branch_where_it_was(self):
        self.commit(self.project, {"f.txt": "a\n"})
        parent, _ = self.trees.claim("U-0001", "main")
        self.commit(parent, {"f.txt": "parent\n"})
        child, _ = self.trees.claim("U-0002", "unit/U-0001")
        self.commit(child, {"f.txt": "child\n"})
        self.commit(self.project, {"f.txt": "main moved\n"})
        before = self.git(self.project, "rev-parse", "unit/U-0002").stdout
        self.trees.release("U-0002")
        self.assertIn("CONFLICT", self.trees.restack("unit/U-0002", "unit/U-0001", "main"))
        self.assertEqual(self.git(self.project, "rev-parse", "unit/U-0002").stdout, before)
        self.assertEqual([p.name for p in self.trees.root.iterdir() if p.name.startswith("_restack")], [])


class LocalHostTest(unittest.TestCase):
    """The default source host: changes merge off the project checkout, then main is pushed."""

    ENV = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = git_project(self.root / "acme")
        from springer_harness.providers.local import LocalSourceHost
        from springer_harness.scheduler.worktrees import Worktrees
        self.host = LocalSourceHost(lambda slug: self.project, self.root / "home" / "changes")
        self.trees = Worktrees(self.root / "home", "acme", self.project)

    def git(self, cwd, *args):
        return subprocess.run(["git", "-C", str(cwd), *self.ENV, *args], capture_output=True, text=True)

    def unit(self, unit_id, files, base="main"):
        path, branch = self.trees.claim(unit_id, base)
        for rel, text in files.items():
            (path / rel).write_text(text)
        self.git(path, "add", "-A")
        self.git(path, "commit", "-qm", f"{unit_id} work")
        return branch

    def test_a_change_merges_with_a_merge_commit_and_main_is_pushed(self):
        remote = self.root / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
        self.git(self.project, "remote", "add", "origin", str(remote))
        branch = self.unit("U-0001", {"app.ts": "one"})
        number = self.host.open("acme", branch, "main", "the counter")
        self.assertEqual(self.host.open("acme", branch, "main"), number, "a retry reuses its change")
        self.assertIn("app.ts", self.host.diff("acme", number))
        self.assertEqual(self.host.mergeable("acme", number), "mergeable")
        sha = self.host.merge("acme", number)
        self.assertEqual(self.host.pr_state("acme", number), "merged")
        parents = self.git(self.project, "rev-list", "--parents", "-n", "1", sha).stdout.split()
        self.assertEqual(len(parents), 3, "a merge commit has two parents")
        self.assertEqual(self.git(remote, "rev-parse", "main").stdout.strip(), sha)

    def test_a_stacked_change_merges_after_its_parent_with_no_restack(self):
        parent = self.unit("U-0001", {"f.txt": "A\nb\n"})
        child = self.unit("U-0002", {"f.txt": "A\nB\n"}, base=parent)
        first, second = self.host.open("acme", parent, "main"), self.host.open("acme", child, parent)
        self.host.merge("acme", first)
        self.host.retarget("acme", second, "main")
        self.assertEqual(self.host.mergeable("acme", second), "mergeable")
        self.host.merge("acme", second)
        self.assertEqual((self.project / "f.txt").read_text(), "A\nB\n")

    def test_a_conflict_is_refused_and_leaves_main_alone(self):
        from springer_harness.providers.local import LocalMergeError
        branch = self.unit("U-0001", {"f.txt": "unit"})
        (self.project / "f.txt").write_text("main")
        self.git(self.project, "add", "-A")
        self.git(self.project, "commit", "-qm", "main moved")
        number = self.host.open("acme", branch, "main")
        self.assertEqual(self.host.mergeable("acme", number), "conflicting")
        before = self.git(self.project, "rev-parse", "HEAD").stdout
        with self.assertRaises(LocalMergeError):
            self.host.merge("acme", number)
        self.assertEqual(self.git(self.project, "rev-parse", "HEAD").stdout, before)
        self.assertEqual(self.git(self.project, "status", "--porcelain").stdout, "")

    def test_a_persons_unrelated_edit_does_not_refuse_the_merge_and_is_kept(self):
        """The reference run's merges were refused for a modified run log and an
        uncommitted brief. The merge is made off the checkout, and git keeps the edit."""
        branch = self.unit("U-0001", {"app.ts": "one"})
        number = self.host.open("acme", branch, "main")
        (self.project / "notes.md").write_text("a person's edit")
        sha = self.host.merge("acme", number)
        self.assertEqual(self.git(self.project, "rev-parse", "HEAD").stdout.strip(), sha)
        self.assertEqual((self.project / "app.ts").read_text(), "one")
        self.assertEqual((self.project / "notes.md").read_text(), "a person's edit")
        self.assertEqual(self.git(self.project, "status", "--porcelain").stdout, "?? notes.md\n")

    def test_an_edit_the_merge_would_overwrite_is_refused_and_kept(self):
        from springer_harness.providers.local import LocalMergeError
        (self.project / "app.ts").write_text("zero")
        self.git(self.project, "add", "-A")
        self.git(self.project, "commit", "-qm", "app")
        branch = self.unit("U-0001", {"app.ts": "one"})
        number = self.host.open("acme", branch, "main")
        before = self.git(self.project, "rev-parse", "HEAD").stdout
        (self.project / "app.ts").write_text("a person's edit")
        with self.assertRaisesRegex(LocalMergeError, "overwrite uncommitted work"):
            self.host.merge("acme", number)
        self.assertEqual(self.git(self.project, "rev-parse", "HEAD").stdout, before)
        self.assertEqual((self.project / "app.ts").read_text(), "a person's edit")

    def test_a_checkout_on_another_branch_does_not_refuse_the_merge(self):
        branch = self.unit("U-0001", {"app.ts": "one"})
        number = self.host.open("acme", branch, "main")
        self.git(self.project, "checkout", "-q", "-b", "experiment")
        sha = self.host.merge("acme", number)
        self.assertEqual(self.git(self.project, "rev-parse", "main").stdout.strip(), sha)
        self.assertEqual(self.git(self.project, "symbolic-ref", "--short", "HEAD").stdout.strip(), "experiment")
        self.assertFalse((self.project / "app.ts").exists(), "the person's checkout is not touched")

    def test_the_session_contract_follows_the_source_host(self):
        from springer_harness.providers.claude_code import PR_STEPS
        self.assertIn("Do not push", PR_STEPS["local"])
        self.assertIn("spgr-create-pr", PR_STEPS["github"])


class GitHubTest(FakeBinCase):
    def test_merge_reads_the_sha_and_retarget_and_state_go_through_gh(self):
        project = git_project(self.root / "acme")
        host = GitHubSourceHost(lambda slug: project)
        self.assertEqual(host.merge("acme", 7), "abc123")
        self.assertEqual(host.pr_state("acme", 7), "merged")
        self.assertEqual(host.mergeable("acme", 7), "conflicting")
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

    def test_doctor_names_a_hosted_project_without_a_clone(self):
        home = self.root / "home"
        hosted = {"path": str(self.root / "acme"), "settings": {"source_host": "github"}}
        found = setup.check_clones(home, {"acme": hosted, "local": {"path": "/x", "settings": {}}})
        self.assertEqual([(f.name, f.ok, f.required) for f in found], [("clone acme", False, False)])
        clone = self.root / "clone"
        (clone / ".git").mkdir(parents=True)
        found = setup.check_clones(home, {"acme": {**hosted, "clone": str(clone)}})
        self.assertEqual([(f.name, f.ok, f.detail) for f in found], [("clone acme", True, str(clone))])


if __name__ == "__main__":
    unittest.main()


class ReviewPackageTest(unittest.TestCase):
    """The daemon cuts the reviewer's package and checks its tag dispositions."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = git_project(Path(self.tmp.name) / "acme")
        script = self.project / ".claude/skills/spgr-run-harness/scripts/review-package.py"
        script.parent.mkdir(parents=True)
        shutil.copy(REPO / "runtime/skills/spgr-run-harness/scripts/review-package.py", script)
        env = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
        subprocess.run(["git", "-C", str(self.project), "checkout", "-qb", "unit/U-0001"], check=True)
        (self.project / "eslint.config.js").write_text("export default [];\n")
        subprocess.run(["git", "-C", str(self.project), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.project), *env, "commit", "-qm", "loosen lint"], check=True)

    def test_the_package_is_cut_and_a_skipped_tag_is_refused(self):
        from springer_harness.check import review
        out = Path(self.tmp.name) / "U-0002" / "review" / "package.md"
        self.assertIsNone(review.cut_package(self.project, "main", "unit/U-0001", out))
        self.assertIn("eslint.config.js", out.read_text())
        tags = Path(str(out) + ".tags.json")
        self.assertTrue(tags.exists())
        code_review = Path(self.tmp.name) / "code-review.json"
        code_review.write_text(json.dumps({"content": {"gate_tags": []}}))
        self.assertIsNotNone(review.dispositions(self.project, tags, code_review), "an unanswered tag fails")
        self.assertIsNotNone(review.dispositions(self.project, tags, None), "no artifact cannot be checked")

    def test_a_range_that_does_not_exist_is_reported(self):
        from springer_harness.check import review
        self.assertIsNotNone(review.cut_package(self.project, "main", "unit/U-9999", Path(self.tmp.name) / "p.md"))


class IntegrateTest(unittest.TestCase):
    """An artifact unit's branch lands on the default branch, merged off the main checkout."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.project = git_project(root / "acme")
        from springer_harness.scheduler.worktrees import Worktrees
        self.trees = Worktrees(root / "home", "acme", self.project)
        self.path, _ = self.trees.claim("U-0001", "main")

    def commit(self, rel, text):
        (self.path / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.path / rel).write_text(text)
        env = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
        subprocess.run(["git", "-C", str(self.path), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.path), *env, "commit", "-qm", "unit work"], check=True)

    def test_docs_land_and_an_identical_run_store_copy_does_not_block(self):
        self.commit("docs/prd.md", "PRD")
        self.commit("runs/acme-1/artifacts/prd.json", "{}")
        (self.project / "runs/acme-1/artifacts").mkdir(parents=True)
        (self.project / "runs/acme-1/artifacts/prd.json").write_text("{}")
        self.assertIsNone(self.trees.integrate("U-0001"))
        self.assertEqual((self.project / "docs/prd.md").read_text(), "PRD")

    def test_a_differing_untracked_copy_is_never_overwritten(self):
        self.commit("runs/acme-1/artifacts/prd.json", "{}")
        (self.project / "runs/acme-1/artifacts").mkdir(parents=True)
        (self.project / "runs/acme-1/artifacts/prd.json").write_text('{"newer": true}')
        self.assertIn("would be overwritten", self.trees.integrate("U-0001"))
        self.assertEqual((self.project / "runs/acme-1/artifacts/prd.json").read_text(), '{"newer": true}')

    def test_a_dirty_checkout_does_not_refuse_an_integration(self):
        self.commit("docs/prd.md", "PRD")
        (self.project / "notes.md").write_text("a person's edit")
        self.assertIsNone(self.trees.integrate("U-0001"))
        self.assertEqual((self.project / "docs/prd.md").read_text(), "PRD")
        self.assertEqual((self.project / "notes.md").read_text(), "a person's edit")
        self.assertEqual(self.trees.claimed(), ["U-0001"], "the merge scratch tree is gone")

    def test_only_unit_worktrees_count_as_claimed(self):
        (self.trees.root / ".venv").mkdir()
        self.assertEqual(self.trees.claimed(), ["U-0001"])

    def test_code_paths_name_what_is_not_an_artifact(self):
        self.commit("docs/prd.md", "PRD")
        self.commit("design/variants-1/a.html", "<p>")
        self.assertEqual(self.trees.code_paths("U-0001"), [])
        self.commit("src/Hero.tsx", "export {}")
        self.assertEqual(self.trees.code_paths("U-0001"), ["src/Hero.tsx"])

    def test_nothing_committed_is_nothing_to_integrate(self):
        self.assertEqual(self.trees.integrate("U-0001"), "nothing to integrate")

    def test_two_units_that_both_wrote_the_docs_index_merge_it(self):
        index = "# Project documentation\n\nCopies of runs/.\n\n## {h}\n\n- [{a}]({a}.md)\n"
        self.commit("docs/README.md", index.format(h="Product", a="brief"))
        other, _ = self.trees.claim("U-0002", "main")
        (other / "docs").mkdir()
        (other / "docs/README.md").write_text(index.format(h="Design", a="directions"))
        env = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
        subprocess.run(["git", "-C", str(other), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(other), *env, "commit", "-qm", "other"], check=True)
        self.assertIsNone(self.trees.integrate("U-0001"))
        self.assertIsNone(self.trees.integrate("U-0002"))
        merged = (self.project / "docs/README.md").read_text()
        self.assertEqual(merged, "# Project documentation\n\nCopies of runs/.\n\n## Product\n\n- [brief](brief.md)\n\n"
                                 "## Design\n\n- [directions](directions.md)\n")
        status = subprocess.run(["git", "-C", str(self.project), "status", "--porcelain"], capture_output=True, text=True)
        self.assertEqual(status.stdout, "")

    def test_a_conflict_beyond_the_docs_index_is_refused(self):
        self.commit("docs/prd.md", "one")
        other, _ = self.trees.claim("U-0002", "main")
        (other / "docs").mkdir()
        (other / "docs/prd.md").write_text("two")
        env = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
        subprocess.run(["git", "-C", str(other), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(other), *env, "commit", "-qm", "other"], check=True)
        self.assertIsNone(self.trees.integrate("U-0001"))
        self.assertIn("CONFLICT", self.trees.integrate("U-0002"))
        self.assertEqual((self.project / "docs/prd.md").read_text(), "one")
