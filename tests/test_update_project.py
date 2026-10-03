"""scripts/update-project.py: the owned-runtime manifest and the update that
replaces what an instance never touched and keeps what it edited."""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from helpers import REPO, load_script

up = load_script(REPO / "scripts" / "update-project.py")

CLAUDE_TEMPLATE = """# Project rules

Default profile for this project: `saas`.

Build the app.
"""
SETTINGS_TEMPLATE = '{\n  "hooks": {}\n}\n'
GITIGNORE = """.env
# --- Generated POC artifacts (Phase 3 run output, not source) ---
/runs/
.venv/
"""


def make_source(root):
    """A miniature Springer checkout with the files update-project reads."""
    (root / ".claude" / "skills" / "spgr-one").mkdir(parents=True)
    (root / ".claude" / "skills" / "spgr-one" / "SKILL.md").write_text("one v1\n")
    (root / ".claude" / "skills" / "spgr-two").mkdir(parents=True)
    (root / ".claude" / "skills" / "spgr-two" / "SKILL.md").write_text("two v1\n")
    (root / ".claude" / "agents").mkdir()
    (root / ".claude" / "agents" / "spgr-agent-a.md").write_text("agent v1\n")
    (root / ".claude" / "references").mkdir()
    (root / ".claude" / "references" / "ref.md").write_text("ref v1\n")
    (root / ".claude" / "hooks").mkdir()
    (root / ".claude" / "hooks" / "h.py").write_text("print(1)\n")
    (root / "schemas").mkdir()
    (root / "schemas" / "x-v1.json").write_text("{}\n")
    (root / "templates").mkdir()
    (root / "templates" / "project-CLAUDE.md").write_text(CLAUDE_TEMPLATE)
    (root / "templates" / "project-settings.json").write_text(SETTINGS_TEMPLATE)
    (root / ".gitignore").write_text(GITIGNORE)


def instantiate(source, target, profile="small"):
    """What new-project.sh does, minus git."""
    for rel in up.RUNTIME_DIRS:
        shutil.copytree(source / rel, target / rel)
    (target / "CLAUDE.md").write_text(up.render_claude_md(source, profile))
    (target / ".claude" / "settings.json").write_text(up.render_settings(source))
    (target / ".gitignore").write_text(up.render_gitignore(source))
    (target / "runs").mkdir()
    return up.cmd_manifest(target, profile)


def run_main(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = up.main(["update-project.py", *argv])
    return code, out.getvalue(), err.getvalue()


class UpdateProjectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.source = Path(self.tmp.name) / "springer"
        self.target = Path(self.tmp.name) / "app"
        self.source.mkdir()
        self.target.mkdir()
        make_source(self.source)
        self.saved_source = up.SOURCE
        up.SOURCE = self.source
        with contextlib.redirect_stdout(io.StringIO()):
            instantiate(self.source, self.target)

    def tearDown(self):
        up.SOURCE = self.saved_source
        self.tmp.cleanup()

    def manifest(self):
        return json.loads((self.target / up.MANIFEST_REL).read_text())

    def test_manifest_records_runtime_and_templates(self):
        m = self.manifest()
        self.assertEqual(m["profile"], "small")
        self.assertEqual(sorted(m["runtime"]), [
            ".claude/agents/spgr-agent-a.md", ".claude/hooks/h.py",
            ".claude/references/ref.md", ".claude/skills/spgr-one/SKILL.md",
            ".claude/skills/spgr-two/SKILL.md", "schemas/x-v1.json"])
        self.assertTrue(all(v.startswith("sha256:") for v in m["runtime"].values()))
        self.assertEqual(m["templates"]["CLAUDE.md"]["from"], "templates/project-CLAUDE.md")
        self.assertEqual(m["templates"]["CLAUDE.md"]["hash"], m["templates"]["CLAUDE.md"]["rendered_hash"])
        self.assertIn("Default profile for this project: `small`.", (self.target / "CLAUDE.md").read_text())
        self.assertNotIn("/runs/", (self.target / ".gitignore").read_text())

    def test_fresh_instance_has_nothing_to_do(self):
        code, out, _ = run_main("status", str(self.target))
        self.assertEqual(code, 0)
        self.assertIn("6 runtime files and 3 template renders already match", out)
        self.assertNotIn("replaced", out)

    def test_source_change_replaces_an_unedited_file(self):
        (self.source / ".claude" / "skills" / "spgr-one" / "SKILL.md").write_text("one v2\n")
        code, out, _ = run_main("update", str(self.target))
        self.assertEqual(code, 0)
        self.assertIn("1 replaced", out)
        self.assertEqual((self.target / ".claude" / "skills" / "spgr-one" / "SKILL.md").read_text(), "one v2\n")
        self.assertEqual(self.manifest()["runtime"][".claude/skills/spgr-one/SKILL.md"],
                         up.sha256(self.source / ".claude" / "skills" / "spgr-one" / "SKILL.md"))

    def test_instance_edit_is_kept_unless_forced(self):
        (self.source / ".claude" / "skills" / "spgr-one" / "SKILL.md").write_text("one v2\n")
        (self.target / ".claude" / "skills" / "spgr-one" / "SKILL.md").write_text("one edited here\n")
        code, out, _ = run_main("update", str(self.target))
        self.assertEqual(code, 0)
        self.assertIn("edited in the instance, kept", out)
        self.assertEqual((self.target / ".claude" / "skills" / "spgr-one" / "SKILL.md").read_text(), "one edited here\n")
        run_main("update", str(self.target), "--force")
        self.assertEqual((self.target / ".claude" / "skills" / "spgr-one" / "SKILL.md").read_text(), "one v2\n")

    def test_new_source_file_is_added(self):
        (self.source / ".claude" / "skills" / "spgr-three").mkdir()
        (self.source / ".claude" / "skills" / "spgr-three" / "SKILL.md").write_text("three\n")
        code, out, _ = run_main("update", str(self.target))
        self.assertIn("1 added", out)
        self.assertTrue((self.target / ".claude" / "skills" / "spgr-three" / "SKILL.md").exists())
        self.assertIn(".claude/skills/spgr-three/SKILL.md", self.manifest()["runtime"])

    def test_removed_source_file_is_removed_when_unedited_and_kept_when_edited(self):
        shutil.rmtree(self.source / ".claude" / "skills" / "spgr-two")
        (self.source / ".claude" / "references" / "ref.md").unlink()
        (self.target / ".claude" / "references" / "ref.md").write_text("ref edited\n")
        code, out, _ = run_main("update", str(self.target))
        self.assertIn("1 removed", out)
        self.assertIn("gone from the source but edited here, kept", out)
        self.assertFalse((self.target / ".claude" / "skills" / "spgr-two" / "SKILL.md").exists())
        self.assertTrue((self.target / ".claude" / "references" / "ref.md").exists())

    def test_instance_only_file_is_kept(self):
        (self.target / ".claude" / "skills" / "local-skill").mkdir()
        (self.target / ".claude" / "skills" / "local-skill" / "SKILL.md").write_text("mine\n")
        code, out, _ = run_main("update", str(self.target))
        self.assertIn("added by the instance, kept", out)
        self.assertTrue((self.target / ".claude" / "skills" / "local-skill" / "SKILL.md").exists())

    def test_template_change_replaces_an_unedited_render(self):
        (self.source / "templates" / "project-CLAUDE.md").write_text(CLAUDE_TEMPLATE + "\nNew rule.\n")
        code, out, _ = run_main("update", str(self.target))
        self.assertIn("1 template render replaced", out)
        text = (self.target / "CLAUDE.md").read_text()
        self.assertIn("New rule.", text)
        self.assertIn("Default profile for this project: `small`.", text)

    def test_template_change_with_edited_render_is_written_aside(self):
        (self.source / "templates" / "project-CLAUDE.md").write_text(CLAUDE_TEMPLATE + "\nNew rule.\n")
        (self.target / "CLAUDE.md").write_text("my own rules\n")
        code, out, _ = run_main("update", str(self.target))
        self.assertIn("template changed and the file was edited", out)
        self.assertEqual((self.target / "CLAUDE.md").read_text(), "my own rules\n")
        aside = self.target / up.UPDATE_DIR_REL / "CLAUDE.md"
        self.assertIn("New rule.", aside.read_text())

    def test_live_lock_refuses_and_stale_lock_proceeds(self):
        run_dir = self.target / "runs" / "r1"
        run_dir.mkdir()
        fresh = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (run_dir / ".lock").write_text(json.dumps({"session_id": "live", "claimed_at": fresh}))
        code, _, err = run_main("update", str(self.target))
        self.assertEqual(code, 1)
        self.assertIn("live lock", err)
        self.assertEqual(run_main("update", str(self.target), "--force")[0], 0)
        stale = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))
        (run_dir / ".lock").write_text(json.dumps({"session_id": "old", "claimed_at": stale}))
        self.assertEqual(run_main("update", str(self.target))[0], 0)

    def test_dry_run_writes_nothing(self):
        (self.source / ".claude" / "skills" / "spgr-one" / "SKILL.md").write_text("one v2\n")
        before = self.manifest()
        code, out, _ = run_main("update", str(self.target), "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("Dry run, nothing written", out)
        self.assertEqual((self.target / ".claude" / "skills" / "spgr-one" / "SKILL.md").read_text(), "one v1\n")
        self.assertEqual(self.manifest(), before)

    def test_missing_manifest_is_refused(self):
        (self.target / up.MANIFEST_REL).unlink()
        code, _, err = run_main("update", str(self.target))
        self.assertEqual(code, 1)
        self.assertIn("springer-manifest", err)

    def test_adopting_a_hand_synced_instance_names_what_already_differs(self):
        (self.target / up.MANIFEST_REL).unlink()
        (self.target / ".claude" / "skills" / "spgr-one" / "SKILL.md").write_text("edited before adoption\n")
        code, out, _ = run_main("manifest", str(self.target), "--profile", "small")
        self.assertEqual(code, 0)
        self.assertIn("1 runtime file(s) differ from this checkout", out)
        self.assertIn(".claude/skills/spgr-one/SKILL.md", out)
        code, out, _ = run_main("manifest", str(self.target), "--profile", "small")
        self.assertIn("1 runtime file(s) differ", out)

    def test_usage_errors(self):
        self.assertEqual(run_main("bogus", str(self.target))[0], 2)
        self.assertEqual(run_main("manifest", str(self.target))[0], 2)
        self.assertEqual(run_main("manifest", str(self.target), "--profile", "enterprise")[0], 2)


class NewProjectIntegrationTest(unittest.TestCase):
    """The real new-project.sh on the real checkout: the sed render and the
    Python render must agree, and a fresh instance must need no update."""

    def test_new_project_writes_a_manifest_and_a_clean_status(self):
        if shutil.which("git") is None:
            self.skipTest("git not available")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "app"
            env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null")
            proc = subprocess.run(["bash", str(REPO / "scripts" / "new-project.sh"), str(target), "brochure"],
                                  capture_output=True, text=True, env=env)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            manifest = json.loads((target / up.MANIFEST_REL).read_text())
            self.assertEqual(manifest["profile"], "brochure")
            self.assertGreater(len(manifest["runtime"]), 200)
            self.assertIn("Default profile for this project: `brochure`.", (target / "CLAUDE.md").read_text())
            proc = subprocess.run([sys.executable, str(REPO / "scripts" / "update-project.py"), "status", str(target)],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("3 template renders already match", proc.stdout)
            self.assertNotIn("replaced", proc.stdout)
            self.assertNotIn("added", proc.stdout.replace("already match", ""))


if __name__ == "__main__":
    unittest.main()
