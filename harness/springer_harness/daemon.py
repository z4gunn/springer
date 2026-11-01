"""One daemon serving every registered project. It owns the engines and the ticking,
and the API reads through it. All writers take one lock, so an operation and a tick
never interleave, which is the single-writer rule held inside one process."""

import re
import subprocess
import sys
import threading
import traceback
from pathlib import Path

from .common import artifact_header, read_json, write_json
from .errors import InvalidArgs, NotFound
from .registry import Home
from .scheduler.engine import RunEngine
from .scheduler.worktrees import Worktrees
from .state.brief import BriefStore, derive
from .state.lock import daemon_owner
from .state.usage import UsageWindow

SOURCE = Path(__file__).resolve().parents[2]
TICK_SECONDS = 5


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"


class Daemon:
    def __init__(self, home, provider, source_host, planner_factory, secrets, now, maximum=2):
        self.home = Home(home)
        self.provider = provider
        self.source_host = source_host
        self.planner_factory = planner_factory
        self.secrets = secrets
        self.now = now
        self.maximum = maximum
        self.owner = daemon_owner()
        self.lock = threading.RLock()
        self.engines = {}
        self.window = UsageWindow(self.home.root, provider.name, now, maximum)
        self._stop = threading.Event()
        self.started_at = now()

    # --- projects and runs ---

    def project_path(self, slug):
        return Path(self.home.project(slug)["path"])

    def brief(self, slug):
        return BriefStore(self.project_path(slug))

    def run_ids(self, slug):
        root = self.project_path(slug) / "runs"
        if not root.is_dir():
            return []
        return sorted((p.name for p in root.iterdir() if (p / "run-brief.json").exists()),
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
        return RunEngine(slug, path, run_id, self.provider, self.planner_factory(slug, run_id, kind), self.source_host,
                         Worktrees(self.home.root, slug, path), self.window, self.owner, self.now,
                         in_flight_total=self._in_flight_total)

    def _in_flight_total(self):
        return sum(len(e.units.by_state("running")) for e in self.engines.values())

    def create_project(self, name, path, mode):
        slug = slugify(name)
        if slug in self.home.projects():
            raise InvalidArgs(f"a project named {slug} already exists")
        target = Path(path)
        if not target.is_absolute():
            raise InvalidArgs("path must be absolute")
        if mode == "new":
            done = subprocess.run(["bash", str(SOURCE / "scripts" / "new-project.sh"), str(target), "small"],
                                  capture_output=True, text=True)
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

    def start_run(self, slug, kind, sections=None):
        front, _ = self.brief(slug).load()
        count = len(self.run_ids(slug)) + 1
        run_id = f"{slug}-{kind}-{count}" if kind != "build" else f"{slug}-{count}"
        path = self.project_path(slug)
        derived = derive(front)
        doc = artifact_header(f"run-brief-{run_id}", "run-brief", "run_brief", "v1", self.now())
        doc["content"] = {"run_id": run_id, "profile": derived["profile"], "kind": kind, "lane": derived["lane"],
                          "brief_version": front.get("brief_version", 1), "sections": sections}
        write_json(path / "runs" / run_id / "run-brief.json", doc)
        self.engines[(slug, run_id)] = self._new_engine(slug, path, run_id, kind)
        return run_id

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
                    except Exception:  # noqa: BLE001, one run's defect must not stop the others
                        traceback.print_exc(file=sys.stderr)
                        results[(slug, run_id)] = "failed"
            return results

    def loop(self, seconds=TICK_SECONDS):
        while not self._stop.wait(seconds):
            self.tick_all()

    def start(self, seconds=TICK_SECONDS):
        self.recover()
        thread = threading.Thread(target=self.loop, args=(seconds,), daemon=True, name="springer-tick")
        thread.start()
        return thread

    def stop(self):
        self._stop.set()

    def state(self):
        record = self.window.read()
        parked = self.window.parked()
        return {"state": "parked" if parked else "running", "parked_until": record["resets_at"] if parked else None}
