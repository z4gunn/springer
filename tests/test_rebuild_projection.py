"""rebuild-projection.py: run-state is a cache rebuilt from the cycle log.
The cycle-derived fields come from the log every time, the board and the
pinned learnings are carried forward, and the result validates."""

import contextlib
import io
import json
import tempfile
import unittest

from helpers import SCHEMAS, SCRIPTS, RunStore, load_script

rp = load_script(SCRIPTS / "rebuild-projection.py")

try:
    import jsonschema  # noqa: F401
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False


class RebuildProjectionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = RunStore(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_log_starts_at_discovery(self):
        content = rp.rebuild(self.store.run_dir)["content"]
        self.assertEqual(content["cycle_counter"], 0)
        self.assertEqual(content["generated_from_cycle"], 0)
        self.assertEqual(content["active_phase"], "discovery")
        self.assertTrue(content["regenerable"])

    def test_cycle_fields_are_replayed_from_the_log(self):
        self.store.add_cycle("requirements", "architecture")
        self.store.add_cycle("architecture", "design")
        content = rp.rebuild(self.store.run_dir)["content"]
        self.assertEqual(content["cycle_counter"], 2)
        self.assertEqual(content["generated_from_cycle"], 2)
        self.assertEqual(content["active_phase"], "design")

    def test_open_gates_and_escalations_are_listed(self):
        self.store.add_gate("HIL-0001", "pr-merge")
        self.store.add_gate("HIL-0002", "pr-merge", answered=True)
        self.store.add_escalation("ESC-0001", "open")
        self.store.add_escalation("ESC-0002", "resolved")
        content = rp.rebuild(self.store.run_dir)["content"]
        self.assertEqual(content["open_gates"], ["HIL-0001"])
        self.assertEqual(content["open_escalations"], ["ESC-0001"])

    def test_archive_is_ignored(self):
        self.store.add_gate("HIL-0009", "pr-merge", subdir="archive")
        self.assertEqual(rp.rebuild(self.store.run_dir)["content"]["open_gates"], [])

    def test_board_and_learnings_carry_forward(self):
        board = {"backlog": ["S-2"], "development": ["S-1"], "review": [],
                 "validation": [], "done": []}
        self.store.set_state(wip_board=board, learnings=[{"retrospective_ref": "r", "hash": "h"}])
        content = rp.rebuild(self.store.run_dir)["content"]
        self.assertEqual(content["wip_board"], board)
        self.assertEqual(content["learnings_pinned"][0]["retrospective_ref"], "r")

    def test_profile_comes_from_the_brief(self):
        self.assertEqual(rp.rebuild(self.store.run_dir)["content"]["profile"], "brochure")

    def test_main_writes_run_state(self):
        self.store.add_cycle()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = rp.main(["rebuild-projection.py", str(self.store.run_dir)])
        self.assertEqual(code, 0)
        written = json.loads((self.store.run_dir / "run-state.json").read_text())
        self.assertEqual(written["artifact_type"], "run-state")
        self.assertEqual(written["content"]["cycle_counter"], 1)

    @unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed in this interpreter")
    def test_rebuilt_state_validates_against_the_schema(self):
        self.store.add_cycle()
        self.store.add_gate("HIL-0001", "pr-merge", holds=["S-1"])
        validate = load_script(SCHEMAS / "validate.py")
        artifact = rp.rebuild(self.store.run_dir)
        issues = validate._validate_object(artifact, validate.load_registry())
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
