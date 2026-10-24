"""spgr-run-harness/assets/dispatch-preamble.md: pasted byte for byte into
every dispatch prompt, so it must hold no fact that changes between
dispatches, or the cached prompt prefix it exists for never repeats."""

import re
import unittest

from helpers import REPO

PREAMBLE = REPO / ".claude" / "skills" / "spgr-run-harness" / "assets" / "dispatch-preamble.md"


class DispatchPreambleTest(unittest.TestCase):
    def setUp(self):
        self.text = PREAMBLE.read_text()

    def test_ends_with_the_brief_line_the_harness_completes(self):
        self.assertTrue(self.text.endswith("Your brief:\n"))

    def test_holds_no_run_variable_fact(self):
        self.assertIsNone(re.search(r"\{[a-z_]+\}|\$\{|\d{4}-\d{2}-\d{2}|CYCLE-\d|runs/[a-z0-9-]+/", self.text))
        placeholders = set(re.findall(r"<([a-z-]+)>", self.text))
        self.assertLessEqual(placeholders, {"name", "unit-dir", "command", "n"})

    def test_carries_the_unit_contract(self):
        for needle in ("receipt.py run", "DONE_WITH_CONCERNS", "BLOCKED", "NEEDS_CONTEXT", "result.md",
                       "fifteen lines", "TODO(DEF-<n>)", ".claude/skills/<name>/SKILL.md"):
            self.assertIn(needle, self.text)

    def test_the_harness_points_at_it(self):
        skill = (REPO / ".claude" / "skills" / "spgr-run-harness" / "SKILL.md").read_text()
        self.assertIn("assets/dispatch-preamble.md", skill)


if __name__ == "__main__":
    unittest.main()
