"""pin-learnings.py: a deterministic hash set over retrospective artifacts."""

import json
import tempfile
import unittest
from pathlib import Path

from helpers import SCRIPTS, header, load_script

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


if __name__ == "__main__":
    unittest.main()
