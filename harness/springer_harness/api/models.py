"""The payloads this API defines. A payload with a schema under runtime/schemas is
served in that shape and only named here, because the schema already owns it."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Open(BaseModel):
    """A view over a record that has its own schema, so extra fields pass through."""

    model_config = ConfigDict(extra="allow")


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict = {}


class ErrorResponse(BaseModel):
    error: ErrorBody


class Health(BaseModel):
    status: str
    api_version: str
    harness_version: str
    build: str


class DaemonView(BaseModel):
    state: Literal["running", "parked"]
    parked_until: str | None
    started_at: str
    degradations: list[str]


class ActiveRun(BaseModel):
    run_id: str
    phase: str
    open_gates: int
    in_flight: int
    paused: bool
    waiting_on: Literal["usage_window", "gate", "provisioning"] | None
    externally_held: bool


class ProjectSummary(BaseModel):
    slug: str
    name: str
    path: str
    profile: str | None
    deploy: str | None
    runtime_version: str | None
    archived: bool
    active_run: ActiveRun | None
    adopted: bool = False
    hand_merge: list[str] = []  # renderings under .claude/springer-update/ awaiting a hand merge
    lane: str | None = None
    settings: dict = {}  # ci_signal, staging, dry_run_seen, deploy_confirmed
    adopted_brief_version: int | None = None  # a build on an adopted project waits for a brief delta
    has_design: bool = False  # docs/design/index.html exists


class SectionView(BaseModel):
    name: str
    required: bool
    confidence: Literal["confirmed", "proposed", "needs-human-input"]
    body: str


class Derived(BaseModel):
    profile: str
    lane: str
    sentence: str


class BriefView(BaseModel):
    version: int
    started: bool
    facts: dict
    derived: Derived
    sections: list[SectionView]
    recommendation: dict | None


class CritiqueItem(BaseModel):
    rule: str
    section: str
    message: str


class Critique(BaseModel):
    errors: list[CritiqueItem]
    warnings: list[CritiqueItem]
    info: list[CritiqueItem]


class ProvisioningItem(BaseModel):
    item_id: str
    secret_name: str
    needed_by: str | None = None
    present: bool


class RunSummary(BaseModel):
    run_id: str
    kind: str
    phase: str
    complete: bool
    paused: bool


class BacklogView(Open):
    as_of: str
    state: Literal["generated", "not_generated"]
    epics: list[dict]
    unknowns: list[dict]


class Page(BaseModel):
    items: list[dict]
    next_cursor: str | None


class Metrics(BaseModel):
    product_checks_per_100_dispatches: float
    failure_class_mix: dict
    dispatches: int
    list_price_spend_usd: float
    daily_cap_usd: float | None


class DesignSession(BaseModel):
    url: str
    expires_at: str


class OperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op_id: str
    type: str
    project: str | None = None
    run_id: str | None = None
    args: dict = {}
    confirm_token: str | None = None


class OperationResponse(BaseModel):
    op_id: str
    type: str
    status: Literal["applied", "accepted", "needs_confirmation"]
    cursor: str | None = None
    result: dict = {}
    preview: dict | None = None
    confirm_token: str | None = None


class CatalogEntry(BaseModel):
    type: str
    effect: str
    scope: Literal["none", "project", "run"]
    confirm: str
    chat: bool
    args_schema: dict


class ChatRequest(BaseModel):
    session_id: str | None = None
    project: str | None = None
    message: str
