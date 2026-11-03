"""spgr-run-harness is a shim: the daemon drives every run, and this skill must not
carry the loop, because a second writer is the defect the run lock prevents."""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import REPO, SCHEMAS, RunStore, read_events, run_hook

SKILL = (REPO / "runtime" / "skills" / "spgr-run-harness" / "SKILL.md").read_text()


class ShimTest(unittest.TestCase):
    def test_it_sends_the_person_to_springer_and_names_the_daemon(self):
        self.assertIn("`springer`", SKILL)
        self.assertIn("daemon:", SKILL)

    def test_it_carries_no_loop(self):
        self.assertLess(len(SKILL.splitlines()), 40)
        for loop_step in ("## Inputs", "Rehydrate", "Dispatch each routed unit", "fork-join"):
            self.assertNotIn(loop_step, SKILL)

    def test_the_old_loop_is_gone(self):
        self.assertFalse((REPO / "docs" / "harness" / "in-session-loop.md").exists())
        self.assertFalse((REPO / "runtime" / "skills" / "spgr-run-harness" / "scripts" / "run-unattended.py").exists())

    def test_every_script_the_daemon_still_needs_is_still_there(self):
        scripts = REPO / "runtime" / "skills" / "spgr-run-harness" / "scripts"
        for name in ("receipt.py", "classify-failure.py", "pr-risk.py", "review-package.py"):
            self.assertTrue((scripts / name).exists(), name)

    def test_the_barrier_rule_is_gone_from_the_reference(self):
        reference = (REPO / "runtime" / "references" / "pdca-harness.md").read_text()
        self.assertNotIn("barrier", reference)
        self.assertIn("Cycles may overlap", reference)


class HeadlessGateTest(unittest.TestCase):
    def test_notify_human_tells_a_daemon_session_to_write_the_request(self):
        skill = (REPO / "runtime" / "skills" / "spgr-notify-human" / "SKILL.md").read_text()
        self.assertLess(skill.index("gate-request.json"), skill.index("AskUserQuestion"))
        self.assertIn("SPRINGER_SESSION_DIR", skill)


class HookInWorktreeTest(unittest.TestCase):
    def test_the_event_goes_to_the_project_and_not_the_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RunStore(Path(tmp) / "project")
            worktree = Path(tmp) / "worktree"
            worktree.mkdir()
            payload = {"hook_event_name": "PreToolUse", "session_id": "s", "tool_use_id": "t", "cwd": str(worktree),
                       "tool_input": {"subagent_type": "spgr-agent-qa-tester", "description": "d", "prompt": "p"}}
            run_hook("log-agent-events.py", payload, worktree,
                     env={"SPRINGER_PROJECT_DIR": str(store.root), "SPRINGER_RUN_ID": store.run_id})
            lines = read_events(store.run_dir)
            self.assertEqual(lines[0]["run_id"], store.run_id)
            self.assertFalse((worktree / "runs").exists())


class ValidateVenvTest(unittest.TestCase):
    """A python with no site-packages cannot import jsonschema, so it must re-exec."""

    def layout(self, tmp, schema_dir):
        root = Path(tmp)
        target = root / schema_dir
        target.mkdir(parents=True)
        shutil.copy(SCHEMAS / "validate.py", target / "validate.py")
        venv = root / ".venv" / "bin"
        venv.mkdir(parents=True)
        fake = venv / "python"
        fake.write_text("#!/bin/sh\necho found-the-venv\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        return target / "validate.py"

    def test_it_finds_the_venv_in_both_layouts(self):
        for schema_dir in ("schemas", "runtime/schemas"):
            with self.subTest(schema_dir), tempfile.TemporaryDirectory() as tmp:
                script = self.layout(tmp, schema_dir)
                env = {k: v for k, v in os.environ.items() if k != "SPGR_VALIDATE_REEXEC"}
                done = subprocess.run([sys.executable, "-S", "-I", str(script), "--self-check"],
                                      capture_output=True, text=True, env=env)
                self.assertIn("found-the-venv", done.stdout, done.stderr)


if __name__ == "__main__":
    unittest.main()
