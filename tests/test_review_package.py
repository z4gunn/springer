"""spgr-run-harness/scripts/review-package.py: the one file a reviewer reads
instead of the main session pasting a diff. The range guard refuses a head
that does not descend from the base."""

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import SCRIPTS, load_script

rp = load_script(SCRIPTS / "review-package.py")


def sh(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
                          env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
                               "GIT_COMMITTER_EMAIL": "t@x", "HOME": str(repo), "PATH": "/usr/bin:/bin:/usr/local/bin"})


class ReviewPackageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        sh(self.repo, "init", "-q", "-b", "main")
        (self.repo / "a.py").write_text("x = 1\n")
        sh(self.repo, "add", "a.py")
        sh(self.repo, "commit", "-q", "-m", "base")
        sh(self.repo, "checkout", "-q", "-b", "feature/s-1-work")
        (self.repo / "a.py").write_text("x = 2\n")
        (self.repo / "b.py").write_text("y = 1\n")
        sh(self.repo, "add", "a.py", "b.py")
        sh(self.repo, "commit", "-q", "-m", "feat: change")

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = rp.main(["review-package.py", *args])
        return rc, buf.getvalue()

    def test_writes_commits_stat_and_diff(self):
        out = self.repo / "pkg" / "review.md"
        rc, msg = self.run_script("main", "HEAD", "--out", str(out), "--repo", str(self.repo))
        self.assertEqual(rc, 0, msg)
        text = out.read_text()
        self.assertIn("commits: 1", text)
        self.assertIn("feat: change", text)
        self.assertIn("b.py", text)
        self.assertIn("-x = 1", text)
        self.assertIn("+x = 2", text)
        self.assertIn("working_tree_dirty: false", text)

    def test_dirty_tree_is_recorded(self):
        (self.repo / "c.py").write_text("z = 1\n")
        out = self.repo / "review.md"
        self.run_script("main", "HEAD", "--out", str(out), "--repo", str(self.repo))
        self.assertIn("working_tree_dirty: true", out.read_text())

    def test_refuses_a_head_that_is_not_a_descendant(self):
        sh(self.repo, "checkout", "-q", "main")
        sh(self.repo, "checkout", "-q", "-b", "other")
        (self.repo / "d.py").write_text("w = 1\n")
        sh(self.repo, "add", "d.py")
        sh(self.repo, "commit", "-q", "-m", "other work")
        out = self.repo / "review.md"
        rc, msg = self.run_script("feature/s-1-work", "other", "--out", str(out), "--repo", str(self.repo))
        self.assertEqual(rc, 1)
        self.assertIn("not a descendant", msg)
        self.assertFalse(out.exists())

    def test_unknown_ref_and_non_repo_exit_two(self):
        rc, _ = self.run_script("main", "nope", "--out", str(self.repo / "r.md"), "--repo", str(self.repo))
        self.assertEqual(rc, 2)
        with tempfile.TemporaryDirectory() as empty:
            rc, _ = self.run_script("main", "HEAD", "--out", str(Path(empty) / "r.md"), "--repo", empty)
            self.assertEqual(rc, 2)


class GateTagsTest(unittest.TestCase):
    """The tags a script can see in a diff that make a gate easier to pass."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        sh(self.repo, "init", "-q", "-b", "main")
        self.write({
            "src/app.ts": "export const a = 1;\n",
            "src/app.test.ts": "it('a', () => {\n  expect(a).toBe(1);\n  expect(a).not.toBe(2);\n});\n"
                               "it('b', () => {\n  expect(a).toBeDefined();\n});\n",
            "tests/test_core.py": "def test_one():\n    assert True\n",
            "tsconfig.json": '{"compilerOptions": {"strict": true}}\n',
            "tests/fixtures/real/resume.txt": "Jane Doe\n",
            "docs/notes.md": "notes\n",
        })
        self.commit("base")
        sh(self.repo, "checkout", "-q", "-b", "story")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, files):
        for rel, text in files.items():
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

    def commit(self, msg, remove=()):
        for rel in remove:
            sh(self.repo, "rm", "-q", rel)
        sh(self.repo, "add", "-A")
        sh(self.repo, "commit", "-q", "-m", msg)

    def tags(self, touch_paths=None):
        out = self.repo / "pkg" / "review.md"
        args = ["review-package.py", "main", "HEAD", "--out", str(out), "--repo", str(self.repo)]
        if touch_paths:
            args += ["--touch-paths", *touch_paths]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rp.main(args), 0)
        self.package = out.read_text()
        return json.loads((self.repo / "pkg" / "review.md.tags.json").read_text())

    def kinds(self, tags):
        return sorted(t["tag"] for t in tags)

    def test_test_first_story_with_no_gate_change_has_no_tags(self):
        self.write({"src/app.test.ts": "it('a', () => {\n  expect(a).toBe(1);\n  expect(a).not.toBe(2);\n});\n"
                                       "it('b', () => {\n  expect(a).toBeDefined();\n});\n"
                                       "it('c', () => {\n  expect(a).toBe(1);\n});\n"})
        self.commit("test: c")
        self.write({"src/app.ts": "export const a = 1;\nexport const c = 3;\n"})
        self.commit("feat: c")
        self.assertEqual(self.tags(["src/"]), [])
        self.assertIn("gate_tags: 0", self.package)

    def test_skips_suppressions_and_removed_tests_are_tagged(self):
        self.write({
            "src/app.test.ts": "it.skip('a', () => {\n  expect(a).toBe(1);\n});\n",
            "src/app.ts": "// @ts-ignore\nexport const a = 1;\n",
        })
        self.commit("chore: quiet the suite")
        tags = self.tags()
        kinds = self.kinds(tags)
        self.assertIn("TEST-SKIPPED", kinds)
        self.assertIn("SUPPRESSION", kinds)
        self.assertIn("TEST-REMOVED", kinds)
        self.assertIn("ASSERTION-LOSS", kinds)
        skipped = next(t for t in tags if t["tag"] == "TEST-SKIPPED")
        self.assertEqual((skipped["file"], skipped["line"]), ("src/app.test.ts", 1))
        self.assertIn("GI-1", self.package)

    def test_config_golden_deleted_tests_and_scope(self):
        self.write({"tsconfig.json": '{"compilerOptions": {"strict": false}}\n',
                    "tests/fixtures/real/resume.txt": "edited\n",
                    "lib/other.ts": "export {};\n",
                    "tests/test_new.py": "def test_two():\n    assert 1\n"})
        self.commit("chore: loosen", remove=["tests/test_core.py"])
        kinds = self.kinds(self.tags(["src/", "tests/"]))
        for kind in ("CHECK-CONFIG", "GOLDEN-EDITED", "TEST-REMOVED", "OUT-OF-SCOPE"):
            self.assertIn(kind, kinds)
        self.assertEqual(kinds.count("OUT-OF-SCOPE"), 2)

    def test_source_before_test_and_source_without_test_are_tagged(self):
        self.write({"src/app.ts": "export const a = 2;\n"})
        self.commit("feat: first")
        tags = self.tags()
        self.assertEqual(self.kinds(tags), ["TEST-ORDER"])
        self.assertIn("no test changed", tags[0]["detail"])
        self.write({"tests/test_core.py": "def test_one():\n    assert True\n\ndef test_more():\n    assert 2\n"})
        self.commit("test: after")
        tags = self.tags()
        self.assertEqual(self.kinds(tags), ["TEST-ORDER"])
        self.assertIn("before the first test change", tags[0]["detail"])

    def test_docs_only_change_is_not_a_test_order_tag(self):
        self.write({"docs/notes.md": "more notes\n"})
        self.commit("docs: notes")
        self.assertEqual(self.tags(), [])

    def test_dispositions_must_cover_every_tag_with_a_reason(self):
        self.write({"src/app.ts": "// eslint-disable-next-line\nexport const a = 1;\n"})
        self.commit("feat: quiet")
        tags = self.tags()
        tags_path = str(self.repo / "pkg" / "review.md.tags.json")
        review = self.repo / "review.json"
        review.write_text(json.dumps({"content": {"gate_tags": []}}))
        self.assertEqual(rp.check_dispositions(tags_path, str(review)) and 1, 1)
        review.write_text(json.dumps({"content": {"gate_tags": [
            {"id": t["id"], "disposition": "accepted", "reason": "the story asks for it"} for t in tags]}}))
        self.assertEqual(rp.check_dispositions(tags_path, str(review)), [])
        review.write_text(json.dumps({"gate_tags": [{"id": tags[0]["id"], "disposition": "maybe", "reason": ""}]}))
        problems = rp.check_dispositions(tags_path, str(review))
        self.assertTrue(any("accepted or finding" in p for p in problems))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rp.main(["review-package.py", "dispositions", tags_path, str(review)]), 1)


if __name__ == "__main__":
    unittest.main()
