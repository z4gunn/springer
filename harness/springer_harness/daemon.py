"""One daemon serving every registered project. It owns the engines and the ticking,
and the API reads through it. All writers take one lock, so an operation and a tick
never interleave, which is the single-writer rule held inside one process."""

import os
import re
import subprocess
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path

from . import cleanup, risk_rules
from .common import artifact_header, iso, read_json, write_json, write_text
from .errors import IllegalTransition, InvalidArgs, NotFound
from .providers.local import LocalSourceHost
from .reconcile import Reconciler
from .registry import Home
from .release import Releases, ready_to_ship
from .scheduler.engine import RunEngine
from .scheduler.worktrees import Worktrees
from .state.backlog import BacklogStore
from .state.brief import BriefStore, derive, parse
from .state.lock import daemon_owner
from .state.usage import UsageWindow

SOURCE = Path(__file__).resolve().parents[2]
TICK_SECONDS = 5
HEARTBEAT_FILE = "heartbeat.json"
CRASH_FILE = "crashes.json"
CRASH_WINDOW_SECONDS = 600
CRASH_LIMIT = 3  # unclean starts inside the window that make a crash loop
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


RUN_STORE_IGNORES = (
    "# --- Springer run store: working state. The daemon commits each run's records when it ends ---",
    "runs/_dashboard/", "runs/*/units/", "runs/*/plan/", "runs/*/release/", "runs/*/events.jsonl",
    "runs/*/run-state.json", "runs/*/unit-keys.json", "runs/*/.lock",
)


def ignore_run_store(path):
    """Add the run store's ignore rules to the project's .gitignore. True when it changed.
    A file already tracked stays tracked, so an older run's committed ledger is untouched."""
    target = Path(path) / ".gitignore"
    text = target.read_text() if target.exists() else ""
    present = set(text.splitlines())
    missing = [line for line in RUN_STORE_IGNORES if line not in present]
    if not missing:
        return False
    target.write_text(text + ("" if not text or text.endswith("\n") else "\n") + ("\n" if text else "")
                      + "\n".join(missing) + "\n")
    return True


def _legacy_names(path, run_id):
    """True for a run whose units already have branches named before branches carried
    the run, so it finishes under the names it started with."""
    for state in (Path(path) / "runs" / run_id / "units").glob("U-*/state.json"):
        if '"unit/U-' in state.read_text():
            return True
    return False


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


def _brief_version(text):
    try:
        return int(parse(text)[0].get("brief_version", 1))
    except (InvalidArgs, TypeError, ValueError):
        return 0


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
        self.releases = Releases()
        self._recorded = set()  # finished runs whose records are committed
        self._tick_errors = {}
        self._tick_failures = {}
        self.unclean_start = None  # the last heartbeat, when the daemon before did not stop cleanly
        self.crash_loop = None  # {"count", "since"} when the unclean starts in the window reach CRASH_LIMIT
        self.restart_process = None  # set by serve, so a drained restart can replace the process
        self.operations = None  # set by the API app
        self._restarting = False
        self.window = UsageWindow(self.home.root, provider.name, now, maximum)
        self._stop = threading.Event()
        self.started_at = now()
        self.config = None  # set when onboarded
        self.degradations = []  # what doctor found missing, shown in the TUI
        self.reconciler = Reconciler(self)
        self.announcements = []  # lines for the person's channel, drained by the notifier

    # --- projects and runs ---

    def checkout_path(self, slug):
        """The person's checkout. The daemon reads it, and the one file it writes there
        is docs/brief.md on the person's own edit from a client."""
        return Path(self.home.project(slug)["path"])

    def project_path(self, slug):
        """The checkout the daemon works in: its own clone of a hosted project, else the
        person's, which a local project shares (see Modes in pdca-harness)."""
        record = self.home.project(slug)
        return Path(record["clone"]) if record.get("clone") else Path(record["path"])

    def brief(self, slug):
        """The brief is the person's document, read and edited in their checkout. A run
        takes a copy into the daemon's checkout at start (see _take_brief)."""
        return BriefStore(self.checkout_path(slug))

    def ensure_clone(self, slug):
        """A hosted project gets a clone of its own under the daemon's home, so the
        daemon never commits in the person's checkout. The working state of every run
        moves in with it. None while the project has no origin, because the clone is
        cut from origin and waits for the remote."""
        record = self.home.project(slug)
        if record.get("clone"):
            return Path(record["clone"])
        checkout = Path(record["path"])
        origin = subprocess.run(["git", "-C", str(checkout), "remote", "get-url", "origin"],
                                capture_output=True, text=True)
        if origin.returncode:
            return None
        running = self.active_run(slug)
        if running:
            raise IllegalTransition(f"{slug} has {running} in progress, so the daemon cannot move to a clone yet")
        clone = self.home.root / "clones" / slug
        if not (clone / ".git").exists():
            clone.parent.mkdir(parents=True, exist_ok=True)
            done = subprocess.run(["git", "clone", "--quiet", origin.stdout.strip(), str(clone)],
                                  capture_output=True, text=True)
            if done.returncode:
                raise IllegalTransition(f"could not clone {slug}: {done.stderr.strip()[-300:]}")
        for key, value in (("user.name", "Springer"), ("user.email", "springer@local")):
            subprocess.run(["git", "-C", str(clone), "config", key, value], capture_output=True)
        cleanup.move_untracked(checkout, checkout / "runs", cleanup.tracked_under(checkout, "runs/"), clone / "runs")
        self.home.save_project(slug, {**self.home.project(slug), "clone": str(clone)})
        self._forget_engines(slug)
        return clone

    def drop_clone(self, slug):
        """Back to local: the working state returns to the person's checkout, which a
        local project shares with the daemon. The clone stays on disk."""
        record = self.home.project(slug)
        if not record.get("clone"):
            return
        running = self.active_run(slug)
        if running:
            raise IllegalTransition(f"{slug} has {running} in progress, so the daemon cannot leave its clone yet")
        clone, checkout = Path(record["clone"]), Path(record["path"])
        cleanup.move_untracked(clone, clone / "runs", cleanup.tracked_under(clone, "runs/"), checkout / "runs")
        self.home.save_project(slug, {k: v for k, v in record.items() if k != "clone"})
        self._forget_engines(slug)

    def _forget_engines(self, slug):
        """Engines built on the old checkout are rebuilt from disk on the next read."""
        for key in [k for k in self.engines if k[0] == slug]:
            self.engines.pop(key)

    def run_ids(self, slug):
        root = self.project_path(slug) / "runs"
        if not root.is_dir():
            return []
        # A run the daemon made carries kind in its run brief. A run written before the
        # daemon (an adopted instance's history) is the project's, read from the index.
        # A pruned run is gone even while its removal waits in a pull request.
        pruned = self.pruned_runs(slug)
        return sorted((p.name for p in root.iterdir() if (p / "run-brief.json").exists()
                       and p.name not in pruned and _content_of(p / "run-brief.json").get("kind")),
                      key=lambda r: (root / r / "run-brief.json").stat().st_mtime_ns)

    def archived_runs(self, slug):
        return list(self.home.project(slug).get("archived_runs") or [])

    def pruned_runs(self, slug):
        return dict(self.home.project(slug).get("pruned_runs") or {})

    def _known_run(self, slug, run_id):
        path = self.project_path(slug)
        if run_id in self.run_ids(slug) or any(r.get("run_id") == run_id for r in self.history(slug).get("runs") or []):
            return path
        cleanup.run_folder(path, run_id)
        return path

    def archive_run(self, slug, run_id):
        """Hide a finished run from the runs list. Deletes nothing."""
        self._known_run(slug, run_id)
        if run_id in self.run_ids(slug) and not self.engine(slug, run_id).cycles.is_complete():
            raise IllegalTransition(f"{run_id} is still in progress. Cancel it or let it finish first.")
        record = self.home.project(slug)
        archived = list(record.get("archived_runs") or [])
        if run_id not in archived:
            self.home.save_project(slug, {**record, "archived_runs": archived + [run_id]})

    def restore_run(self, slug, run_id):
        if run_id in self.pruned_runs(slug):
            raise IllegalTransition(f"{run_id} was pruned. Its working state is under "
                                    f"{self.pruned_runs(slug)[run_id]['moved_to']}.")
        record = self.home.project(slug)
        self.home.save_project(slug, {**record, "archived_runs": [r for r in record.get("archived_runs") or []
                                                                  if r != run_id]})

    def prune_run(self, slug, run_id):
        """Remove an archived run's folder. See cleanup for what goes where."""
        if run_id not in self.archived_runs(slug):
            raise IllegalTransition(f"Archive {run_id} before pruning it.")
        if run_id in self.pruned_runs(slug):
            raise IllegalTransition(f"{run_id} is already pruned.")
        path = self.project_path(slug)
        cleanup.run_folder(path, run_id)
        daemon_run = run_id in self.run_ids(slug)
        remove, keep = cleanup.plan(path, run_id)
        message = f"chore(runs): prune {run_id}"
        change = None
        if self.settings(slug)["source_host"] == "github":
            scratch = self.home.root / "worktrees" / slug / f"_prune-{run_id}"
            branch, base = cleanup.branch_removal(path, remove, f"springer/prune-{run_id}", message, scratch)
            if branch:
                body = (f"Removes the records of archived run {run_id}: {len(remove)} files. "
                        f"{len(keep)} files stay because the repository cites them by path.")
                change = self.source_host.open_pr(slug, branch, base, message, body)
        else:
            change = cleanup.commit_removal(path, remove, message)
            if change and hasattr(self.host_for(slug), "publish"):
                self.host_for(slug).publish(slug, "HEAD")
        target = self.home.root / "pruned" / slug / run_id
        moved = cleanup.move_ignored(path, run_id, remove + keep, target)
        self.engines.pop((slug, run_id), None)
        # No run_id key: the operation log reads that as the run to write to, and this
        # run's ledger has just moved.
        result = {"pruned": run_id, "removed": len(remove), "kept": keep, "moved": moved,
                  "moved_to": str(target), "change": change, "daemon_run": daemon_run, "at": iso(self.now())}
        record = self.home.project(slug)
        self.home.save_project(slug, {**record, "pruned_runs": {**(record.get("pruned_runs") or {}), run_id: result}})
        return result

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
                         Worktrees(self.home.root, slug, path, None if _legacy_names(path, run_id) else run_id),
                         self.window, self.owner, self.now,
                         in_flight_total=self._in_flight_total, settings=lambda: self.settings(slug),
                         release=lambda by, gate_id: self.release(slug, by, run_id, reason=gate_id))

    # --- per-project settings ---

    def settings(self, slug):
        return {**SETTINGS_DEFAULT, **(self.home.project(slug).get("settings") or {})}

    def release(self, slug, by, run_id=None, reason=None):
        """Start the project's deploy command on a thread, after a person's go. Returns
        (out_dir, None) once started, or (None, why not). The run it is logged under is
        the one named, else the project's newest, so its thread in Slack reports it."""
        settings = self.settings(slug)
        command = settings.get("release_command")
        if not command:
            return None, f"{slug} has no release command. Set one with /springer release-command {slug} \"<command>\""
        run_ids = self.run_ids(slug)
        run_id = run_id or (run_ids[-1] if run_ids else None)
        if run_id is None:
            return None, f"{slug} has no run to log the release under"
        if self.releases.running(slug):
            return None, f"a release of {slug} is already running"
        path = self.project_path(slug)
        sha, why_not = ready_to_ship(path, Worktrees(self.home.root, slug, path).default_branch())
        if why_not:
            return None, why_not
        engine = self.engine(slug, run_id)
        out_dir = engine.run_dir / "release" / f"{time.strftime('%Y%m%dT%H%M%S', time.gmtime(self.now()))}"
        engine.ledger.append("release_started", sha=sha, by=by, reason=reason, command=command)

        def done(result):
            with self.lock:
                event = "release_finished" if result["exit_code"] == 0 else "release_failed"
                engine.ledger.append(event, sha=sha, by=by, exit_code=result["exit_code"],
                                     detail=result["tail"][-600:])

        self.releases.start(slug, command, settings.get("release_confirm"), path, out_dir, sha, done)
        return out_dir, None

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

    def start_run(self, slug, kind, sections=None, lane=None, issue=None, burndown=False, story_ids=None):
        source = self._prepare(slug, kind)
        path = self.project_path(slug)
        front, _ = BriefStore(path).load()
        # A pruned run keeps its number, so a new run never reuses its branch names.
        count = len(self.run_ids(slug)) + sum(1 for r in self.pruned_runs(slug).values() if r.get("daemon_run")) + 1
        run_id = f"{slug}-{kind}-{count}" if kind != "build" else f"{slug}-{count}"
        derived = derive(front)
        lane = lane or derived["lane"]
        # A polish run's issue is one item on the project backlog, which its unit carries.
        # A burndown is a polish run over several open items, each its own change.
        items = BacklogStore(path).claim(run_id, story_ids) if lane == "polish" and burndown else None
        story_ids = [i["story_id"] for i in items] if items else \
            [BacklogStore(path).add_issue(run_id, issue)] if lane == "polish" and issue else []
        doc = artifact_header(f"run-brief-{run_id}", "run-brief", "run_brief", "v1", self.now())
        doc["content"] = {"run_id": run_id, "profile": derived["profile"], "kind": kind, "lane": lane,
                          "issue": issue, "story_ids": story_ids, **({"items": items} if items else {}),
                          "brief_version": front.get("brief_version", 1), "brief_source": source, "sections": sections,
                          "pinned_rulings": list(front.get("pinned_rulings") or [])}
        write_json(path / "runs" / run_id / "run-brief.json", doc)
        if kind == "build":
            self._stamp_profile(path, derived["profile"])
            self.commit_brief(slug, path, run_id)
        self.engines[(slug, run_id)] = self._new_engine(slug, path, run_id, kind)
        return run_id

    def _prepare(self, slug, kind):
        """Before a run: a hosted build has its remote and the daemon has its clone, the
        daemon's checkout is at origin's tip, and the brief is the person's when theirs
        is the newer one. Returns where the run's brief comes from."""
        host = self.host_for(slug)
        if kind == "build" and hasattr(host, "ensure_remote"):
            private = (self.config or {}).get("private_repos", True)
            try:
                host.ensure_remote(slug, private=private)
            except RuntimeError as exc:
                raise InvalidArgs(f"the project has no GitHub repository and one could not be made: {exc}")
        if self.settings(slug)["source_host"] == "github":
            self.ensure_clone(slug)
        path = self.project_path(slug)
        stale = Worktrees(self.home.root, slug, path).sync_default()
        if stale:
            sys.stderr.write(f"{slug}: {stale}\n")
        return self._take_brief(slug)

    def _take_brief(self, slug):
        """The person writes docs/brief.md in their checkout. When the daemon works in a
        clone, their copy is taken when its version is at least the clone's and the text
        differs, read-only on their side. Returns commit when the brief the run reads is
        committed, else working_tree."""
        checkout, path = self.checkout_path(slug), self.project_path(slug)
        theirs, mine = checkout / "docs" / "brief.md", path / "docs" / "brief.md"
        if path != checkout and theirs.exists():
            text = theirs.read_text()
            current = mine.read_text() if mine.exists() else None
            if text != current and (current is None or _brief_version(text) >= _brief_version(current)):
                mine.parent.mkdir(parents=True, exist_ok=True)
                write_text(mine, text)
        status = subprocess.run(["git", "-C", str(path), "status", "--porcelain", "--", "docs/brief.md"],
                                capture_output=True, text=True)
        return "working_tree" if status.stdout.strip() else "commit"

    def commit_brief(self, slug, path, run_id, message=None):
        """Start run is the commit, and so is an applied brief change: a unit's worktree
        is cut from a commit, so a brief that lives only in the working tree is a brief
        no session can read, and an uncommitted change refuses every local merge. The
        run store's ignore rules ride on the same commit, so they never sit as a tracked
        change that refuses a merge or a release."""
        files = [f for f in ("docs/brief.md", ".gitignore" if ignore_run_store(path) else None) if f]
        self._commit(slug, path, files, message or f"docs: the brief for {run_id}", "the brief")

    def commit_run_records(self, slug, run_id):
        """A finished run's records go into git as one commit: whatever under its folder
        the ignore rules leave (artifacts with the gate answers, escalations, cycles and
        reviews, the run brief, the backlog, the defaults ledger), and the config rulings.
        The working state (sessions, plans, the ledger) stays on disk, ignored. Returns
        True when nothing is left to record."""
        path = self.project_path(slug)
        files = [".gitignore"] if ignore_run_store(path) else []
        files += [p for p in (f"runs/{run_id}", "runs/_config-unlock.json", "runs/_backlog.json",
                              "runs/_reconcile.jsonl", "runs/_reconcile") if (path / p).exists()]
        return self._commit(slug, path, files, f"chore(runs): record {run_id}", f"the records of {run_id}")

    def apply_risk_rule(self, slug, rule, gate_id):
        """A gate answer's rule change goes into the project's risk rules and is
        committed, so the next merge's pr-risk.py reads it."""
        path = self.project_path(slug)
        if risk_rules.apply(path, rule):
            self._commit(slug, path, [risk_rules.FILE], f"chore(runs): risk rule from {gate_id}", "the risk rules")

    def commit_backlog(self, slug, action):
        """A person's edit to the project backlog, committed on its own."""
        path = self.project_path(slug)
        return self._commit(slug, path, ["runs/_backlog.json"], f"chore(runs): backlog {action}", "the backlog")

    def commit_reconcile(self, slug):
        """Reconcile's ledger, its product check results, and the backlog closes it made
        go in as one commit whose subject reconcile knows as its own."""
        path = self.project_path(slug)
        files = [p for p in ("runs/_reconcile.jsonl", "runs/_reconcile", "runs/_backlog.json") if (path / p).exists()]
        return self._commit(slug, path, files, "chore(runs): reconcile", "the reconcile records")

    def _clean_up(self, engine):
        done = [e.line for e in engine.ledger.read() if e.line.get("event") == "cleaned_up"]
        if done and not done[-1].get("kept"):
            return
        try:
            engine.clean_up()
        except Exception as exc:  # noqa: BLE001, a cleanup that fails is retried at the next start
            sys.stderr.write(f"could not clean up {engine.run_id}: {exc}\n")

    def _commit(self, slug, path, files, message, what):
        """Commit files that changed, and publish. True when nothing is left uncommitted.
        Only the paths with a change are named to git, because a path git does not know,
        such as an empty folder, fails the whole commit."""
        files = [f for f in files if subprocess.run(["git", "-C", str(path), "status", "--porcelain", "-uall", "--", f],
                                                    capture_output=True, text=True).stdout.strip()]
        if not files:
            return True
        subprocess.run(["git", "-C", str(path), "add", "--", *files], capture_output=True)
        done = subprocess.run(["git", "-C", str(path), "-c", "user.name=Springer", "-c", "user.email=springer@local",
                               "commit", "-q", "-m", message, "--", *files], capture_output=True, text=True)
        if done.returncode:
            sys.stderr.write(f"could not commit {what} in {path}: {done.stderr.strip() or done.stdout.strip()}\n")
            return False
        if hasattr(self.host_for(slug), "publish"):
            self.host_for(slug).publish(slug, "HEAD")
        return True

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
                        # Once per daemon start, and at the tick that completes it, so a run
                        # cancelled through an operation or finished before this existed is
                        # recorded too.
                        if (slug, run_id) not in self._recorded and self.commit_run_records(slug, run_id):
                            self._clean_up(engine)
                            self._recorded.add((slug, run_id))
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
            self.reconcile_all()
            return results

    def reconcile_all(self):
        """Once a minute per project, the external changes since the last look. See
        reconcile.py and Modes in pdca-harness."""
        now = self.now()
        for slug, record in self.home.projects().items():
            if record.get("archived") or not self.reconciler.due(slug, now):
                continue
            try:
                self.reconciler.tick(slug, now)
            except Exception as exc:  # noqa: BLE001, one project's defect must not stop the others
                self.reconciler.last[slug] = now
                traceback.print_exc(file=sys.stderr)
                sys.stderr.write(f"could not reconcile {slug}: {exc}\n")

    def announce(self, text):
        """A line for the person's channel, posted by the notifier on its next poll."""
        self.announcements.append(text)

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
        crashes = self.home.root / CRASH_FILE
        if isinstance(previous, dict) and not previous.get("clean"):
            self.unclean_start = {"at": previous.get("at"), "pid": previous.get("pid")}
            now = self.now()
            starts = [s for s in (read_json(crashes) or []) if now - s < CRASH_WINDOW_SECONDS] + [now]
            write_json(crashes, starts)
            if len(starts) >= CRASH_LIMIT:
                self.crash_loop = {"count": len(starts), "since": iso(starts[0]), "announce": len(starts) == CRASH_LIMIT}
        elif isinstance(previous, dict):
            crashes.unlink(missing_ok=True)
        self.beat()

    def hold_for_crash_loop(self):
        """A daemon that keeps dying must not keep dispatching into whatever kills it.
        Every active run is paused, and the notifier tells the person once. A person
        resumes each run when the cause is fixed."""
        if not self.crash_loop or self.operations is None:
            return []
        paused = []
        with self.lock:
            runs = [(slug, run_id) for slug, run_id in self._active_runs() if not self.engine(slug, run_id).paused()]
        for slug, run_id in runs:
            try:
                self.operations.apply(f"crash-loop-pause-{uuid.uuid4().hex}", "run.pause", slug, run_id,
                                      {"reason": f"the daemon restarted {self.crash_loop['count']} times in "
                                                 f"{CRASH_WINDOW_SECONDS // 60} minutes"}, None, "daemon")
                paused.append(run_id)
            except Exception as exc:  # noqa: BLE001, one run that cannot pause must not stop the rest
                sys.stderr.write(f"could not pause {run_id} for the crash loop: {exc}\n")
        self.crash_loop["paused"] = paused
        return paused

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
        self.hold_for_crash_loop()
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
