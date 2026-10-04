"""spgr-run-harness/scripts/review-package.py: the one file a reviewer reads
instead of the main session pasting a diff. The range guard refuses a head
that does not descend from the base."""

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import SCRIPTS, load_script

rp = load_script(SCRIPTS / "review-package.py")


def sh(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
                          env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
                               "GIT_COMMITTER_EMAIL": "t@x", "HOME": str(repo), "PATH": "/usr/bin:/bin:/usr/local/bin"})


class ReviewPackageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        sh(self.repo, "init", "-q", "-b", "main")
        (self.repo / "a.py").write_text("x = 1\n")
        sh(self.repo, "add", "a.py")
        sh(self.repo, "commit", "-q", "-m", "base")
        sh(self.repo, "checkout", "-q", "-b", "feature/s-1-work")
        (self.repo / "a.py").write_text("x = 2\n")
        (self.repo / "b.py").write_text("y = 1\n")
        sh(self.repo, "add", "a.py", "b.py")
        sh(self.repo, "commit", "-q", "-m", "feat: change")

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = rp.main(["review-package.py", *args])
        return rc, buf.getvalue()

    def test_writes_commits_stat_and_diff(self):
        out = self.repo / "pkg" / "review.md"
        rc, msg = self.run_script("main", "HEAD", "--out", str(out), "--repo", str(self.repo))
        self.assertEqual(rc, 0, msg)
        text = out.read_text()
        self.assertIn("commits: 1", text)
        self.assertIn("feat: change", text)
        self.assertIn("b.py", text)
        self.assertIn("-x = 1", text)
        self.assertIn("+x = 2", text)
        self.assertIn("working_tree_dirty: false", text)

    def test_dirty_tree_is_recorded(self):
        (self.repo / "c.py").write_text("z = 1\n")
        out = self.repo / "review.md"
        self.run_script("main", "HEAD", "--out", str(out), "--repo", str(self.repo))
        self.assertIn("working_tree_dirty: true", out.read_text())

    def test_refuses_a_head_that_is_not_a_descendant(self):
        sh(self.repo, "checkout", "-q", "main")
        sh(self.repo, "checkout", "-q", "-b", "other")
        (self.repo / "d.py").write_text("w = 1\n")
        sh(self.repo, "add", "d.py")
        sh(self.repo, "commit", "-q", "-m", "other work")
        out = self.repo / "review.md"
        rc, msg = self.run_script("feature/s-1-work", "other", "--out", str(out), "--repo", str(self.repo))
        self.assertEqual(rc, 1)
        self.assertIn("not a descendant", msg)
        self.assertFalse(out.exists())

    def test_unknown_ref_and_non_repo_exit_two(self):
        rc, _ = self.run_script("main", "nope", "--out", str(self.repo / "r.md"), "--repo", str(self.repo))
        self.assertEqual(rc, 2)
        with tempfile.TemporaryDirectory() as empty:
            rc, _ = self.run_script("main", "HEAD", "--out", str(Path(empty) / "r.md"), "--repo", empty)
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
