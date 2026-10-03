"""scripts/validate-repo.py: the mechanical half of the per-artifact checklist.
The repo itself must pass, and a fixture tree with one violation per rule
must report each one by name."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from helpers import REPO, load_script

vr = load_script(REPO / "scripts" / "validate-repo.py")

GOOD_SKILL = """---
name: {name}
description: Produce a thing from an input. Use when a test needs a valid skill.
---

# {name}

Do the thing.
"""

GOOD_AGENT = """---
name: {name}
description: Reviews things. Use when a test needs a valid agent.
tools: Read, Grep, Glob
model: sonnet
---

You are a test agent.

A skill name like spgr-read-artifact refers to the procedure at `.claude/skills/<name>/SKILL.md`. Read it first.

## Workflow
1. Do the step.
"""


def run_validator(root):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = vr.main(["validate-repo.py", str(root)])
    return code, out.getvalue()


class ValidateRepoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude" / "skills").mkdir(parents=True)
        (self.root / ".claude" / "agents").mkdir(parents=True)
        (self.root / ".claude" / "references").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def skill(self, name, text=None):
        d = self.root / ".claude" / "skills" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(text if text is not None else GOOD_SKILL.format(name=name))
        return d

    def agent(self, name, text=None):
        p = self.root / ".claude" / "agents" / f"{name}.md"
        p.write_text(text if text is not None else GOOD_AGENT.format(name=name))
        return p

    def test_the_real_repo_is_clean(self):
        code, out = run_validator(REPO)
        self.assertEqual(code, 0, out)

    def test_clean_fixture_passes(self):
        self.skill("spgr-a")
        self.agent("spgr-agent-a")
        code, out = run_validator(self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("clean", out)

    def test_extra_frontmatter_key_fails(self):
        self.skill("spgr-a", GOOD_SKILL.format(name="spgr-a").replace("---\n\n#", "tools: Read\n---\n\n#"))
        code, out = run_validator(self.root)
        self.assertEqual(code, 1)
        self.assertIn("skill-frontmatter", out)
        self.assertIn("exactly name, description", out)

    def test_name_mismatch_fails(self):
        self.skill("spgr-a", GOOD_SKILL.format(name="spgr-b"))
        self.assertIn("does not match the directory", run_validator(self.root)[1])

    def test_long_description_fails(self):
        long = GOOD_SKILL.format(name="spgr-a").replace("Use when a test needs a valid skill.",
                                                         "Use when " + "x" * 360)
        self.skill("spgr-a", long)
        self.assertIn("skill-description", run_validator(self.root)[1])

    def test_long_body_fails(self):
        self.skill("spgr-a", GOOD_SKILL.format(name="spgr-a") + "line\n" * 500)
        self.assertIn("skill-body", run_validator(self.root)[1])

    def test_auxiliary_file_fails(self):
        d = self.skill("spgr-a")
        (d / "README.md").write_text("no")
        self.assertIn("skill-extras", run_validator(self.root)[1])

    def test_nested_reference_dir_fails(self):
        d = self.skill("spgr-a")
        (d / "references" / "deeper").mkdir(parents=True)
        self.assertIn("one level deep", run_validator(self.root)[1])

    def test_long_reference_without_contents_fails(self):
        d = self.skill("spgr-a")
        (d / "references").mkdir()
        (d / "references" / "big.md").write_text("# Big\n" + "text\n" * 120)
        self.assertIn("without a Contents section", run_validator(self.root)[1])
        (d / "references" / "big.md").write_text("# Big\n\n## Contents\n- a\n" + "text\n" * 120)
        self.assertEqual(run_validator(self.root)[0], 0)

    def test_agent_missing_model_fails(self):
        self.agent("spgr-agent-a", GOOD_AGENT.format(name="spgr-agent-a").replace("model: sonnet\n", ""))
        out = run_validator(self.root)[1]
        self.assertIn("agent-frontmatter", out)
        self.assertIn("missing model", out)

    def test_agent_bad_model_fails(self):
        self.agent("spgr-agent-a", GOOD_AGENT.format(name="spgr-agent-a").replace("model: sonnet", "model: gpt"))
        self.assertIn("agent-model", run_validator(self.root)[1])

    def test_agent_without_skill_path_sentence_fails(self):
        text = GOOD_AGENT.format(name="spgr-agent-a").replace("`.claude/skills/<name>/SKILL.md`", "somewhere")
        self.agent("spgr-agent-a", text)
        self.assertIn("agent-skill-path", run_validator(self.root)[1])

    def test_em_dash_anywhere_fails(self):
        self.skill("spgr-a", GOOD_SKILL.format(name="spgr-a") + "\nA line — with a dash.\n")
        out = run_validator(self.root)[1]
        self.assertIn("voice", out)
        self.assertIn("em-dash at line", out)

    def test_shared_reference_needs_contents_when_long(self):
        (self.root / ".claude" / "references" / "big.md").write_text("# Big\n" + "t\n" * 120)
        self.assertIn("references (1)", run_validator(self.root)[1])


if __name__ == "__main__":
    unittest.main()
