"""The harness package layout: every subpackage imports, and the command is declared."""

import importlib
import sys
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


if __name__ == "__main__":
    unittest.main()
