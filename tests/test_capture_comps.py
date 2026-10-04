"""spgr-render-design-comps/scripts/capture-comps.py: the deterministic capture
and detect step behind the design critique. Both external tools are optional,
so the script is exercised with fake binaries on PATH and with none."""

import contextlib
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from helpers import REPO, load_script

cc = load_script(REPO / ".claude" / "skills" / "spgr-render-design-comps" / "scripts" / "capture-comps.py")

FAKE_CLI = """#!/bin/sh
# Fake playwright-cli: writes a file for screenshot, accepts everything else.
cmd="$1"
if [ "$cmd" = "screenshot" ]; then
  for a in "$@"; do
    case "$a" in --filename=*) f="${a#--filename=}";; esac
  done
  printf 'PNG' > "$f"
fi
echo "$@" >> "$FAKE_LOG"
exit 0
"""

FAKE_DETECTOR = """#!/bin/sh
echo "scanning..."
echo '{"findings": [{"rule": "gradient-text", "file": "home.html"}]}'
exit 2
"""


def write_exec(path, body):
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class CaptureCompsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.comps = self.root / "comps"
        self.comps.mkdir()
        for name in ("home", "job"):
            (self.comps / f"{name}.html").write_text("<!doctype html><title>x</title>")
        (self.comps / "tokens.css").write_text(":root{}")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.old_path = os.environ.get("PATH", "")
        self.old_home = os.environ.get("HOME", "")
        self.old_cwd = os.getcwd()
        os.environ["HOME"] = str(self.root / "home")
        (self.root / "home").mkdir()
        os.environ.pop("IMPECCABLE_BIN", None)
        os.chdir(self.root)
        os.environ["FAKE_LOG"] = str(self.root / "cli.log")

    def tearDown(self):
        os.chdir(self.old_cwd)
        os.environ["PATH"] = self.old_path
        os.environ["HOME"] = self.old_home
        os.environ.pop("FAKE_LOG", None)
        self.tmp.cleanup()

    def run_script(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cc.main(list(args))
        return rc, buf.getvalue()

    def report(self, out):
        return json.loads((Path(out) / "capture-report.json").read_text())

    def test_missing_tools_still_writes_report_and_exits_zero(self):
        os.environ["PATH"] = str(self.bin)
        rc, out = self.run_script(str(self.comps), "--out", "shots")
        self.assertEqual(rc, 0)
        rep = self.report("shots")
        self.assertEqual(rep["tools"], {"playwright-cli": "missing", "impeccable": "missing"})
        self.assertEqual(rep["shots"], [])
        self.assertFalse(rep["detect"]["ran"])
        self.assertEqual(rep["pages"], ["home", "job"])
        self.assertIn("playwright-cli missing", out)

    def test_capture_matrix_with_fake_cli(self):
        write_exec(self.bin / "playwright-cli", FAKE_CLI)
        os.environ["PATH"] = f"{self.bin}:{self.old_path}"
        rc, _ = self.run_script(str(self.comps), "--out", "shots",
                                "--widths", "375,1440", "--schemes", "light,dark", "--no-detect")
        self.assertEqual(rc, 0)
        rep = self.report("shots")
        self.assertEqual(len(rep["shots"]), 8)
        self.assertTrue(all(s["ok"] for s in rep["shots"]))
        self.assertTrue((self.root / "shots" / "home-375-light.png").exists())
        self.assertTrue((self.root / "shots" / "job-1440-dark.png").exists())
        self.assertEqual(rep["failures"], [])
        log = (self.root / "cli.log").read_text()
        self.assertIn("resize 375 900", log)
        self.assertIn("set-color-scheme dark", log)
        self.assertNotIn("set-reduced-motion", log)

    def test_reduced_motion_flag_is_passed_through(self):
        write_exec(self.bin / "playwright-cli", FAKE_CLI)
        os.environ["PATH"] = f"{self.bin}:{self.old_path}"
        self.run_script(str(self.comps / "home.html"), "--out", "shots",
                        "--widths", "768", "--schemes", "light", "--reduced-motion", "--no-detect")
        log = (self.root / "cli.log").read_text()
        self.assertIn("set-reduced-motion reduce", log)
        rep = self.report("shots")
        self.assertEqual(rep["kind"], "file")
        self.assertTrue(rep["reduced_motion"])

    def test_detector_output_is_recorded(self):
        write_exec(self.bin / "impeccable", FAKE_DETECTOR)
        os.environ["PATH"] = f"{self.bin}"
        rc, out = self.run_script(str(self.comps), "--out", "shots")
        self.assertEqual(rc, 0)
        rep = self.report("shots")
        self.assertTrue(rep["detect"]["ran"])
        self.assertEqual(rep["detect"]["exit_code"], 2)
        self.assertEqual(rep["detect"]["findings_count"], 1)
        parsed = json.loads((self.root / "shots" / "detect.json").read_text())
        self.assertEqual(parsed["findings"][0]["rule"], "gradient-text")
        self.assertIn("findings 1", out)

    def test_detector_is_found_in_the_global_skill_install(self):
        launcher = self.root / "home" / ".claude" / "skills" / "impeccable" / "scripts" / "impeccable"
        launcher.parent.mkdir(parents=True)
        write_exec(launcher, FAKE_DETECTOR)
        os.environ["PATH"] = str(self.bin)
        rc, _ = self.run_script(str(self.comps), "--out", "shots")
        self.assertEqual(rc, 0)
        rep = self.report("shots")
        self.assertEqual(rep["tools"]["impeccable"], "ok")
        self.assertEqual(rep["detect"]["findings_count"], 1)

    def test_url_target_derives_a_page_name(self):
        os.environ["PATH"] = str(self.bin)
        kind, pages = cc.resolve_pages("http://localhost:3000/app/settings")
        self.assertEqual(kind, "url")
        self.assertEqual(pages, [("app-settings", "http://localhost:3000/app/settings")])
        self.assertEqual(cc.resolve_pages("http://localhost:3000/")[1][0][0], "page")

    def test_missing_target_exits_two(self):
        os.environ["PATH"] = str(self.bin)
        rc, _ = self.run_script(str(self.root / "nope"), "--out", "shots")
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
