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


class CarriedIgnoredTest(unittest.TestCase):
    """A monorepo instance's units would have run with no .env, no package node_modules,
    and none of the person's local fixtures, so tests and product checks fail in the tree
    and on the base alike."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.project = git_project(root / "acme")
        self.extra = []
        (self.project / ".gitignore").write_text(
            ".env\nnode_modules/\n.worktrees/\ntests/fixtures/local/*\n!tests/fixtures/local/.gitkeep\n")
        (self.project / "package-lock.json").write_text('{"v": 1}\n')
        for package in ("web", "worker"):
            (self.project / "packages" / package).mkdir(parents=True)
            (self.project / "packages" / package / "package.json").write_text("{}\n")
        (self.project / "tests" / "fixtures" / "local").mkdir(parents=True)
        (self.project / "tests" / "fixtures" / "local" / ".gitkeep").write_text("")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-qm", "monorepo")
        self.trees = Worktrees(root / "home", "acme", self.project, "acme-1", carried=lambda: self.extra)

    def modules(self, rel):
        folder = self.project / rel / ".bin"
        folder.mkdir(parents=True)
        (folder / "tool").write_text("#!/bin/sh\n")

    def test_each_package_gets_its_own_node_modules(self):
        self.modules("node_modules")
        self.modules("packages/web/node_modules")
        self.modules("packages/gone/node_modules")
        self.modules(".worktrees/feat-x/node_modules")
        tree, _ = self.trees.claim("U-0001", "main")
        self.assertTrue((tree / "node_modules" / ".bin" / "tool").is_file())
        self.assertTrue((tree / "packages" / "web" / "node_modules" / ".bin" / "tool").is_file())
        self.assertFalse((tree / "packages" / "worker" / "node_modules").exists(), "the person has none there")
        self.assertFalse((tree / "packages" / "gone").exists(), "a package the branch does not have")
        self.assertFalse((tree / ".worktrees").exists(), "a hidden folder is never a package")
        self.assertEqual(git(tree, "status", "--porcelain", "-uall").stdout, "")

    def test_a_retry_adds_a_package_folder_the_first_claim_missed(self):
        self.modules("node_modules")
        tree, _ = self.trees.claim("U-0001", "main")
        self.modules("packages/worker/node_modules")
        self.trees.claim("U-0001", "main")
        self.assertTrue((tree / "packages" / "worker" / "node_modules" / ".bin" / "tool").is_file())

    def test_the_env_file_and_the_project_s_fixtures_are_copied_and_never_committed(self):
        (self.project / ".env").write_text("DATABASE_URL=postgres://local\n")
        (self.project / "tests" / "fixtures" / "local" / "sample.pdf").write_text("pdf\n")
        tree, _ = self.trees.claim("U-0001", "main")
        self.assertEqual((tree / ".env").read_text(), "DATABASE_URL=postgres://local\n")
        self.assertFalse((tree / "tests" / "fixtures" / "local" / "sample.pdf").exists(), "not carried until named")
        self.extra = ["tests/fixtures/local/", "/etc", "../outside"]
        self.assertEqual(self.trees.carried_paths()[-1], "tests/fixtures/local/")
        self.assertNotIn("/etc", self.trees.carried_paths())
        self.assertNotIn("../outside", self.trees.carried_paths())
        (tree / ".env").write_text("changed by the unit\n")
        self.trees.claim("U-0001", "main")
        self.assertEqual((tree / "tests" / "fixtures" / "local" / "sample.pdf").read_text(), "pdf\n",
                         "a half-tracked folder still gets its ignored files")
        self.assertEqual((tree / ".env").read_text(), "changed by the unit\n", "a retry keeps the unit's copy")
        self.assertEqual(git(tree, "status", "--porcelain", "-uall").stdout, "", "nothing a unit could commit")
        self.assertEqual((self.project / ".env").read_text(), "DATABASE_URL=postgres://local\n")

    def test_a_base_scratch_tree_has_the_same_files_the_unit_had(self):
        self.modules("node_modules")
        self.modules("packages/web/node_modules")
        (self.project / ".env").write_text("A=1\n")
        sha = git(self.project, "rev-parse", "HEAD").stdout.strip()
        scratch = self.trees.scratch_at(sha)
        self.addCleanup(self.trees.drop_scratch, scratch)
        self.assertTrue((scratch / "packages" / "web" / "node_modules" / ".bin" / "tool").is_file())
        self.assertEqual((scratch / ".env").read_text(), "A=1\n")


if __name__ == "__main__":
    unittest.main()
