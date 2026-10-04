"""spgr-check-quality-floor/scripts/floor_guard.py: the diff-scoped detector
for a lowered quality bar. Each rule is exercised against a temporary git
repository with a main branch, plus the keep annotation, the clean path, and
the unverified exit outside a repository."""

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import REPO, load_script

fg = load_script(REPO / ".claude" / "skills" / "spgr-check-quality-floor" / "scripts" / "floor_guard.py")

APP = "def add(a, b):\n    return a + b\n"
TEST = ("from app import add\n\n\ndef test_add():\n"
        "    assert add(1, 2) == 3\n    assert add(0, 0) == 0\n    assert add(-1, 1) == 0\n")
JEST = "module.exports = {\n  coverageThreshold: {\n    global: { branches: 80, lines: 90 }\n  }\n};\n"
CONSTRAINTS = "# Constraints\n\n- Coverage at least 85 percent\n- p95 latency under 300 ms\n"
RUN_SH = "#!/bin/sh\ngit commit -m \"$1\"\n"
COVERAGERC = "[report]\nfail_under = 90\n"


class FloorGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.write("src/app.py", APP)
        self.write("tests/test_app.py", TEST)
        self.write("jest.config.js", JEST)
        self.write("CONSTRAINTS.md", CONSTRAINTS)
        self.write("scripts/run.sh", RUN_SH)
        self.write(".coveragerc", COVERAGERC)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "init")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def run_guard(self, *extra):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = fg.main(["floor_guard.py", "--repo", str(self.root), "--base", "main", "--json", *extra])
        return rc, json.loads(buf.getvalue())

    def rules(self, result):
        return sorted(v["rule"] for v in result["violations"])

    def test_clean_tree_exits_zero(self):
        rc, result = self.run_guard()
        self.assertEqual(rc, 0)
        self.assertEqual(result["status"], "clean")
        self.assertEqual(result["violations"], [])

    def test_benign_change_is_clean(self):
        self.write("src/app.py", APP + "\n\ndef sub(a, b):\n    return a - b\n")
        self.write("tests/test_app.py", TEST + "\n\ndef test_more():\n    assert add(2, 2) == 4\n")
        rc, result = self.run_guard()
        self.assertEqual(rc, 0, result)

    def test_suppression_added(self):
        self.write("src/app.py", APP + "x = 1  # noqa\n// @ts-expect-error\n")
        rc, result = self.run_guard()
        self.assertEqual(rc, 1)
        hits = [v for v in result["violations"] if v["rule"] == "suppression"]
        self.assertEqual([h["line"] for h in hits], [3, 4])
        self.assertEqual(hits[0]["file"], "src/app.py")

    def test_ts_expect_error_with_reason_is_fine(self):
        self.write("src/app.py", APP + "// @ts-expect-error legacy shim, tracked in ADR-004\n")
        rc, result = self.run_guard()
        self.assertEqual(rc, 0, result)

    def test_skip_in_test_file(self):
        self.write("tests/test_app.py", TEST.replace("def test_add", "@unittest.skip('later')\ndef test_add"))
        self.write("tests/ui.spec.ts", "describe.skip('x', () => {});\nit.only('y', () => {});\n")
        rc, result = self.run_guard()
        self.assertEqual(rc, 1)
        skips = [v for v in result["violations"] if v["rule"] == "test-skip"]
        self.assertEqual(len(skips), 3)

    def test_skip_pattern_outside_test_file_is_not_flagged(self):
        self.write("src/app.py", APP + "items = stream.skip(2)\n")
        rc, result = self.run_guard()
        self.assertEqual(rc, 0, result)

    def test_deleted_test_file(self):
        os.remove(self.root / "tests" / "test_app.py")
        rc, result = self.run_guard()
        self.assertEqual(rc, 1)
        self.assertIn("test-deleted", self.rules(result))

    def test_fewer_assertions(self):
        self.write("tests/test_app.py", TEST.replace("    assert add(-1, 1) == 0\n", ""))
        rc, result = self.run_guard()
        self.assertEqual(rc, 1)
        hit = next(v for v in result["violations"] if v["rule"] == "assertions")
        self.assertEqual(hit["text"], "assertions 3 -> 2")

    def test_stubs_in_source(self):
        self.write("src/app.py", APP +
                   "def later():\n    raise NotImplementedError\n"
                   "def loud():\n    # TODO(DEF-3) copy pending\n    pass\n"
                   "def quiet():\n    try:\n        run()\n    except Exception:\n        pass\n")
        self.write("src/ui.ts", "try { go(); } catch (e) {}\n")
        rc, result = self.run_guard()
        self.assertEqual(rc, 1)
        stubs = [v for v in result["violations"] if v["rule"] == "stub"]
        self.assertEqual(len(stubs), 4, stubs)

    def test_stub_words_in_test_file_are_not_flagged(self):
        self.write("tests/test_app.py", TEST + "# TODO cover negative numbers\n")
        rc, result = self.run_guard()
        self.assertEqual(rc, 0, result)

    def test_hook_bypass_in_script_but_not_prose(self):
        self.write("scripts/run.sh", "#!/bin/sh\ngit commit --no-verify -m \"$1\"\n")
        self.write("docs/git.md", "Never pass --no-verify.\n")
        rc, result = self.run_guard()
        self.assertEqual(rc, 1)
        self.assertEqual(self.rules(result), ["hook-bypass"])

    def test_loosened_thresholds_are_reported_and_tightened_ones_are_not(self):
        self.write("CONSTRAINTS.md", CONSTRAINTS.replace("at least 85", "at least 70").replace("under 300", "under 250"))
        self.write("jest.config.js", JEST.replace("branches: 80", "branches: 60").replace("lines: 90", "lines: 95"))
        self.write(".coveragerc", "[report]\nfail_under = 80\n")
        rc, result = self.run_guard()
        self.assertEqual(rc, 1)
        hits = [v["text"] for v in result["violations"] if v["rule"] == "threshold"]
        self.assertEqual(len(hits), 3, hits)
        self.assertTrue(any("85 -> 70" in h for h in hits))
        self.assertTrue(any("branches 80 -> 60" in h for h in hits))
        self.assertTrue(any("fail_under 90 -> 80" in h for h in hits))

    def test_keep_annotation_moves_finding_to_kept(self):
        self.write("src/app.py", APP + "x = 1  # noqa  floor: keep vendored line, upstream bug 12\n")
        rc, result = self.run_guard()
        self.assertEqual(rc, 0)
        self.assertEqual(result["violations"], [])
        self.assertEqual(result["kept"][0]["rule"], "suppression")
        self.assertEqual(result["kept"][0]["reason"], "vendored line, upstream bug 12")

    def test_committed_branch_work_is_in_scope(self):
        self.git("checkout", "-q", "-b", "feature/x")
        self.write("src/new.py", "def f():\n    raise NotImplementedError\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "wip")
        rc, result = self.run_guard()
        self.assertEqual(rc, 1)
        self.assertEqual(self.rules(result), ["stub"])
        self.assertEqual(result["base"], "main")

    def test_untracked_file_is_scanned(self):
        self.write("src/extra.py", "# FIXME wire this\n")
        rc, result = self.run_guard()
        self.assertEqual(rc, 1)
        self.assertEqual(result["violations"][0]["file"], "src/extra.py")

    def test_table_output_names_status(self):
        self.write("src/app.py", APP + "x = 1  # noqa\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = fg.main(["floor_guard.py", "--repo", str(self.root), "--base", "main"])
        self.assertEqual(rc, 1)
        self.assertIn("suppression", buf.getvalue())
        self.assertIn("floor-guard: violation", buf.getvalue())

    def test_outside_a_repository_is_unverified(self):
        with tempfile.TemporaryDirectory() as other:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = fg.main(["floor_guard.py", "--repo", other, "--json"])
        self.assertEqual(rc, 2)
        self.assertEqual(json.loads(buf.getvalue())["status"], "unverified")


if __name__ == "__main__":
    unittest.main()
