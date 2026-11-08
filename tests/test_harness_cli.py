"""The springer command against real background daemon processes: one command from any
directory, one daemon however many terminals open it, and a clean stop."""

import json
import os
import socket
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

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

    def test_a_daemon_running_older_code_is_replaced(self):
        first = cli.ensure_daemon(self.home)
        with mock.patch.object(cli, "build_id", return_value="newer-code"):
            second = cli.ensure_daemon(self.home)
        self.assertNotEqual(second["pid"], first["pid"])
        self.assertEqual(cli.running(self.home)["pid"], second["pid"])

    def test_a_daemon_with_a_stream_open_still_stops(self):
        record = cli.ensure_daemon(self.home)
        token = (self.home / "api-token").read_text().strip()
        request = urllib.request.Request(f"http://127.0.0.1:{record['port']}/v1/events",
                                         headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(request, timeout=5):
            self.assertTrue(cli.stop_daemon(self.home))
            self.assertIsNone(cli.running(self.home))

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


@unittest.skipUnless(HAVE_DEPS, "the harness dependencies are not installed")
class PolishCommandTest(unittest.TestCase):
    """springer polish and springer tail: one fix from a terminal, which the daemon drives."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(lambda: cli.stop_daemon(self.home))
        self.project = git_project(Path(self.tmp.name) / "acme")
        BriefStore(self.project).create("Acme")
        (self.home).mkdir(parents=True)
        (self.home / "projects.json").write_text(json.dumps({"acme": {
            "slug": "acme", "name": "Acme", "path": str(self.project), "archived": False}}))

    def run_cli(self, *args):
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(cli, "_interactive", return_value=False):
            code = cli.main(["--home", str(self.home), *args])
        return code, out.getvalue()

    def test_polish_starts_a_run_then_offers_a_bug_when_the_project_is_busy(self):
        code, text = self.run_cli("polish", "The footer link is wrong", "--project", "acme", "--no-follow")
        self.assertEqual((code, "Started acme-1 on acme: The footer link is wrong" in text), (0, True), text)
        brief = json.loads((self.project / "runs" / "acme-1" / "run-brief.json").read_text())["content"]
        self.assertEqual((brief["lane"], brief["issue"]), ("polish", "The footer link is wrong"))
        self.assertEqual(len(brief["story_ids"]), 1)
        code, text = self.run_cli("polish", "Also the hero", "--project", "acme", "--no-follow")
        self.assertEqual(code, 1)
        self.assertIn("acme has acme-1 in progress", text)
        self.assertIn("--as-bug", text)
        code, text = self.run_cli("polish", "Also the hero", "--project", "acme", "--as-bug")
        self.assertEqual(code, 0, text)
        self.assertRegex(text, r"Filed BUG-\d{4}-\d+ on acme's backlog")
        self.assertIn("Also the hero", (self.project / "runs" / "_backlog.json").read_text())

    def test_polish_finds_the_project_from_a_directory_inside_it(self):
        inside = self.project / "src" / "deep"
        inside.mkdir(parents=True)
        self.assertEqual(cli.project_for(self.home, inside), "acme")
        with self.assertRaises(RuntimeError):
            cli.project_for(self.home, Path(self.tmp.name))
        self.assertEqual(cli.project_of_run(self.home, "acme-discovery-2"), "acme")

    def test_tail_follows_a_run_in_the_feeds_wording_and_stops_at_a_gate(self):
        self.assertEqual(cli.tail_line({"ts": "2026-11-07T10:11:12Z", "event": "unit_state", "to": "running",
                                        "unit_id": "U-0001"}), "10:11:12  U-0001 started")
        gate = {"ts": "2026-11-07T10:12:00Z", "event": "gate_opened", "gate_id": "G-0001"}
        self.assertIn("gate G-0001 is open. Answer it in Slack", cli.tail_line(gate))
        self.assertTrue(cli.tail_stops(gate) and cli.tail_stops({"event": "cleaned_up"}))
        self.assertFalse(cli.tail_stops({"event": "unit_state", "to": "running"}))
        self.assertIsNone(cli.tail_line({"event": "heartbeat"}))
        code, text = self.run_cli("polish", "Tidy the footer", "--project", "acme", "--no-follow")
        self.assertEqual(code, 0, text)
        code, text = self.run_cli("tail", "acme-1", "--timeout", "4")
        self.assertEqual(code, 0)
        self.assertIn("following acme-1. Ctrl-C leaves it running.", text)
        code, text = self.run_cli("tail", "nowhere-1")
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
