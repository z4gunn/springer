"""pin-learnings.py: a deterministic hash set over retrospective artifacts."""

import json
import tempfile
import unittest
from pathlib import Path

from helpers import SCHEMAS, SCRIPTS, header, load_script

try:
    import jsonschema  # noqa: F401
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

pl = load_script(SCRIPTS / "pin-learnings.py")


class PinLearningsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def retro(self, artifact_id, learning):
        obj = header(artifact_id, "run-retrospective", "retro")
        obj["content"] = {"run_id": "x", "learnings": [learning]}
        path = self.dir / f"{artifact_id}.json"
        path.write_text(json.dumps(obj))
        return path

    def test_order_is_by_ref_not_argv(self):
        b = self.retro("RETRO-b", "two")
        a = self.retro("RETRO-a", "one")
        pinned = pl.pin([str(b), str(a)])
        self.assertEqual([p["retrospective_ref"] for p in pinned], ["RETRO-a", "RETRO-b"])
        self.assertTrue(all(p["hash"].startswith("sha256:") for p in pinned))

    def test_hash_changes_with_content(self):
        a = self.retro("RETRO-a", "one")
        first = pl.pin([str(a)])[0]["hash"]
        self.retro("RETRO-a", "changed")
        self.assertNotEqual(first, pl.pin([str(a)])[0]["hash"])

    def test_non_retrospective_is_rejected(self):
        obj = header("prd-1", "prd", "prd")
        path = self.dir / "prd.json"
        path.write_text(json.dumps(obj))
        with self.assertRaises(ValueError):
            pl.pin([str(path)])
        self.assertEqual(pl.main(["pin-learnings.py", str(path)]), 1)


@unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed in this interpreter")
class RetrospectiveRemedyTest(unittest.TestCase):
    """A learning names where its fix lands: a check names the script that
    will catch the mistake, and reference text names the rule it displaces."""

    def learning(self, **extra):
        base = {"learning_id": "L-1", "category": "audit-pattern", "observation": "a unit skipped the suite",
                "recommendation": "catch it", "confidence": "proposed", "requires_human_promotion": False}
        return dict(base, **extra)

    def issues(self, learning):
        validate = load_script(SCHEMAS / "validate.py")
        obj = header("RETRO-1", "run-retrospective", "retro")
        obj["content"] = {"retrospective_id": "RETRO-1", "run_id": "r1", "run_outcome": "completed",
                          "learnings": [learning]}
        return validate._validate_object(obj, validate.load_registry())

    def test_remedies(self):
        self.assertEqual(self.issues(self.learning()), [])
        self.assertEqual(self.issues(self.learning(remedy="check", remedy_target="receipt.py zero-run")), [])
        self.assertTrue(self.issues(self.learning(remedy="check")))
        self.assertTrue(self.issues(self.learning(remedy="reference")))
        self.assertEqual(self.issues(self.learning(remedy="reference", displaces="Fold-in policy, line 3")), [])
        self.assertTrue(self.issues(self.learning(remedy="maybe")))


if __name__ == "__main__":
    unittest.main()
