"""spgr-run-harness/scripts/pr-risk.py: low and medium merge on their own,
high waits for the human, and the reasons say why."""

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import SCRIPTS, load_script

pr = load_script(SCRIPTS / "pr-risk.py")
ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@x", "PATH": "/usr/bin:/bin:/usr/local/bin"}


class PrRiskTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.sh("init", "-q", "-b", "main")
        self.write({"src/app.ts": "export const a = 1;\n", "package.json": '{"dependencies": {}}\n'})
        self.commit("base")
        self.sh("checkout", "-q", "-b", "story")

    def tearDown(self):
        self.tmp.cleanup()

    def sh(self, *args):
        subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True,
                       env=dict(ENV, HOME=str(self.repo)))

    def write(self, files):
        for rel, text in files.items():
            p = self.repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)

    def commit(self, msg):
        self.sh("add", "-A")
        self.sh("commit", "-q", "-m", msg)

    def assess(self, **kw):
        return pr.assess(self.repo, "main", "HEAD", **kw)

    def test_ordinary_feature_is_low(self):
        self.write({"src/app.ts": "export const a = 2;\n", "src/list.tsx": "export {};\n"})
        self.commit("feat: list")
        r = self.assess()
        self.assertEqual((r["risk"], r["auto_merge"]), ("low", True))

    def test_each_high_category(self):
        cases = {
            "auth": {"src/auth/session.ts": "x\n"},
            "data": {"db/migrations/0002_add.sql": "ALTER TABLE t ADD c int;\n"},
            "money": {"src/billing/plan.ts": "x\n"},
            "infra": {".github/workflows/ci.yml": "on: push\n"},
            "fact": {"src/footer.tsx": "const year = 'TODO(DEF-3)';\n"},
            "vendor": {"package.json": '{"dependencies": {\n  "stripe": "^14.0.0"\n}}\n'},
        }
        for cat, files in cases.items():
            self.sh("checkout", "-q", "main")
            self.sh("checkout", "-q", "-B", f"s-{cat}")
            self.write(files)
            self.commit(cat)
            r = self.assess()
            self.assertEqual(r["risk"], "high", cat)
            self.assertIn(cat, r["categories"], cat)

    def test_destructive_statement_in_any_file_is_high(self):
        self.write({"src/cleanup.ts": "await db.query('DELETE FROM sessions');\n"})
        self.commit("chore: cleanup")
        r = self.assess()
        self.assertEqual(r["categories"], ["data"])
        self.assertTrue(any("destructive" in x for x in r["reasons"]))

    def test_dependency_size_and_accepted_tags_are_medium(self):
        self.write({"package.json": '{"dependencies": {\n  "clsx": "^2.0.0"\n}}\n'})
        self.commit("chore: dep")
        self.assertEqual(self.assess()["risk"], "medium")
        tags = [{"id": "GI-1", "tag": "TEST-SKIPPED", "file": "src/a.test.ts"}]
        review = {"content": {"gate_tags": [{"id": "GI-1", "disposition": "accepted", "reason": "flaky upstream"}]}}
        self.assertIn("gate-tag", self.assess(tags=tags, review=review)["categories"])
        finding = {"content": {"gate_tags": [{"id": "GI-1", "disposition": "finding", "reason": "raised P1"}]}}
        self.assertNotIn("gate-tag", self.assess(tags=tags, review=finding)["categories"])
        self.write({"src/big.ts": "x\n" * 450})
        self.commit("feat: big")
        self.assertIn("size", self.assess()["categories"])

    def test_open_security_finding_is_high_and_resolved_is_not(self):
        self.write({"src/app.ts": "export const a = 3;\n"})
        self.commit("feat: a")
        open_finding = {"content": {"findings": [{"severity": "High", "title": "SSRF in fetch", "status": "open"}]}}
        self.assertEqual(self.assess(audits=[open_finding])["categories"], ["security"])
        closed = {"content": {"findings": [{"severity": "Critical", "title": "x", "status": "resolved"}]}}
        self.assertEqual(self.assess(audits=[closed])["risk"], "low")
        self.assertEqual(self.assess(audits=[{"content": {"verdict": "GATE"}}])["risk"], "high")

    def test_project_config_adds_and_exempts_paths(self):
        self.write({"src/server/tenancy.ts": "x\n", "docs/auth/guide.md": "x\n"})
        self.commit("feat: tenancy docs")
        config = {"high": {"data": ["^src/server/tenancy"]}, "low": ["^docs/"]}
        r = self.assess(config=config)
        self.assertEqual(r["categories"], ["data"])
        self.assertFalse(any("docs/auth" in x for x in r["reasons"]))

    def test_run_store_changes_are_ignored(self):
        self.write({"runs/r1/artifacts/auth-model.json": "{}\n"})
        self.commit("chore: artifacts")
        self.assertEqual(self.assess()["risk"], "low")

    def test_cli_exit_codes(self):
        self.write({"src/auth/x.ts": "x\n"})
        self.commit("feat: auth")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(pr.main(["pr-risk.py", "main", "HEAD", "--repo", str(self.repo)]), 1)
        self.assertEqual(json.loads(out.getvalue())["risk"], "high")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(pr.main(["pr-risk.py", "main", "nope", "--repo", str(self.repo)]), 2)


if __name__ == "__main__":
    unittest.main()
