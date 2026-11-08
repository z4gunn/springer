"""The production release runner: a deploy script that guards itself with a typed
answer at a terminal gets one, and the harness types the configured word only when
the script stops at its prompt. A checkout that is not clean on the default branch
does not ship."""

import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import harness_support  # noqa: F401, puts the harness package on the path
from springer_harness.release import Releases, ready_to_ship, run_release

GUARDED = """
import sys, time
if not sys.stdin.isatty():
    print("no terminal for the go or no-go answer; aborting.")
    sys.exit(2)
print("building dist")
time.sleep(0.3)
answer = input("Type 'go' to deploy abc123, anything else aborts: ")
if answer != "go":
    print("No-go. Nothing was shipped.")
    sys.exit(1)
print("shipped abc123")
"""


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@x", "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(cwd)})


class RunReleaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "deploy.py").write_text(GUARDED)
        self.command = f"{sys.executable} deploy.py"

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_word_is_typed_at_the_prompt_and_the_script_ships(self):
        result = run_release(self.command, "go", self.root, self.root / "out" / "output.log", timeout=60)
        self.assertEqual((result["exit_code"], result["typed"]), (0, True), result["tail"])
        self.assertIn("shipped abc123", result["tail"])
        self.assertIn("building dist", (self.root / "out" / "output.log").read_text())

    def test_without_the_word_the_script_keeps_its_own_no_go(self):
        result = run_release(self.command, "nope", self.root, self.root / "o.log", timeout=60)
        self.assertEqual(result["exit_code"], 1)
        self.assertIn("Nothing was shipped", result["tail"])

    def test_a_script_that_never_finishes_is_stopped(self):
        (self.root / "hang.py").write_text("import time\nprint('waiting')\ntime.sleep(60)\n")
        started = time.monotonic()
        result = run_release(f"{sys.executable} hang.py", None, self.root, self.root / "h.log", timeout=1)
        self.assertLess(time.monotonic() - started, 30)
        self.assertNotEqual(result["exit_code"], 0)

    def test_the_thread_writes_its_result_and_runs_one_at_a_time(self):
        releases, done = Releases(), []
        out = self.root / "rel"
        self.assertTrue(releases.start("acme", self.command, "go", self.root, out, "abc123", done.append))
        self.assertFalse(releases.start("acme", self.command, "go", self.root, out, "abc123"))
        for _ in range(200):
            if done:
                break
            time.sleep(0.05)
        self.assertEqual(done[0]["exit_code"], 0)
        self.assertEqual(Releases.result(out)["sha"], "abc123")


class ReadyToShipTest(unittest.TestCase):
    def test_only_a_clean_default_branch_ships(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git(repo, "init", "-q", "-b", "main")
            (repo / "a.txt").write_text("1\n")
            git(repo, "add", "a.txt")
            git(repo, "commit", "-q", "-m", "one")
            sha, why = ready_to_ship(repo, "main")
            self.assertEqual((len(sha), why), (40, None))
            (repo / "a.txt").write_text("2\n")
            self.assertIn("uncommitted", ready_to_ship(repo, "main")[1])
            git(repo, "checkout", "-q", "-b", "side")
            self.assertIn("on side, not main", ready_to_ship(repo, "main")[1])
            (repo / "untracked.txt").write_text("x")
            git(repo, "checkout", "-q", "main")
            git(repo, "checkout", "-q", "--", "a.txt")
            self.assertIsNone(ready_to_ship(repo, "main")[1], "an untracked file does not block a release")


if __name__ == "__main__":
    unittest.main()
