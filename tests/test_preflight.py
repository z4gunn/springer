"""spgr-run-harness/scripts/preflight.py: the run-open tooling table. The
optional design-check tools appear as rows whether or not they are installed,
and a missing optional tool never changes the exit code."""

import contextlib
import io
import os
import stat
import tempfile
import unittest
from pathlib import Path

from helpers import SCRIPTS, load_script

pf = load_script(SCRIPTS / "preflight.py")


class PreflightTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bin = Path(self.tmp.name)
        self.old_path = os.environ.get("PATH", "")
        # Stub the slow or environment-bound checks so main() is fast and hermetic.
        self.saved = {n: getattr(pf, n) for n in
                      ("check_browser", "check_gh", "check_venv", "check_git_identity")}
        pf.check_browser = lambda: ("ok", "stub")
        pf.check_gh = lambda: ("ok", "stub")
        pf.check_venv = lambda: ("ok", "stub")
        pf.check_git_identity = lambda: ("ok", "stub")

    def tearDown(self):
        os.environ["PATH"] = self.old_path
        for n, fn in self.saved.items():
            setattr(pf, n, fn)
        self.tmp.cleanup()

    def table(self, profile="brochure"):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = pf.main(["preflight.py", "--profile", profile])
        return rc, buf.getvalue()

    def test_optional_design_tools_are_rows_even_when_missing(self):
        os.environ["PATH"] = str(self.bin)
        rc, out = self.table()
        self.assertEqual(rc, 0)
        rows = {line.split("  ")[0].strip(): line for line in out.splitlines()}
        self.assertIn("playwright-cli (optional)", rows)
        self.assertIn("impeccable (optional)", rows)
        self.assertIn("missing", rows["playwright-cli (optional)"])
        self.assertIn("missing", rows["impeccable (optional)"])

    def test_installed_design_tool_reports_ok(self):
        fake = self.bin / "playwright-cli"
        fake.write_text("#!/bin/sh\necho 0.1.22\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        os.environ["PATH"] = str(self.bin)
        rc, out = self.table()
        self.assertEqual(rc, 0)
        line = next(l for l in out.splitlines() if l.startswith("playwright-cli (optional)"))
        self.assertIn("ok", line)
        self.assertIn("0.1.22", line)

    def test_broken_tool_reports_broken(self):
        fake = self.bin / "impeccable"
        fake.write_text("#!/bin/sh\nexit 1\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        os.environ["PATH"] = str(self.bin)
        _, out = self.table()
        line = next(l for l in out.splitlines() if l.startswith("impeccable (optional)"))
        self.assertIn("broken", line)


if __name__ == "__main__":
    unittest.main()
