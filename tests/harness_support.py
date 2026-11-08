"""Fixtures for the harness package tests: a real git project, a clock the test
turns by hand, and an engine wired to the mock provider."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import REPO, SCHEMAS

sys.path.insert(0, str(REPO / "harness"))

try:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

from springer_harness.providers.mock import MockProvider, MockSourceHost  # noqa: E402
from springer_harness.scheduler.engine import RunEngine  # noqa: E402
from springer_harness.scheduler.plan import CannedPlanner  # noqa: E402
from springer_harness.scheduler.worktrees import Worktrees  # noqa: E402
from springer_harness.state.usage import UsageWindow  # noqa: E402

OWNER = "daemon:test:1"
RUN = "demo"


class Clock:
    def __init__(self, start=1_800_000_000):
        self.t = start

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def git_project(path):
    path.mkdir(parents=True)
    env = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    (path / "README.md").write_text("project\n")
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(path), *env, "commit", "-q", "-m", "init"], check=True)
    return path


class EngineCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.project = git_project(self.root / "app")
        self.clock = Clock()
        self.host = MockSourceHost()
        self.provider = MockProvider()
        self.addCleanup(self.tmp.cleanup)

    def engine(self, batches=(), provider=None, owner=OWNER, maximum=2):
        provider = provider or self.provider
        return RunEngine("app", self.project, RUN, provider, CannedPlanner(batches), self.host,
                         Worktrees(self.home, "app", self.project),
                         UsageWindow(self.home, provider.name, self.clock, maximum), owner, self.clock)

    def tick_until(self, engine, predicate, limit=40):
        for _ in range(limit):
            if predicate():
                return
            engine.tick()
        self.fail(f"not reached in {limit} ticks: {self.states(engine)}")

    def states(self, engine):
        return {u: engine.units.state(u)["state"] for u in engine.units.ids()}

    def events(self, engine, name=None):
        return [e.line for e in engine.ledger.read() if name is None or e.line.get("event") == name]


def registry():
    resources = [(s["$id"], Resource.from_contents(s)) for s in
                 (__import__("json").loads(p.read_text()) for p in SCHEMAS.glob("*.json")) if s.get("$id")]
    return Registry().with_resources(resources)


def schema_errors(name, obj, reg=None):
    import json
    schema = json.loads((SCHEMAS / f"{name}.json").read_text())
    return [f"{list(e.path)}: {e.message}" for e in
            Draft202012Validator(schema, registry=reg or registry()).iter_errors(obj)]
