"""The Plan seam. The orchestrator agent names the next units, and a canned planner
stands in for it until step 6. Either returns drafts, and the engine owns the ids."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class UnitDraft:
    key: str
    agent: str
    expected_outcome: str = "the unit's artifact"
    brief: str = "Do the work."
    declared_paths: tuple = ()
    depends_on: tuple = ()  # keys in this run, across batches
    risk_baseline: str = "L0"
    model_tier: str = "sonnet"
    workstream: str | None = None
    executable_check: str | None = None
    wall_clock_seconds: int = 3600


@dataclass
class GateDraft:
    checkpoint_type: str
    prompt: str
    holds: tuple = ()  # keys of units whose start waits
    level: str = "L3"
    options: tuple = ()
    decisions: tuple = ()
    artifact_ref: str = "none"


@dataclass
class PlanBatch:
    phase: str
    rationale: str
    units: list = field(default_factory=list)
    gates: list = field(default_factory=list)
    next_phase: str | None = None
    barrier: bool = True  # wait until nothing is in flight or open before this batch


@dataclass
class Snapshot:
    in_flight: int
    nonterminal: int
    open_gates: int


class Planner(Protocol):
    def next_batch(self, snapshot: Snapshot) -> PlanBatch | None: ...

    def finished(self) -> bool: ...


class CannedPlanner:
    """Replays a list of batches. A barrier batch waits for all earlier work."""

    def __init__(self, batches):
        self.batches = list(batches)

    def next_batch(self, snapshot):
        if not self.batches:
            return None
        batch = self.batches[0]
        if batch.barrier and (snapshot.nonterminal or snapshot.open_gates):
            return None
        return self.batches.pop(0)

    def finished(self):
        return not self.batches
