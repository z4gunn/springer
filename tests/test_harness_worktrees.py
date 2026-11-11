"""What a unit worktree carries that git does not."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from harness_support import git_project

from springer_harness.scheduler.worktrees import Worktrees  # noqa: E402

ENV = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *ENV, *args], capture_output=True, text=True)


class LocalStateTest(unittest.TestCase):
    """Run ecg-10's units found no .venv/bin/python and no .impeccable/ in their trees."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.project = git_project(root / "acme")
        (self.project / ".gitignore").write_text(".venv/\n.impeccable/\n")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-qm", "ignores")
        self.trees = Worktrees(root / "home", "acme", self.project, "acme-1")
        harness_python = root / "home" / "worktrees" / "acme" / ".venv" / "bin" / "python"
        harness_python.parent.mkdir(parents=True)
        harness_python.write_text("#!/bin/sh\n")

    def test_a_unit_tree_has_the_venv_and_a_copy_of_the_ignored_design_notes(self):
        notes = self.project / ".impeccable" / "surfaces" / "site-index-html.md"
        notes.parent.mkdir(parents=True)
        notes.write_text("surface\n")
        tree, _ = self.trees.claim("U-0001", "main")
        self.assertTrue((tree / ".venv" / "bin" / "python").exists())
        self.assertEqual((tree / ".impeccable" / "surfaces" / "site-index-html.md").read_text(), "surface\n")
        self.assertFalse((tree / ".impeccable").is_symlink(), "a copy, so the unit cannot change the person's")
        self.assertEqual(git(tree, "status", "--porcelain", "-uall").stdout, "", "nothing a unit could commit")
        self.assertEqual(git(self.project, "status", "--porcelain", "-uall").stdout, "")
        tree, _ = self.trees.claim("U-0001", "main")
        self.assertTrue((tree / ".venv").is_symlink(), "a retry keeps the same tree")
        self.assertIsNone(self.trees.release("U-0001"), "what the harness carried never keeps a worktree")
        self.assertFalse(tree.exists())
        self.assertTrue((self.project / ".impeccable" / "surfaces" / "site-index-html.md").exists())

    def test_a_tracked_path_is_never_copied_over(self):
        (self.project / ".gitignore").write_text(".venv/\n")
        (self.project / ".impeccable").mkdir()
        (self.project / ".impeccable" / "x.md").write_text("tracked\n")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-qm", "track it")
        tree, _ = self.trees.claim("U-0001", "main")
        self.assertEqual((tree / ".impeccable" / "x.md").read_text(), "tracked\n")
        self.assertEqual(git(tree, "status", "--porcelain", "-uall").stdout, "")


if __name__ == "__main__":
    unittest.main()
