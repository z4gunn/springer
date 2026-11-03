"""The springer command. With no arguments it opens the TUI from any directory, and
starts the daemon in the background first when none is running. The daemon outlives
the TUI, because a run keeps going after the window closes. Onboarding lands later and
will install the daemon as a service.
"""

import argparse
import fcntl
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .build import build_id

DEFAULT_PORT = 7337
START_TIMEOUT_SECONDS = 45


def default_home():
    return Path(os.environ.get("SPRINGER_HOME") or Path.home() / ".springer")


def _record(home):
    try:
        return json.loads((Path(home) / "daemon.json").read_text())
    except (OSError, ValueError):
        return None


def running(home):
    """The daemon's record when it answers on the port it wrote. A stale record, left
    by a crash or a reboot, or some other program on that port, does not count."""
    record = _record(home)
    if not record:
        return None
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{record['port']}/v1/health", timeout=1) as response:
            body = json.loads(response.read())
    except (OSError, ValueError, KeyError, urllib.error.URLError):
        return None
    return {**record, "build": body.get("build")} if body.get("status") == "ok" and body.get("api_version") else None


def _free_port():
    """The usual port, or any free one when something else already holds it."""
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", DEFAULT_PORT))
            return DEFAULT_PORT
        except OSError:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]


def ensure_daemon(home):
    """Return a running daemon's record, starting one if needed. A file lock means two
    terminals opening springer at once get one daemon and not two."""
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    with open(home / "daemon.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        record = running(home)
        if record and record["build"] == build_id():
            return record
        if record:
            # Code the TUI knows and the daemon does not fails in confusing ways, so the
            # daemon is replaced. Its sessions are recovered at the next start, with no
            # retry spent.
            stop_daemon(home)
        log_path = home / "daemon.log"
        package_parent = str(Path(__file__).resolve().parents[1])
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [package_parent, os.environ.get("PYTHONPATH")]))}
        with open(log_path, "a") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "springer_harness.cli", "daemon", "--home", str(home), "--port", str(_free_port())],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log, cwd=home, env=env, start_new_session=True)
        deadline = time.time() + START_TIMEOUT_SECONDS
        while time.time() < deadline:
            record = running(home)
            if record:
                return record
            if process.poll() is not None:
                break
            time.sleep(0.1)
        tail = log_path.read_text()[-600:] if log_path.exists() else ""
        raise RuntimeError(f"the daemon did not start. See {log_path}\n{tail}")


def stop_daemon(home):
    """Returns True when a daemon was running and has been asked to stop. In-flight
    sessions die with it, and recovery redispatches them at the next start."""
    record = running(home)
    if not record:
        return False
    os.kill(record["pid"], signal.SIGTERM)
    deadline = time.time() + 5
    while time.time() < deadline and running(home):
        time.sleep(0.1)
    if running(home):
        os.kill(record["pid"], signal.SIGKILL)
    return True


def build_daemon(home):
    """Claude Code and GitHub once onboarded. Before that, the mock provider serves a
    canned run, so springer can be tried with no tokens spent."""
    from .daemon import Daemon
    from .providers.secrets import KeyringSecrets
    from .setup import load_config

    config = load_config(home)
    if config is None:
        from .providers.mock import MockProvider, MockSourceHost
        from .providers.mock_scenario import demo_planner_factory, demo_script

        host = MockSourceHost()
        return Daemon(home, MockProvider(demo_script()), host, demo_planner_factory(), KeyringSecrets(),
                      time.time, local_host=host)
    from .providers.claude_code import ClaudeCodeProvider
    from .providers.github import GitHubSourceHost
    from .scheduler.orchestrator import orchestrator_factory

    holder = {}

    def project_path_of(slug):
        return holder["daemon"].project_path(slug)

    daemon = Daemon(home, ClaudeCodeProvider(config["claude"]), GitHubSourceHost(project_path_of),
                    orchestrator_factory(project_path_of, config["claude"]), KeyringSecrets(), time.time,
                    maximum=int(config["max_sessions"]))
    daemon.config = config
    holder["daemon"] = daemon
    return daemon


def serve(home, port):
    """Run the daemon in this process, on the loopback interface."""
    import uvicorn

    from .api.app import create_app

    daemon = build_daemon(home)
    app = create_app(daemon)
    daemon.home.write_port(port)
    daemon.start()
    if daemon.config is not None:
        from .notify.notifier import start_notifications
        start_notifications(daemon, app.state.operations)
    # A TUI's open event stream must not hold the daemon's shutdown.
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", timeout_graceful_shutdown=1)
    return 0


def open_tui(home):
    from .tui.app import SpringerApp
    from .tui.client import ApiClient

    try:
        ensure_daemon(home)
        client = ApiClient.from_home(home)
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        sys.stderr.write(f"springer: {exc}\n")
        return 1
    SpringerApp(client).run()
    print(leave(home))
    return 0


def active_runs(home):
    """Each run still in progress, from the daemon's own API."""
    record = running(home)
    if not record:
        return []
    token = (Path(home) / "api-token").read_text().strip()
    request = urllib.request.Request(f"http://127.0.0.1:{record['port']}/v1/projects",
                                     headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=5) as response:
        projects = json.loads(response.read())
    return [p["active_run"] for p in projects if p["active_run"] and not p["archived"]]


def leave(home):
    """Closing the TUI. A run keeps going without the window, which is the point of a
    daemon, so it stays up and says so. With nothing to do it stops, so nothing lingers."""
    try:
        runs = active_runs(home)
    except (OSError, ValueError, urllib.error.URLError):
        return "Springer closed."
    if not runs:
        stop_daemon(home)
        return "Springer closed."
    waiting = sum(run["open_gates"] for run in runs)
    note = f", {waiting} waiting on you" if waiting else ""
    names = ", ".join(run["run_id"] for run in runs)
    return f"Springer closed. Still running in the background: {names}{note}. Run springer to come back."


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(prog="springer", description="Open the Springer TUI, starting the daemon if needed.")
    parser.add_argument("--home", default=None, help="harness state directory, default ~/.springer")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("stop", help="stop the background daemon")
    onboard_cmd = sub.add_parser("onboard", help="set up the coding agent, the source host, and the daemon, once")
    onboard_cmd.add_argument("--yes", action="store_true", help="take every default without asking")
    sub.add_parser("doctor", help="check the setup and repair what is safe to repair")
    notes = sub.add_parser("notifications", help="send gates to Slack and answer them from your phone")
    notes.add_argument("action", nargs="?", default="setup", choices=("setup", "test", "manifest", "off"))
    run_daemon = sub.add_parser("daemon", help="run the daemon in the foreground")
    run_daemon.add_argument("--home", dest="daemon_home", default=None)
    run_daemon.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    home = args.home or getattr(args, "daemon_home", None) or default_home()
    if args.command == "daemon":
        return serve(home, args.port)
    if args.command == "onboard":
        from .setup import onboard
        return onboard(home, assume_yes=args.yes)
    if args.command == "doctor":
        from .setup import doctor
        return doctor(home)
    if args.command == "notifications":
        from .notify.setup import notifications
        return notifications(home, args.action)
    if args.command == "stop":
        stopped = stop_daemon(home)
        print("springer: daemon stopped." if stopped else "springer: no daemon is running.")
        return 0
    return open_tui(home)


if __name__ == "__main__":
    sys.exit(main())
