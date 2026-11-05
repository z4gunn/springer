"""springer service: the daemon as a launchd agent. launchctl is faked and the agents
folder is a temporary one, so nothing here touches the real home or launchd."""

import os
import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401, points SPRINGER_LAUNCH_AGENTS away from the real home
import harness_support  # noqa: F401, puts the harness package on the path


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.agents = Path(self.tmp.name) / "agents"
        self.previous = os.environ.get("SPRINGER_LAUNCH_AGENTS")
        os.environ["SPRINGER_LAUNCH_AGENTS"] = str(self.agents)
        self.addCleanup(lambda: os.environ.__setitem__("SPRINGER_LAUNCH_AGENTS", self.previous or ""))
        self.home = Path(self.tmp.name) / "home"
        self.calls = []

    def launchctl(self, command, **kwargs):
        self.calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    def test_install_writes_a_kept_alive_agent_and_uninstall_removes_it(self):
        from springer_harness import service
        lines = []
        self.assertEqual(service.service(self.home, "install", run=self.launchctl, running=lambda h: None,
                                         out=lines.append), 0)
        plist = plistlib.loads(service.plist_path().read_bytes())
        self.assertTrue(str(service.plist_path()).startswith(str(self.agents)), "never the real home")
        self.assertEqual((plist["KeepAlive"], plist["RunAtLoad"], plist["Label"]), (True, True, service.LABEL))
        self.assertEqual(plist["ProgramArguments"][-4:], ["--home", str(self.home), "--port", "7337"])
        self.assertEqual(plist["StandardOutPath"], str(self.home / "daemon.log"))
        self.assertEqual(plist["EnvironmentVariables"]["SPRINGER_SERVICE"], "1")
        self.assertEqual(self.calls[-1][:2], ["launchctl", "bootstrap"])
        service.service(self.home, "status", run=self.launchctl, running=lambda h: {"port": 7337}, out=lines.append)
        self.assertIn("installed: yes", lines[-1])
        self.assertEqual(service.service(self.home, "uninstall", run=self.launchctl, running=lambda h: None,
                                         out=lines.append), 0)
        self.assertFalse(service.plist_path().exists())
        self.assertEqual(self.calls[-1][:2], ["launchctl", "bootout"])

    def test_install_refuses_while_a_daemon_runs_outside_it(self):
        from springer_harness import service
        lines = []
        self.assertEqual(service.service(self.home, "install", run=self.launchctl, running=lambda h: {"port": 1},
                                         out=lines.append), 1)
        self.assertFalse(service.plist_path().exists())
        self.assertIn("Stop it first", lines[-1])


class DaemonUnderServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        previous = os.environ.get("SPRINGER_LAUNCH_AGENTS")
        os.environ["SPRINGER_LAUNCH_AGENTS"] = str(Path(self.tmp.name) / "agents")
        self.addCleanup(lambda: os.environ.__setitem__("SPRINGER_LAUNCH_AGENTS", previous or ""))

    def test_open_waits_for_the_service_and_starts_no_second_daemon(self):
        from springer_harness import cli, service
        service.plist_path().parent.mkdir(parents=True)
        service.plist_path().write_bytes(b"installed")
        up = {"port": 7337, "pid": 2, "build": cli.build_id()}
        answers = iter([None, None, up])
        with mock.patch.object(cli, "running", side_effect=lambda home: next(answers, up)), \
                mock.patch.object(service, "kickstart", return_value=True) as kick, \
                mock.patch.object(cli.subprocess, "Popen") as popen:
            self.assertEqual(cli.ensure_daemon(self.home), up)
        popen.assert_not_called()
        kick.assert_called_once()

    def test_a_restart_leaves_a_helper_unless_launchd_keeps_the_daemon_alive(self):
        from springer_harness import cli
        for service_env, helpers_expected in (("", 1), ("1", 0)):
            with self.subTest(service=service_env), mock.patch.dict(os.environ, {"SPRINGER_SERVICE": service_env}), \
                    mock.patch.object(cli.subprocess, "Popen") as popen, mock.patch.object(cli.os, "kill") as kill:
                cli.restart_process(self.home)
                self.assertEqual(popen.call_count, helpers_expected)
                if helpers_expected:
                    self.assertIn("respawn", popen.call_args.args[0])
                kill.assert_called_once_with(os.getpid(), cli.signal.SIGTERM)
