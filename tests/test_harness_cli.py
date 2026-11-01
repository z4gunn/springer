"""The springer command against real background daemon processes: one command from any
directory, one daemon however many terminals open it, and a clean stop."""

import json
import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path

from harness_support import git_project

try:
    import uvicorn  # noqa: F401
    HAVE_DEPS = True
except ImportError:
    HAVE_DEPS = False

if HAVE_DEPS:
    from springer_harness import cli
    from springer_harness.state.brief import BriefStore


@unittest.skipUnless(HAVE_DEPS, "the harness dependencies are not installed")
class DaemonLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(lambda: cli.stop_daemon(self.home))

    def test_it_starts_a_daemon_that_outlives_the_call(self):
        record = cli.ensure_daemon(self.home)
        self.assertEqual(cli.running(self.home)["pid"], record["pid"])
        self.assertTrue((self.home / "api-token").exists())

    def test_a_second_call_reuses_the_running_daemon(self):
        self.assertEqual(cli.ensure_daemon(self.home)["pid"], cli.ensure_daemon(self.home)["pid"])

    def test_two_terminals_at_once_get_one_daemon(self):
        pids = []
        threads = [threading.Thread(target=lambda: pids.append(cli.ensure_daemon(self.home)["pid"])) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(set(pids)), 1)

    def test_a_stale_record_from_a_crash_starts_a_fresh_daemon(self):
        self.home.mkdir(parents=True)
        (self.home / "daemon.json").write_text(json.dumps({"port": 1, "pid": 999999}))
        self.assertIsNone(cli.running(self.home))
        self.assertNotEqual(cli.ensure_daemon(self.home)["pid"], 999999)

    def test_stop_ends_it_and_says_when_there_was_nothing_to_stop(self):
        cli.ensure_daemon(self.home)
        self.assertTrue(cli.stop_daemon(self.home))
        self.assertIsNone(cli.running(self.home))
        self.assertFalse(cli.stop_daemon(self.home))

    def test_it_runs_from_any_directory(self):
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(self.tmp.name)
        self.assertTrue(cli.ensure_daemon(self.home))

    def test_a_taken_default_port_is_not_a_failure(self):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", cli.DEFAULT_PORT))
            except OSError:
                pass
            sock.listen(1)
            record = cli.ensure_daemon(self.home)
            self.assertNotEqual(record["port"], cli.DEFAULT_PORT)

    def test_leaving_with_nothing_running_stops_the_daemon(self):
        cli.ensure_daemon(self.home)
        self.assertEqual(cli.leave(self.home), "Springer closed.")
        self.assertIsNone(cli.running(self.home))

    def test_leaving_with_a_run_in_progress_keeps_the_daemon_and_says_so(self):
        project = git_project(Path(self.tmp.name) / "acme")
        cli.ensure_daemon(self.home)
        BriefStore(project).create("Acme")
        (self.home / "projects.json").write_text(json.dumps({"acme": {
            "slug": "acme", "name": "Acme", "path": str(project), "archived": False}}))
        run_dir = project / "runs" / "acme-1"
        run_dir.mkdir(parents=True)
        (run_dir / "run-brief.json").write_text(json.dumps({"content": {"kind": "build"}}))
        message = cli.leave(self.home)
        self.assertIn("acme-1", message)
        self.assertIn("Run springer to come back", message)
        self.assertTrue(cli.running(self.home), "the run keeps going without the window")

    def test_home_comes_from_the_environment_when_set(self):
        os.environ["SPRINGER_HOME"] = "/tmp/spgr-elsewhere"
        self.addCleanup(os.environ.pop, "SPRINGER_HOME", None)
        self.assertEqual(cli.default_home(), Path("/tmp/spgr-elsewhere"))


if __name__ == "__main__":
    unittest.main()
