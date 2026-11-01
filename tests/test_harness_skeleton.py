"""The harness package layout: every subpackage imports, and the command exists
and says what to do when no daemon is running."""

import contextlib
import importlib
import importlib.util
import io
import sys
import tempfile
import tomllib
import unittest

from helpers import REPO

HARNESS = REPO / "harness"
sys.path.insert(0, str(HARNESS))

SUBPACKAGES = ("state", "scheduler", "dispatch", "providers", "check",
               "gates", "retrieval", "api", "tui", "chat")


class HarnessSkeletonTest(unittest.TestCase):
    def test_every_subpackage_imports_and_says_what_it_owns(self):
        for name in SUBPACKAGES:
            module = importlib.import_module(f"springer_harness.{name}")
            self.assertTrue(module.__doc__, name)

    def test_no_subpackage_is_undeclared(self):
        found = {p.name for p in (HARNESS / "springer_harness").iterdir()
                 if p.is_dir() and p.name != "__pycache__"}
        self.assertEqual(found, set(SUBPACKAGES))

    def test_console_script_points_at_the_cli(self):
        project = tomllib.loads((HARNESS / "pyproject.toml").read_text())["project"]
        self.assertEqual(project["name"], "springer-harness")
        self.assertEqual(project["scripts"]["springer"], "springer_harness.cli:main")

    def test_cli_names_the_next_step_when_no_daemon_runs(self):
        if importlib.util.find_spec("textual") is None:
            self.skipTest("the TUI dependencies are not installed")
        cli = importlib.import_module("springer_harness.cli")
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as home, contextlib.redirect_stderr(err):
            self.assertEqual(cli.main([home]), 1)
        self.assertIn("springer daemon", err.getvalue())


if __name__ == "__main__":
    unittest.main()
