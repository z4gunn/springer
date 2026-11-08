"""The springer command. With no arguments it opens the TUI from any directory, and
starts the daemon in the background first when none is running. The daemon outlives
the TUI, because a run keeps going after the window closes. springer service install
puts it under launchd, which restarts it after a crash or a reboot.
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
import uuid
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
        from . import service
        if service.installed():
            # launchd owns the daemon. A second one started here would fight it for the port.
            return _wait_for_service(home, service)
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


def _wait_for_service(home, service):
    service.kickstart()
    deadline = time.time() + START_TIMEOUT_SECONDS
    while time.time() < deadline:
        record = running(home)
        if record and record["build"] == build_id():
            return record
        time.sleep(0.2)
    raise RuntimeError(f"the service did not bring the daemon up. See {Path(home) / 'daemon.log'} "
                       "and springer service status")


def restart_process(home):
    """Replace this daemon process. Under launchd, exiting is enough, because the agent
    is kept alive. Otherwise a detached helper starts the next daemon once this one is
    gone. Either way this process stops through its own clean shutdown."""
    if not os.environ.get("SPRINGER_SERVICE"):
        package_parent = str(Path(__file__).resolve().parents[1])
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [package_parent, os.environ.get("PYTHONPATH")]))}
        with open(Path(home) / "daemon.log", "a") as log:
            subprocess.Popen([sys.executable, "-m", "springer_harness.cli", "--home", str(home), "respawn",
                              "--after", str(os.getpid())], stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                             cwd=home, env=env, start_new_session=True)
    os.kill(os.getpid(), signal.SIGTERM)


def respawn(home, after_pid, timeout=120):
    """Wait for the old daemon to exit, then start the next one."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            os.kill(after_pid, 0)
        except OSError:
            break
        time.sleep(0.2)
    ensure_daemon(home)
    return 0


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
    daemon.restart_process = lambda: restart_process(home)
    daemon.start()
    daemon.resume_after_restart()
    if daemon.config is not None:
        from .notify.notifier import start_notifications
        start_notifications(daemon, app.state.operations)
    # A TUI's open event stream must not hold the daemon's shutdown.
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", timeout_graceful_shutdown=1)
    daemon.stop()
    daemon.mark_clean_stop()
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
    from . import service
    if not runs:
        if service.installed():
            return "Springer closed. The service keeps the daemon up."
        stop_daemon(home)
        return "Springer closed."
    waiting = sum(run["open_gates"] for run in runs)
    note = f", {waiting} waiting on you" if waiting else ""
    names = ", ".join(run["run_id"] for run in runs)
    return f"Springer closed. Still running in the background: {names}{note}. Run springer to come back."


# --- polish and tail: one fix from a terminal, which the daemon drives (Modes in pdca-harness) ---


def project_for(home, cwd, slug=None):
    """The registered project a directory is in, or the one named."""
    from .registry import Home

    projects = Home(home).projects()
    if slug:
        if slug not in projects:
            raise RuntimeError(f"no project named {slug}")
        return slug
    here = Path(cwd).resolve()
    for name, record in projects.items():
        root = Path(record["path"]).resolve()
        if here == root or root in here.parents:
            return name
    raise RuntimeError("this directory is not a registered project. Run springer and add it under Projects, "
                       "or name one with --project.")


def project_of_run(home, run_id):
    """Run ids start with their project's slug, so the longest slug that fits names it."""
    from .registry import Home

    slugs = [s for s in Home(home).projects() if run_id.startswith(s + "-")]
    if not slugs:
        raise RuntimeError(f"no project has a run named {run_id}")
    return max(slugs, key=len)


class Api:
    """The commands' client: plain urllib against the daemon the home's files name."""

    def __init__(self, home):
        record = running(home) or ensure_daemon(home)
        self.base = f"http://127.0.0.1:{record['port']}"
        self.headers = {"Authorization": f"Bearer {(Path(home) / 'api-token').read_text().strip()}"}

    def _call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {**self.headers, **({"Content-Type": "application/json"} if data else {})}
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read() or b"null")
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read() or b"{}").get("error") or {}
            except ValueError:
                detail = {}
            raise RuntimeError(detail.get("message") or f"the daemon answered {exc.code}") from exc

    def get(self, path):
        return self._call("GET", path)

    def op(self, kind, args, project, run_id=None):
        """One operation, confirmed when the daemon asks, because the person typed it."""
        body = {"op_id": str(uuid.uuid4()), "type": kind, "project": project, "run_id": run_id, "args": args}
        outcome = self._call("POST", "/v1/operations", body)
        if outcome.get("status") == "needs_confirmation":
            outcome = self._call("POST", "/v1/operations",
                                 {**body, "op_id": str(uuid.uuid4()), "confirm_token": outcome["confirm_token"]})
        return outcome

    def frames(self, path, timeout=None):
        """(event, data) from an event stream until the server closes it, the timeout
        passes, or the reader stops."""
        request = urllib.request.Request(self.base + path, headers=self.headers)
        deadline = time.monotonic() + timeout if timeout else None
        event, data = None, None
        try:
            with urllib.request.urlopen(request, timeout=min(timeout, 30) if timeout else 60) as response:
                for raw in response:
                    line = raw.decode("utf-8", "replace").rstrip("\n")
                    if line.startswith("event: "):
                        event = line[7:]
                    elif line.startswith("data: "):
                        data = json.loads(line[6:])
                    elif not line and event:
                        yield event, data
                        event, data = None, None
                    if deadline and time.monotonic() > deadline:
                        return
        except (TimeoutError, socket.timeout, urllib.error.URLError, ConnectionError):
            return


def tail_line(data):
    """One line of the tail: the time, then the words Slack and the TUI use for the event."""
    from .notify.notifier import feed_line

    if data.get("event") == "gate_opened":
        text = f"gate {data.get('gate_id')} is open. Answer it in Slack, or in the TUI (springer)."
    else:
        text = feed_line(data)
    if not text:
        return None
    return f"{(data.get('ts') or '')[11:19]}  {text}".strip()


def tail_stops(data):
    """The tail ends when the run completes or a gate waits on the person."""
    return data.get("event") in ("gate_opened", "cleaned_up")


def tail(home, run_id, slug=None, timeout=None, out=print):
    """Follow a run's events, in the wording Slack and the TUI use, until it completes or
    a gate opens. Ctrl-C leaves the run going, because the daemon drives it."""
    api = Api(home)
    slug = slug or project_of_run(home, run_id)
    out(f"following {run_id}. Ctrl-C leaves it running.")
    for event, data in api.frames(f"/v1/projects/{slug}/runs/{run_id}/events", timeout):
        if event == "heartbeat":
            if api.get(f"/v1/projects/{slug}/runs/{run_id}").get("complete"):
                out(f"{run_id} is complete.")
                return 0
            continue
        if event == "resync" or not isinstance(data, dict):
            continue
        line = tail_line(data)
        if line:
            out(line)
        if tail_stops(data):
            return 0
    return 0


def _interactive():
    return sys.stdin.isatty()


def polish(home, issue, slug=None, as_bug=False, follow=True, timeout=None, cwd=None, out=print):
    """Start a polish run on one issue in the person's words, for the project in this
    directory. With a run in progress, the issue can go on the backlog as a bug instead,
    which the person decides."""
    issue = issue.strip()
    if not issue:
        raise RuntimeError("say what is wrong, in your own words")
    slug = project_for(home, cwd or os.getcwd(), slug)
    api = Api(home)
    active = (api.get(f"/v1/projects/{slug}").get("active_run") or {}).get("run_id")
    title = issue.splitlines()[0][:120]
    if active:
        if not as_bug and _interactive():
            answer = input(f"{slug} has {active} in progress. File the issue as a bug on the backlog instead? [y/N] ")
            as_bug = answer.strip().lower().startswith("y")
        if not as_bug:
            out(f"{slug} has {active} in progress. springer polish --as-bug \"{title}\" files the issue as a bug "
                f"on the backlog for it, or wait for the run to finish.")
            return 1
        outcome = api.op("backlog.add_bug", {"title": title, "description": issue, "severity": "medium"}, slug,
                         run_id=active)
        out(f"Filed {outcome['result']['story_id']} on {slug}'s backlog. {active} or the next polish run picks it up.")
        return 0
    version = api.get(f"/v1/projects/{slug}/brief")["version"]
    outcome = api.op("run.start", {"base_version": version, "lane": "polish", "issue": issue}, slug)
    run_id = outcome["result"]["run_id"]
    out(f"Started {run_id} on {slug}: {title}")
    out("Its progress thread opens in your Slack direct message, and springer shows it under Run.")
    return tail(home, run_id, slug, timeout, out) if follow else 0


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
    svc = sub.add_parser("service", help="keep the daemon running under launchd, across crashes and reboots")
    svc.add_argument("action", choices=("install", "uninstall", "status"))
    again = sub.add_parser("respawn")  # internal: the helper a drained restart leaves behind
    again.add_argument("--after", type=int, required=True)
    run_daemon = sub.add_parser("daemon", help="run the daemon in the foreground")
    run_daemon.add_argument("--home", dest="daemon_home", default=None)
    run_daemon.add_argument("--port", type=int, default=DEFAULT_PORT)
    polish_cmd = sub.add_parser("polish", help="start a polish run on one issue, in your words, for the project here")
    polish_cmd.add_argument("issue", nargs="+", help="what is wrong, in your own words")
    polish_cmd.add_argument("--project", default=None, help="the project, when not run from inside it")
    polish_cmd.add_argument("--as-bug", action="store_true", help="with a run in progress, file the issue as a bug")
    polish_cmd.add_argument("--no-follow", action="store_true", help="print the run id and return")
    polish_cmd.add_argument("--timeout", type=float, default=None, help="stop following after this many seconds")
    tail_cmd = sub.add_parser("tail", help="follow a run's lines until it completes or a gate opens")
    tail_cmd.add_argument("run_id")
    tail_cmd.add_argument("--project", default=None)
    tail_cmd.add_argument("--timeout", type=float, default=None, help="stop following after this many seconds")
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
    if args.command == "service":
        from .service import service
        return service(home, args.action)
    if args.command == "respawn":
        return respawn(home, args.after)
    if args.command in ("polish", "tail"):
        try:
            if args.command == "polish":
                return polish(home, " ".join(args.issue), slug=args.project, as_bug=args.as_bug,
                              follow=not args.no_follow, timeout=args.timeout)
            return tail(home, args.run_id, slug=args.project, timeout=args.timeout)
        except (RuntimeError, OSError, KeyError, ValueError) as exc:
            sys.stderr.write(f"springer: {exc}\n")
            return 1
    if args.command == "stop":
        stopped = stop_daemon(home)
        print("springer: daemon stopped." if stopped else "springer: no daemon is running.")
        from . import service
        if stopped and service.installed():
            print("springer: the service starts it again. springer service uninstall keeps it stopped.")
        return 0
    return open_tui(home)


if __name__ == "__main__":
    sys.exit(main())
