"""The coding agent provider contract. The daemon never depends on which agent runs.

spawn(request) starts a session and returns a handle the scheduler polls once per
tick. The contract fixes where a session leaves its outputs: return.txt, result.json,
and handoff.md under the session directory, so Check reads files and not a transcript.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class SpawnRequest:
    unit_id: str
    session_id: str
    agent: str
    role_prompt_ref: str
    model_tier: str
    brief: str
    allowlist: tuple
    mcp_config_ref: str | None
    cwd: Path
    session_dir: Path
    attempt: int = 1
    env: dict = field(default_factory=dict)  # set in the session's environment


@dataclass(frozen=True)
class SessionExit:
    outcome: str  # return, handoff, or killed
    code: int | None = 0


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    context_percent: float = 0
    cost_usd: float = 0


class SessionHandle(Protocol):
    pid: int | None
    provider_session_id: str | None
    model: str

    def poll(self) -> list[dict]:
        """Stream events since the last poll."""

    def usage(self) -> Usage: ...

    def alive(self) -> bool: ...

    def exit(self) -> SessionExit | None:
        """The exit, once the session ended on its own terms. None while it runs,
        and None forever for a session that died, which alive() reports."""

    def kill(self) -> None: ...


class CodingAgentProvider(Protocol):
    name: str

    def spawn(self, request: SpawnRequest) -> SessionHandle: ...

    def usage_signal(self) -> dict | None:
        """{"used_fraction", "resets_at"}, or None when the provider exposes none."""


@dataclass(frozen=True)
class CheckResult:
    """What a session's outputs say. Check turns this into a unit transition."""

    status: str
    outcome: str = "artifact"
    pr: dict | None = None
    touched_paths: tuple = field(default_factory=tuple)
    failure_class: str | None = None
    detail: str = ""
    raised_level: str | None = None
    findings: tuple = field(default_factory=tuple)
