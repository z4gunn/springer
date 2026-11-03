"""The mock coding agent and source host, used to build and test the harness with no
tokens. A script names what each attempt at each unit does. It sits at the provider
slot behind the daemon, so nothing above this module knows it is a mock."""

import itertools
import json
from dataclasses import dataclass, field
from pathlib import Path

from .coding_agent import SessionExit, SpawnRequest, Usage

MODELS = {"haiku": "mock-haiku", "sonnet": "mock-sonnet", "opus": "mock-opus"}


@dataclass
class Attempt:
    """One session's behavior. ticks is how many polls it stays alive."""

    ticks: int = 1
    end: str = "return"  # return, handoff, die, or hang
    result: dict = field(default_factory=lambda: {"status": "pass", "outcome": "artifact"})
    tools: tuple = ("Read", "Bash")
    writes: dict = field(default_factory=dict)  # project-relative path to text, kept if already there


def pr_result(number, branch=None, base="main", touched=(), **extra):
    return {"status": "pass", "outcome": "pr", "pr": {"number": number, "branch": branch, "base": base},
            "touched_paths": list(touched), **extra}


def fail_result(failure_class, detail="scripted failure"):
    return {"status": "fail", "failure_class": failure_class, "detail": detail}


class MockSession:
    _pids = itertools.count(40000)

    def __init__(self, request: SpawnRequest, attempt: Attempt):
        self.request = request
        self.attempt = attempt
        self.pid = next(self._pids)
        self.provider_session_id = f"mock-{request.unit_id}-{request.session_id}"
        self.model = MODELS[request.model_tier]
        self._polls = 0
        self._usage = Usage()
        self._killed = False
        self._exit = None

    def poll(self):
        if self._killed or self._exit or not self.alive():
            return []
        self._polls += 1
        tool = self.attempt.tools[(self._polls - 1) % len(self.attempt.tools)]
        self._usage.input_tokens += 100
        self._usage.output_tokens += 50
        self._usage.context_percent = min(100, self._usage.context_percent + 10)
        self._usage.cost_usd = round(self._usage.cost_usd + 0.01, 4)
        events = [{"type": "tool_use", "name": tool}]
        if self._polls >= self.attempt.ticks:
            self._finish()
        return events

    def _finish(self):
        end = self.attempt.end
        out = Path(self.request.session_dir)
        out.mkdir(parents=True, exist_ok=True)
        if end == "return":
            project = self.request.env.get("SPRINGER_PROJECT_DIR")
            for rel, text in self.attempt.writes.items() if project else ():
                path = Path(project) / rel
                if not path.exists():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(text)
            result = dict(self.attempt.result or {})
            if result.get("pr") and not result["pr"].get("branch"):
                result["pr"] = {**result["pr"], "branch": f"unit/{self.request.unit_id}"}
            if self.attempt.result is not None:
                (out / "result.json").write_text(json.dumps(result))
            (out / "return.txt").write_text(result.get("detail", "done"))
            self._exit = SessionExit("return", 0)
        elif end == "handoff":
            (out / "handoff.md").write_text(f"Continue {self.request.unit_id} from the last checkpoint.\n")
            self._exit = SessionExit("handoff", 0)

    def usage(self):
        return self._usage

    def alive(self):
        if self._killed:
            return False
        if self.attempt.end == "die" and self._polls >= self.attempt.ticks:
            return False
        return True

    def exit(self):
        if self._killed:
            return SessionExit("killed", None)
        return self._exit

    def kill(self):
        self._killed = True


class MockProvider:
    """script maps a unit's agent or id to its attempts in order. The last attempt
    repeats, so a one-entry script is a unit that always does the same thing."""

    name = "mock"

    def __init__(self, script=None, default=None, signals=None):
        self.script = script or {}
        self.default = default or Attempt()
        self.signals = list(signals or [])
        self.spawned = []

    def spawn(self, request):
        attempts = self.script.get(request.unit_id) or self.script.get(request.agent) or [self.default]
        self.spawned.append(request)
        count = sum(1 for r in self.spawned if r.unit_id == request.unit_id)
        return MockSession(request, attempts[min(count - 1, len(attempts) - 1)])

    def usage_signal(self):
        if not self.signals:
            return None
        return self.signals.pop(0) if len(self.signals) > 1 else self.signals[0]


class MockSourceHost:
    def __init__(self):
        self.prs = {}
        self.merged = []
        self.retargeted = []

    def checks(self, project, number):
        """Scripted per PR in check_states, green by default."""
        return getattr(self, "check_states", {}).get(number, ("pass", "mock checks"))

    def pr_state(self, project, number):
        return self.prs.get(number, "open")

    def mergeable(self, project, number):
        """Scripted per PR in mergeable_states, mergeable by default."""
        return getattr(self, "mergeable_states", {}).get(number, "mergeable")

    def merge(self, project, number):
        """A PR listed in merge_errors refuses to merge with that message."""
        if number in getattr(self, "merge_errors", {}):
            raise RuntimeError(self.merge_errors[number])
        self.prs[number] = "merged"
        self.merged.append(number)
        return f"sha{number:04d}"

    def retarget(self, project, number, base):
        self.retargeted.append((number, base))

    def diff(self, project, number):
        return f"diff --git a/file b/file\n# mock diff of PR {number}\n"
