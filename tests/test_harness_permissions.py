"""The allowlist a headless unit runs under."""

import json
import tempfile
import unittest
from pathlib import Path

import harness_support  # noqa: F401, puts the harness package on the path
from harness_support import REPO

from springer_harness.providers.claude_code import expand_directories  # noqa: E402


class ExpandDirectoriesTest(unittest.TestCase):
    def test_a_directory_rule_names_the_scripts_its_interpreter_runs_not_the_data_files(self):
        """Run ecg-10's units ran with `Bash(python3 verification/plex-OFL.txt:*)` and a rule
        for every manifest, while the scripts sat beside them."""
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "verification"
            folder.mkdir()
            for name in ("check.py", "check-a11y.sh", "fonts.manifest.json", "plex-OFL.txt", ".hidden.py"):
                (folder / name).write_text("x")
            (folder / "fixtures").mkdir()
            rules = expand_directories(tmp, ["Bash(python3 verification/:*)", "Bash(bash verification/:*)",
                                             "Bash(git log:*)"])
        self.assertEqual(rules, ["Bash(python3 verification/check.py:*)", "Bash(bash verification/check-a11y.sh:*)",
                                 "Bash(git log:*)"])


class TemplateAllowlistTest(unittest.TestCase):
    def test_a_reviewer_can_serve_a_static_build_on_loopback_and_read_a_merge_ahead(self):
        """Run ecg-10's reviewers could not start a server, so axe and the captures never ran."""
        allow = json.loads((REPO / "templates" / "project-settings.json").read_text())["permissions"]["allow"]
        self.assertIn("Bash(python3 -m http.server --bind 127.0.0.1:*)", allow)
        self.assertIn("Bash(git merge-tree:*)", allow)
        self.assertNotIn("Bash(python3 -c:*)", allow, "inline code would bypass every other rule")


if __name__ == "__main__":
    unittest.main()
