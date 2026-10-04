"""spgr-write-page-copy/scripts/copy_lint.py: the deterministic half of the
copy standards. One fixture per pattern, a clean passage that must stay
clean, the format reducers for HTML and JSON, and the exit codes."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from helpers import REPO, load_script

cl = load_script(REPO / ".claude" / "skills" / "spgr-write-page-copy" / "scripts" / "copy_lint.py")

CLEAN = """# Expense reports that close on time

Receipts arrive late and incomplete. The report pulls them from your inbox and matches each to a card charge.

## Pricing

Each plan is priced per active cardholder. Start with ten cardholders free.

- Pull receipts from Gmail and Outlook.
- Match each receipt to a card charge.
- Export the month to QuickBooks.

Is it secure? Card data never leaves the processor. No card required to start.
"""


def patterns(text, allow=()):
    return [f["pattern"] for f in cl.lint_text(text, allow)]


class CopyLintPatternTest(unittest.TestCase):
    def test_clean_passage_has_no_findings(self):
        self.assertEqual(patterns(CLEAN), [])

    def test_banned_phrase_reports_longest_match_once(self):
        found = cl.lint_text("Say goodbye to spreadsheets and unlock the power of automation.")
        self.assertEqual([f["pattern"] for f in found], ["banned-phrase", "banned-phrase"])
        self.assertEqual({f["match"] for f in found}, {"Say goodbye to", "unlock the power of"})

    def test_banned_phrase_is_word_bounded(self):
        self.assertEqual(patterns("The delver guild met. A robustness test ran."), [])

    def test_allow_flag_suppresses_a_phrase(self):
        self.assertEqual(patterns("Set up in seconds."), ["banned-phrase"])
        self.assertEqual(patterns("Set up in seconds.", allow=["in seconds"]), [])

    def test_dashes_and_exclamation(self):
        self.assertIn("em-dash", patterns("The result — faster closes."))
        self.assertIn("en-dash", patterns("Open 9–17."))
        self.assertIn("exclamation", patterns("Start today!"))
        self.assertNotIn("exclamation", patterns("![alt text](shot.png)"))

    def test_contrast_reveal(self):
        self.assertIn("contrast-reveal", patterns("It's not a tool, it's a teammate."))
        self.assertIn("contrast-reveal", patterns("This is not just tracking but a full close."))
        self.assertNotIn("contrast-reveal", patterns("The export does not include archived cards."))

    def test_bold_decoration_needs_two_consecutive_bullets(self):
        one = "- **Fast.** Loads quickly.\n- Plain second item.\n"
        two = "- **Fast.** Loads quickly.\n- **Simple.** One screen.\n"
        self.assertNotIn("bold-decoration", patterns(one))
        self.assertEqual(patterns(two).count("bold-decoration"), 1)

    def test_long_sentence(self):
        words = " ".join(["word"] * 26) + "."
        self.assertEqual(patterns(words), ["long-sentence"])
        self.assertEqual(patterns(" ".join(["word"] * 25) + "."), [])

    def test_parallel_openers_need_three_in_a_row(self):
        three = "- Build the report.\n- Build the chart.\n- Build the export.\n"
        two = "- Build the report.\n- Build the chart.\n- Export the month.\n"
        self.assertIn("parallel-openers", patterns(three))
        self.assertNotIn("parallel-openers", patterns(two))

    def test_heading_echo_and_decorative_heading(self):
        self.assertIn("heading-echo", patterns("## Pricing\n\nPricing is simple here.\n"))
        self.assertNotIn("heading-echo", patterns("## Pricing\n\nEach plan is per seat.\n"))
        self.assertIn("decorative-heading", patterns("# Built For The Way You Work\n"))
        self.assertNotIn("decorative-heading", patterns("# Expense reports that close on time\n"))

    def test_fenced_code_and_inline_code_are_skipped(self):
        text = "```\nSay goodbye to this line.\n```\nUse `--effortless` to run it.\n"
        self.assertEqual(patterns(text), [])


class CopyLintFormatTest(unittest.TestCase):
    def test_html_is_reduced_to_text_and_scripts_dropped(self):
        html = '<h1>Seamless onboarding</h1><p>Plain.</p><script>var x="robust";</script>'
        found = cl.lint_text(cl.to_text(html, ".html"))
        self.assertEqual([f["match"] for f in found], ["Seamless"])

    def test_json_string_values_are_scanned(self):
        text = json.dumps({"hero": "Effortless tracking", "n": 3, "items": [{"t": "Plain."}]})
        found = cl.lint_text(cl.to_text(text, ".json"))
        self.assertEqual([f["match"] for f in found], ["Effortless"])


class CopyLintCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cl.main(["copy_lint.py", *args])
        return rc, out.getvalue(), err.getvalue()

    def test_exit_codes_and_json_output(self):
        clean = self.root / "clean.md"
        clean.write_text(CLEAN)
        bad = self.root / "bad.md"
        bad.write_text("Join thousands of happy teams.\n")
        self.assertEqual(self.run_cli(str(clean))[0], 0)
        rc, out, _ = self.run_cli(str(bad), "--json")
        self.assertEqual(rc, 1)
        report = json.loads(out)
        self.assertEqual(report["count"], 1)
        self.assertEqual(report["findings"][0]["line"], 1)
        rc, _, err = self.run_cli(str(self.root / "missing.md"))
        self.assertEqual(rc, 2)
        self.assertIn("could not read", err)

    def test_directory_walk_picks_supported_files_only(self):
        (self.root / "a.md").write_text("Game-changer.\n")
        (self.root / "b.html").write_text("<p>Cutting-edge.</p>")
        (self.root / "c.png").write_bytes(b"\x89PNG")
        rc, out, _ = self.run_cli(str(self.root), "--json")
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out)["count"], 2)


if __name__ == "__main__":
    unittest.main()
