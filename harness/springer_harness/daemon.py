"""One daemon serving every registered project. It owns the engines and the ticking,
and the API reads through it. All writers take one lock, so an operation and a tick
never interleave, which is the single-writer rule held inside one process."""

import os
import re
import subprocess
import sys
import threading
import traceback
import uuid
from pathlib import Path

from .common import artifact_header, iso, read_json, write_json
from .errors import IllegalTransition, InvalidArgs, NotFound
from .providers.local import LocalSourceHost
from .registry import Home
from .scheduler.engine import RunEngine
from .scheduler.worktrees import Worktrees
from .state.brief import BriefStore, derive
from .state.lock import daemon_owner
from .state.usage import UsageWindow

SOURCE = Path(__file__).resolve().parents[2]
TICK_SECONDS = 5
HEARTBEAT_FILE = "heartbeat.json"
RESTART_FILE = "restart.json"
STALL_AFTER = 3  # failed ticks in a row before a person is told at once


def expand_path(raw):
    """A path as a person writes it. ~/Repos/app is the home directory, and so is
    ~Repos/app unless Repos really is a user, because that is what people mean by it."""
    text = raw.strip()
    if text.startswith("~"):
        expanded = os.path.expanduser(text)
        text = str(Path.home() / text[1:].lstrip("/")) if expanded.startswith("~") else expanded
    return Path(text)


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"


CI_SIGNALS = ("receipts", "self-hosted-actions", "both")
SOURCE_HOSTS = ("local", "github")
# Local first: a project merges in its own checkout and runs its checks on this
# machine until a person opts it into GitHub pull requests and Actions.
SETTINGS_DEFAULT = {"ci_signal": "receipts", "source_host": "local"}
HOSTED_SIGNALS = ("self-hosted-actions", "both")


class ProjectHost:
    """The source host a project's settings name, looked up on every call, so a
    change in Settings takes effect on the next tick."""

    def __init__(self, daemon, slug):
        self._daemon, self._slug = daemon, slug

    def __getattr__(self, name):
        return getattr(self._daemon.host_for(self._slug), name)


def _content_of(path):
    doc = read_json(path) or {}
    return doc.get("content", {}) if isinstance(doc, dict) else {}


class Daemon:
    def __init__(self, home, provider, source_host, planner_factory, secrets, now, maximum=2, local_host=None):
        """source_host is the hosted one (GitHub) a project opts into. local_host is the
        default, built here when not given."""
        self.home = Home(home)
        self.provider = provider
        self.source_host = source_host
        self.local_host = local_host or LocalSourceHost(self.project_path, self.home.root / "changes")
        self.planner_factory = planner_factory
        self.secrets = secrets
        self.now = now
        self.maximum = maximum
        self.owner = daemon_owner()
        self.lock = threading.RLock()
        self.engines = {}
        self._tick_errors = {}
        self._tick_failures = {}
        self.unclean_start = None  # the last heartbeat, when the daemon before did not stop cleanly
        self.restart_process = None  # set by serve, so a drained restart can replace the process
        self.operations = None  # set by the API app
        self._restarting = False
        self.window = UsageWindow(self.home.root, provider.name, now, maximum)
        self._stop = threading.Event()
        self.started_at = now()
        self.config = None  # set when onboarded
        self.degradations = []  # what doctor found missing, shown in the TUI

    # --- projects and runs ---

    def project_path(self, slug):
        return Path(self.home.project(slug)["path"])

    def brief(self, slug):
        return BriefStore(self.project_path(slug))

    def run_ids(self, slug):
        root = self.project_path(slug) / "runs"
        if not root.is_dir():
            return []
        # A run the daemon made carries kind in its run brief. A run written before the
        # daemon (an adopted instance's history) is the project's, read from the index.
        return sorted((p.name for p in root.iterdir() if (p / "run-brief.json").exists()
                       and _content_of(p / "run-brief.json").get("kind")),
                      key=lambda r: (root / r / "run-brief.json").stat().st_mtime_ns)

    def run_brief(self, slug, run_id):
        return read_json(self.project_path(slug) / "runs" / run_id / "run-brief.json") or {}

    def started(self, slug):
        return any(self.run_brief(slug, r).get("content", {}).get("kind") == "build" for r in self.run_ids(slug))

    def active_run(self, slug):
        for run_id in reversed(self.run_ids(slug)):
            if not self.engine(slug, run_id).cycles.is_complete():
                return run_id
        return None

    def engine(self, slug, run_id):
        key = (slug, run_id)
        if key not in self.engines:
            path = self.project_path(slug)
            if not (path / "runs" / run_id / "run-brief.json").exists():
                raise NotFound(f"no run {run_id} in {slug}")
            kind = self.run_brief(slug, run_id).get("content", {}).get("kind", "build")
            self.engines[key] = self._new_engine(slug, path, run_id, kind)
        return self.engines[key]

    def _new_engine(self, slug, path, run_id, kind):
        return RunEngine(slug, path, run_id, self.provider, self.planner_factory(slug, run_id, kind), ProjectHost(self, slug),
                         Worktrees(self.home.root, slug, path), self.window, self.owner, self.now,
                         in_flight_total=self._in_flight_total, settings=lambda: self.settings(slug))

    # --- per-project settings ---

    def settings(self, slug):
        return {**SETTINGS_DEFAULT, **(self.home.project(slug).get("settings") or {})}

    def host_for(self, slug):
        return self.source_host if self.settings(slug)["source_host"] == "github" else self.local_host

    def save_settings(self, slug, **changes):
        record = self.home.project(slug)
        self.home.save_project(slug, {**record, "settings": {**self.settings(slug), **changes}})
        return self.settings(slug)

    def _in_flight_total(self):
        return sum(len(e.units.by_state("running")) for e in self.engines.values())

    def create_project(self, name, path, mode):
        slug = slugify(name)
        if slug in self.home.projects():
            raise InvalidArgs(f"a project named {slug} already exists")
        target = expand_path(path)
        if not target.is_absolute():
            raise InvalidArgs(f"{path} is relative, and the daemon has no directory to read it from. "
                              "Use ~/Repos/app or a full path.")
        if mode == "new":
            done = subprocess.run(["bash", str(SOURCE / "scripts" / "new-project.sh"), str(target), "small"],
                                  capture_output=True, text=True)
        elif (target / ".claude" / "springer-manifest.json").exists():
            return self._adopt_instance(slug, name, target)
        else:
            done = subprocess.run([sys.executable, str(SOURCE / "scripts" / "update-project.py"), "adopt", str(target),
                                   "--profile", "small"], capture_output=True, text=True)
        if done.returncode:
            raise InvalidArgs(f"could not {mode} {target}: {done.stderr.strip()[:400]}")
        manifest = read_json(target / ".claude" / "springer-manifest.json") or {}
        self.home.save_project(slug, {"slug": slug, "name": name, "path": str(target), "archived": False,
                                      "runtime_version": (manifest.get("source_commit") or "")[:7]})
        store = BriefStore(target)
        if not store.exists():
            store.create(name)
        return slug

    def _adopt_instance(self, slug, name, target):
        """An existing Springer instance takes the update path: see adopt.py."""
        from . import adopt
        plan = adopt.plan(target)
        try:
            written = adopt.apply(target, plan, name, self.home.root, slug)
        except RuntimeError as exc:
            raise InvalidArgs(str(exc))
        manifest = read_json(target / ".claude" / "springer-manifest.json") or {}
        merges = sorted(w for w in written if w.startswith(adopt.UPDATE_DIR))
        brief = BriefStore(target).load()[0] if BriefStore(target).exists() else {}
        self.home.save_project(slug, {"slug": slug, "name": name, "path": str(target), "archived": False,
                                      "runtime_version": (manifest.get("source_commit") or "")[:7],
                                      "adopted": True, "hand_merge": merges,
                                      "adopted_brief_version": brief.get("brief_version")})
        return slug

    def history(self, slug):
        """Runs from before the daemon, imported at adoption, newest last."""
        return read_json(self.home.root / "index" / f"{slug}.json", {"runs": [], "learnings": []})

    def start_run(self, slug, kind, sections=None, lane=None, issue=None):
        front, _ = self.brief(slug).load()
        count = len(self.run_ids(slug)) + 1
        run_id = f"{slug}-{kind}-{count}" if kind != "build" else f"{slug}-{count}"
        path = self.project_path(slug)
        derived = derive(front)
        doc = artifact_header(f"run-brief-{run_id}", "run-brief", "run_brief", "v1", self.now())
        doc["content"] = {"run_id": run_id, "profile": derived["profile"], "kind": kind, "lane": lane or derived["lane"],
                          "issue": issue,
                          "brief_version": front.get("brief_version", 1), "sections": sections,
                          "pinned_rulings": list(front.get("pinned_rulings") or [])}
        write_json(path / "runs" / run_id / "run-brief.json", doc)
        if kind == "build":
            self._stamp_profile(path, derived["profile"])
            self.commit_brief(slug, path, run_id)
            host = self.host_for(slug)
            if hasattr(host, "ensure_remote"):
                private = (self.config or {}).get("private_repos", True)
                try:
                    host.ensure_remote(slug, private=private)
                except RuntimeError as exc:
                    raise InvalidArgs(f"the project has no GitHub repository and one could not be made: {exc}")
        self.engines[(slug, run_id)] = self._new_engine(slug, path, run_id, kind)
        return run_id

    def commit_brief(self, slug, path, run_id, message=None):
        """Start run is the commit, and so is an applied brief change: a unit's worktree
        is cut from a commit, so a brief that lives only in the working tree is a brief
        no session can read, and an uncommitted change refuses every local merge."""
        brief = "docs/brief.md"
        changed = subprocess.run(["git", "-C", str(path), "status", "--porcelain", "--", brief],
                                 capture_output=True, text=True).stdout.strip()
        if not changed:
            return
        subprocess.run(["git", "-C", str(path), "add", "--", brief], capture_output=True)
        done = subprocess.run(["git", "-C", str(path), "-c", "user.name=Springer", "-c", "user.email=springer@local",
                               "commit", "-q", "-m", message or f"docs: the brief for {run_id}", "--", brief],
                              capture_output=True, text=True)
        if done.returncode:
            sys.stderr.write(f"could not commit the brief in {path}: {done.stderr.strip()}\n")
        elif hasattr(self.host_for(slug), "publish"):
            self.host_for(slug).publish(slug, "HEAD")

    def _stamp_profile(self, path, profile):
        """Scaffolding happens before the brief exists, so the ruleset learns its profile
        here. It is committed because a unit's worktree is cut from a commit. A failure
        is reported and does not stop the run, because the run reads the brief."""
        files = ["CLAUDE.md", ".claude/springer-manifest.json"]
        stamped = subprocess.run([sys.executable, str(SOURCE / "scripts" / "update-project.py"), "set-profile", str(path), profile],
                                 capture_output=True, text=True)
        if stamped.returncode:
            sys.stderr.write(f"could not record profile {profile} in {path}: {stamped.stderr.strip()}\n")
            return
        changed = subprocess.run(["git", "-C", str(path), "status", "--porcelain", "--", *files], capture_output=True, text=True)
        if changed.stdout.strip():
            committed = subprocess.run(["git", "-C", str(path), "-c", "user.name=Springer", "-c", "user.email=springer@local",
                                        "commit", "-q", "-m", f"chore: record the {profile} profile", "--", *files],
                                       capture_output=True, text=True)
            if committed.returncode:
                sys.stderr.write(f"could not commit profile {profile} in {path}: {committed.stderr.strip()}\n")

    # --- ticking ---

    def recover(self):
        with self.lock:
            for slug, record in self.home.projects().items():
                if record.get("archived"):
                    continue
                for run_id in self.run_ids(slug):
                    engine = self.engine(slug, run_id)
                    if not engine.cycles.is_complete():
                        engine.recover()

    def tick_all(self):
        with self.lock:
            results = {}
            for slug, record in self.home.projects().items():
                if record.get("archived"):
                    continue
                for run_id in self.run_ids(slug):
                    engine = self.engine(slug, run_id)
                    if engine.cycles.is_complete():
                        continue
                    try:
                        results[(slug, run_id)] = engine.tick()
                    except Exception as exc:  # noqa: BLE001, one run's defect must not stop the others
                        traceback.print_exc(file=sys.stderr)
                        self._tick_failed(engine, (slug, run_id), exc)
                        results[(slug, run_id)] = "failed"
                    else:
                        self._tick_errors.pop((slug, run_id), None)
                        self._tick_failures.pop((slug, run_id), None)
            return results

    def _tick_failed(self, engine, key, exc):
        """A failing tick is written to the run's ledger, where the TUI shows it, once
        per distinct error, because the daemon's stderr is not where anyone looks."""
        detail = f"{type(exc).__name__}: {exc}"[-400:]
        count = self._tick_failures.get(key, 0) + 1
        self._tick_failures[key] = count
        if count == STALL_AFTER:
            # One failed tick can be a passing hiccup. Three in a row is a stalled run,
            # and a person hears of it at once.
            try:
                engine.ledger.append("tick_stalled", count=count, detail=detail)
            except OSError:
                pass
        if self._tick_errors.get(key) == detail:
            return
        self._tick_errors[key] = detail
        try:
            engine.ledger.append("tick_failed", detail=detail)
        except OSError:
            pass

    def loop(self, seconds=TICK_SECONDS):
        while not self._stop.wait(seconds):
            self.tick_all()
            self.beat()

    # --- health and restarts ---

    def beat(self, clean=False):
        """The heartbeat. A start that finds one not marked clean follows a crash, a kill,
        or a reboot, and the notifier says so once."""
        write_json(self.home.root / HEARTBEAT_FILE, {"pid": os.getpid(), "at": iso(self.now()), "clean": clean})

    def note_start(self):
        previous = read_json(self.home.root / HEARTBEAT_FILE)
        if isinstance(previous, dict) and not previous.get("clean"):
            self.unclean_start = {"at": previous.get("at"), "pid": previous.get("pid")}
        self.beat()

    def mark_clean_stop(self):
        self.beat(clean=True)

    def _active_runs(self):
        found = []
        for slug, record in self.home.projects().items():
            if record.get("archived"):
                continue
            run_id = self.active_run(slug)
            if run_id:
                found.append((slug, run_id))
        return found

    def sessions_running(self):
        with self.lock:
            return sum(len(self.engine(slug, run_id).units.by_state("running"))
                       for slug, run_id in self._active_runs())

    def request_restart(self, actor, poll=TICK_SECONDS):
        """Drain, then restart: every run is paused so nothing new starts, the running
        sessions finish, the process is replaced, and the next start resumes the runs.
        A restart that kills a session costs the work in it."""
        if self._restarting:
            raise IllegalTransition("A restart is already draining.")
        if self.operations is None or self.restart_process is None:
            raise IllegalTransition("This daemon cannot restart itself. Run springer stop and start it again.")
        self._restarting = True
        threading.Thread(target=self._drain_and_restart, args=(actor, poll), daemon=True,
                         name="springer-restart").start()

    def _drain_and_restart(self, actor, poll):
        paused = []
        with self.lock:
            runs = [(slug, run_id) for slug, run_id in self._active_runs()
                    if not self.engine(slug, run_id).paused()]
        for slug, run_id in runs:
            self.operations.apply(f"restart-pause-{uuid.uuid4().hex}", "run.pause", slug, run_id,
                                  {"reason": "draining for a daemon restart"}, None, actor)
            paused.append([slug, run_id])
        write_json(self.home.root / RESTART_FILE, {"resume": paused, "by": actor})
        while self.sessions_running() and not self._stop.is_set():
            self._stop.wait(poll)
        self.restart_process()

    def resume_after_restart(self):
        """The runs a drained restart paused, resumed in the name of the person who asked."""
        path = self.home.root / RESTART_FILE
        record = read_json(path)
        if not isinstance(record, dict) or self.operations is None:
            return []
        resumed = []
        for slug, run_id in record.get("resume", []):
            try:
                self.operations.apply(f"restart-resume-{uuid.uuid4().hex}", "run.resume", slug, run_id, {}, None,
                                      record.get("by", "tui"))
                resumed.append(run_id)
            except Exception as exc:  # noqa: BLE001, one run that cannot resume must not stop the rest
                sys.stderr.write(f"could not resume {run_id} after the restart: {exc}\n")
        path.unlink(missing_ok=True)
        return resumed

    def start(self, seconds=TICK_SECONDS):
        self.note_start()
        self.recover()
        if self.config is not None:
            threading.Thread(target=self._find_degradations, daemon=True, name="springer-doctor").start()
        thread = threading.Thread(target=self.loop, args=(seconds,), daemon=True, name="springer-tick")
        thread.start()
        return thread

    def _find_degradations(self):
        from .setup import degradations
        self.degradations = degradations(self.config)

    def stop(self):
        self._stop.set()

    def state(self):
        record = self.window.read()
        parked = self.window.parked()
        return {"state": "parked" if parked else "running", "parked_until": record["resets_at"] if parked else None}
