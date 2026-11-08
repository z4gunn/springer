"""The daemon as a launchd agent, so it comes back after a crash or a reboot without a
person at the machine. KeepAlive restarts it whenever it exits, and RunAtLoad starts it
at login. The agent runs the same module springer runs, from the same source, with the
PATH of the shell that installed it, because a session needs the coding agent on PATH.

SPRINGER_LAUNCH_AGENTS moves the agents folder, so a test never writes into the real
home.
"""

import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "dev.springer.daemon"
DEFAULT_PORT = 7337


def agents_dir():
    return Path(os.environ.get("SPRINGER_LAUNCH_AGENTS") or Path.home() / "Library" / "LaunchAgents")


def plist_path():
    return agents_dir() / f"{LABEL}.plist"


def installed():
    return plist_path().exists()


def _domain():
    return f"gui/{os.getuid()}"


def definition(home, port=DEFAULT_PORT):
    home = Path(home)
    package_parent = str(Path(__file__).resolve().parents[1])
    return {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, "-m", "springer_harness.cli", "daemon", "--home", str(home),
                             "--port", str(port)],
        "EnvironmentVariables": {"PYTHONPATH": package_parent, "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                                 "SPRINGER_SERVICE": "1"},
        "WorkingDirectory": str(home),
        "RunAtLoad": True,
        "KeepAlive": True,
        # A daemon that fails at once is not restarted in a tight loop.
        "ThrottleInterval": 30,
        "StandardOutPath": str(home / "daemon.log"),
        "StandardErrorPath": str(home / "daemon.log"),
    }


def kickstart(run=subprocess.run):
    """Ask launchd to start the agent now, when it is not running."""
    return run(["launchctl", "kickstart", f"{_domain()}/{LABEL}"], capture_output=True, text=True).returncode == 0


def service(home, action, run=subprocess.run, running=None, out=print):
    """springer service install, uninstall, or status. Returns the exit code."""
    home = Path(home)
    if running is None:
        from .cli import running as running_check
        running = running_check
    path = plist_path()
    if action == "install":
        if running(home) and not installed():
            out("A daemon is already running outside the service. Stop it first when no session is running "
                "(springer stop, or /springer restart from Slack), then install.")
            return 1
        home.mkdir(parents=True, exist_ok=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        if installed():
            run(["launchctl", "bootout", f"{_domain()}/{LABEL}"], capture_output=True, text=True)
        path.write_bytes(plistlib.dumps(definition(home)))
        done = run(["launchctl", "bootstrap", _domain(), str(path)], capture_output=True, text=True)
        if done.returncode:
            out(f"Wrote {path}, but launchd refused it: {(done.stderr or done.stdout).strip()}")
            return 1
        out(f"Installed. launchd keeps the daemon running and starts it at login. Logs: {home / 'daemon.log'}")
        return 0
    if action == "uninstall":
        if not installed():
            out("The service is not installed.")
            return 0
        run(["launchctl", "bootout", f"{_domain()}/{LABEL}"], capture_output=True, text=True)
        path.unlink()
        out("Uninstalled. The daemon stopped with it. springer starts one again when you open it.")
        return 0
    if action == "status":
        loaded = run(["launchctl", "print", f"{_domain()}/{LABEL}"], capture_output=True, text=True).returncode == 0
        record = running(home)
        out(f"installed: {'yes' if installed() else 'no'}, loaded: {'yes' if loaded else 'no'}, "
            f"daemon: {'up on port ' + str(record['port']) if record else 'down'}")
        return 0
    out(f"Unknown action {action}. Use install, uninstall, or status.")
    return 2
