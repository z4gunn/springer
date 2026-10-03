"""claim-run.py: the single-writer lock with a heartbeat."""

import contextlib
import io
import tempfile
import unittest

from helpers import SCRIPTS, RunStore, load_script

cr = load_script(SCRIPTS / "claim-run.py")


class ClaimRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = RunStore(self.tmp.name)
        self.run_dir = str(self.store.run_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cmd(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cr.main(["claim-run.py", self.run_dir, *args])
        return code, out.getvalue()

    def test_claim_creates_the_lock(self):
        code, _ = self.run_cmd("claim", "s1")
        self.assertEqual(code, 0)
        lock, alive = cr.lock_state(self.run_dir)
        self.assertEqual(lock["session_id"], "s1")
        self.assertTrue(alive)

    def test_reclaim_by_the_holder_refreshes_the_heartbeat(self):
        self.store.set_lock("s1", seconds_ago=10 * 60)
        code, _ = self.run_cmd("claim", "s1")
        self.assertEqual(code, 0)
        self.assertTrue(cr.lock_state(self.run_dir)[1])

    def test_claim_against_another_live_session_fails(self):
        self.store.set_lock("s1")
        code, out = self.run_cmd("claim", "s2")
        self.assertEqual(code, 1)
        self.assertIn("s1", out)
        self.assertEqual(cr.read_lock(self.run_dir)["session_id"], "s1")

    def test_stale_lock_is_taken_over(self):
        self.store.set_lock("s1", seconds_ago=31 * 60)
        code, _ = self.run_cmd("claim", "s2")
        self.assertEqual(code, 0)
        self.assertEqual(cr.read_lock(self.run_dir)["session_id"], "s2")

    def test_release_by_holder_removes_the_lock(self):
        self.store.set_lock("s1")
        code, _ = self.run_cmd("release", "s1")
        self.assertEqual(code, 0)
        self.assertIsNone(cr.read_lock(self.run_dir))

    def test_release_by_another_live_session_is_refused(self):
        self.store.set_lock("s1")
        code, _ = self.run_cmd("release", "s2")
        self.assertEqual(code, 1)
        self.assertIsNotNone(cr.read_lock(self.run_dir))

    def test_release_of_a_stale_lock_is_allowed(self):
        self.store.set_lock("s1", seconds_ago=31 * 60)
        code, _ = self.run_cmd("release", "s2")
        self.assertEqual(code, 0)
        self.assertIsNone(cr.read_lock(self.run_dir))

    def test_status_reports_without_changing_anything(self):
        self.store.set_lock("s1")
        code, out = self.run_cmd("status")
        self.assertEqual(code, 0)
        self.assertIn('"holder_alive": true', out)

    def test_corrupt_lock_file_is_treated_as_absent(self):
        self.store.write_raw(".lock", "{")
        self.assertEqual(self.run_cmd("claim", "s1")[0], 0)

    def test_usage_errors(self):
        self.assertEqual(cr.main(["claim-run.py", self.run_dir, "bogus"]), 2)
        self.assertEqual(cr.main(["claim-run.py", self.run_dir, "claim"]), 2)


if __name__ == "__main__":
    unittest.main()
