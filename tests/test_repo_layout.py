"""The source layout: runtime/ holds the runtime, .claude and schemas link to it
so this checkout loads its own runtime, and an instance never sees either fact."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import REPO, load_script

up = load_script(REPO / "scripts" / "update-project.py")

LINKS = {
    ".claude/skills": "runtime/skills",
    ".claude/agents": "runtime/agents",
    ".claude/references": "runtime/references",
    ".claude/hooks": "runtime/hooks",
    "schemas": "runtime/schemas",
}


class SourceLayoutTest(unittest.TestCase):
    def test_each_dev_link_is_a_symlink_into_runtime(self):
        for link, target in LINKS.items():
            path = REPO / link
            self.assertTrue(path.is_symlink(), f"{link} must be a symlink")
            self.assertEqual(path.resolve(), (REPO / target).resolve())

    def test_links_are_relative_so_a_fresh_clone_resolves_them(self):
        for link in LINKS:
            self.assertFalse(os.path.isabs(os.readlink(REPO / link)), link)

    def test_layout_table_covers_every_link(self):
        self.assertEqual({instance: source for source, instance in up.RUNTIME_LAYOUT}, LINKS)

    def test_source_files_are_keyed_by_their_instance_path(self):
        files = up.source_runtime_files(REPO)
        self.assertIn(".claude/skills/spgr-run-harness/SKILL.md", files)
        self.assertIn("schemas/validate.py", files)
        self.assertFalse([rel for rel in files if rel.startswith("runtime/")])


class ScaffoldTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.target = Path(cls.tmp.name) / "app"
        subprocess.run(["bash", str(REPO / "scripts" / "new-project.sh"), str(cls.target), "small"],
                       check=True, capture_output=True, text=True,
                       env=dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_instance_holds_real_directories_not_links(self):
        for rel in LINKS:
            path = self.target / rel
            self.assertTrue(path.is_dir(), rel)
            self.assertFalse(path.is_symlink(), f"{rel} must be a copy in an instance")

    def test_instance_has_no_source_layout(self):
        self.assertFalse((self.target / "runtime").exists())
        self.assertFalse((self.target / "harness").exists())

    def test_manifest_records_instance_paths(self):
        manifest = json.loads((self.target / up.MANIFEST_REL).read_text())
        self.assertEqual(set(manifest["runtime"]), set(up.source_runtime_files(REPO)))


if __name__ == "__main__":
    unittest.main()
