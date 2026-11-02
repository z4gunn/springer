"""The closed catalog of writes, and the one path every write takes.

A click, the chat agent, and a notification reply all arrive here, so idempotency,
confirmation, the actor rules, and the audit log each exist once. See Operations in
docs/harness/api-contract.md.
"""

import hashlib
import json
import secrets as stdlib_secrets
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..check.critique import critique
from ..common import read_json
from ..errors import (ConfirmationInvalid, CritiqueErrors, IllegalTransition, InvalidArgs, NotAllowedForActor,
                      UnknownOperation)
from ..state.backlog import BacklogStore

CONFIRM_SECONDS = 300
PERSON_ONLY_GATES = {"production-release"}


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectConfigure(Args):
    ci_signal: Literal["receipts", "self-hosted-actions", "both"] | None = None
    staging: dict | None = None
    clear_staging: bool = False


class StagingDeploy(Args):
    dry_run: bool = True


class ProjectCreate(Args):
    name: str = Field(min_length=1)
    path: str = Field(min_length=1)
    mode: Literal["new", "adopt"]


class UpdateSection(Args):
    section: str = Field(min_length=1)
    body: str
    base_version: int


class UpdateFacts(Args):
    facts: dict
    base_version: int


class ConfirmSection(Args):
    section: str = Field(min_length=1)
    base_version: int


class RunDiscovery(Args):
    sections: list[str] | Literal["all"]


class RunStart(Args):
    base_version: int


class RunPause(Args):
    reason: str = ""


class UnitRef(Args):
    unit_id: str


class UnitRedispatch(Args):
    unit_id: str
    model_tier: Literal["haiku", "sonnet", "opus"] | None = None


class DecisionAnswer(Args):
    decision_id: str
    response: str


class GateAnswer(Args):
    gate_id: str
    option: str
    decisions: list[DecisionAnswer] = []
    free_text: str | None = None
    rule_change: str | None = None


class MarkViewed(Args):
    gate_ids: list[str]


class MoveLine(Args):
    after_feature_id: str


class FeatureRef(Args):
    feature_id: str


class Reorder(Args):
    story_id: str
    position: int = Field(ge=0)


class AddBug(Args):
    title: str = Field(min_length=1)
    description: str = ""
    severity: Literal["critical", "high", "medium", "low"] = "medium"


class AnswerUnknown(Args):
    unknown_id: str
    answer: str


class SetSecret(Args):
    item_id: str
    value: str = Field(min_length=1)


class RoleModel(Args):
    role: str
    model: str


class GateChannels(Args):
    level: Literal["L0", "L1", "L2", "L3"]
    channels: list[str]


class NoArgs(Args):
    pass


@dataclass
class Context:
    daemon: object
    op: "Operation"
    args: BaseModel
    project: str | None
    run_id: str | None
    actor: str

    @property
    def engine(self):
        return self.daemon.engine(self.project, self.run_id)

    @property
    def brief(self):
        return self.daemon.brief(self.project)

    @property
    def backlog(self):
        return BacklogStore(self.engine.run_dir)

    def scope_review_open(self):
        return any(g["content"]["checkpoint_type"] == "scope-review" for g in self.engine.gates.open_gates())

    def brief_change(self, write):
        """After run.start an edit opens a scope-change gate on the active run, and the
        answer can restore what the brief held before it."""
        active = self.daemon.active_run(self.project)
        if not self.daemon.started(self.project) or active is None:
            return {"version": write()}
        previous = self.brief.text()
        version = write()
        engine = self.daemon.engine(self.project, active)
        gate = engine.gates.open(
            "scope-change", "L3", [], "The brief changed after the run started.",
            [{"option": "apply", "consequence": "The change stands, and the next Plan reads it.",
              "recommended_because": "You just made this edit."},
             {"option": "discard", "consequence": "The brief returns to what it was."}],
            artifact_ref="docs/brief.md", context={"previous_brief": previous})
        return {"version": version, "gate_id": gate["content"]["checkpoint_id"]}


@dataclass
class Operation:
    type: str
    args: type
    handler: object
    effect: str
    scope: str = "project"  # none, project, or run
    confirm: object = False  # True, False, or a function of the Context
    confirm_rule: str = "no"
    chat: bool = True
    secret_fields: tuple = field(default_factory=tuple)
    status: str = "applied"
    preview: object = None  # a function of the Context, the lines a confirmation shows


# --- handlers ---

def project_create(c):
    return {"project": c.daemon.create_project(c.args.name, c.args.path, c.args.mode)}


def project_configure(c):
    from ..providers.staging import StagingError, validate
    changes = {}
    if c.args.ci_signal:
        changes["ci_signal"] = c.args.ci_signal
    if c.args.clear_staging:
        changes.update(staging=None, dry_run_seen=False, deploy_confirmed=False)
    elif c.args.staging is not None:
        try:
            host = validate(c.args.staging)
        except StagingError as exc:
            raise InvalidArgs(str(exc))
        # A changed host is a new deploy, so it is shown and confirmed again.
        changes.update(staging=host, dry_run_seen=False, deploy_confirmed=False)
    return {"settings": c.daemon.save_settings(c.project, **changes)}


def _deploy_commands(c):
    from ..providers.staging import describe, plan
    settings = c.daemon.settings(c.project)
    if not settings["staging"]:
        raise IllegalTransition(f"{c.project} has no staging host. Register one first.")
    return describe(plan(settings["staging"], c.daemon.project_path(c.project)))


def staging_deploy(c):
    settings = c.daemon.settings(c.project)
    commands = _deploy_commands(c)
    if c.args.dry_run:
        c.daemon.save_settings(c.project, dry_run_seen=True)
        return {"dry_run": True, "commands": commands}
    if not settings["dry_run_seen"]:
        raise IllegalTransition("Run a dry run first, so you have seen what the deploy does.")
    c.daemon.save_settings(c.project, deploy_confirmed=True)
    ok, log = c.daemon.deploy(c.project)
    return {"dry_run": False, "ok": ok, "log": log[-4000:]}


def _deploy_needs_confirming(c):
    return not c.args.dry_run and not c.daemon.settings(c.project)["deploy_confirmed"]


def project_archive(c):
    record = c.daemon.home.project(c.project)
    if c.daemon.active_run(c.project):
        raise IllegalTransition(f"{c.project} has a run in progress")
    c.daemon.home.save_project(c.project, {**record, "archived": True})
    return {}


def update_section(c):
    return c.brief_change(lambda: c.brief.update_section(c.args.section, c.args.body, c.args.base_version))


def update_facts(c):
    return c.brief_change(lambda: c.brief.update_facts(c.args.facts, c.args.base_version))


def confirm_section(c):
    return {"version": c.brief.confirm_section(c.args.section, c.args.base_version)}


def run_discovery(c):
    sections = c.args.sections
    return {"run_id": c.daemon.start_run(c.project, "discovery", None if sections == "all" else sections)}


def dismiss_recommendation(c):
    return {"version": c.brief.dismiss_recommendation()}


def run_start(c):
    c.brief.check_version(c.args.base_version)
    front, sections = c.brief.load()
    result = critique(front, sections, c.daemon.home.config().get("staging_hosts", []))
    if result["errors"]:
        raise CritiqueErrors("The brief has blocking errors.", {"critique": result})
    if c.daemon.started(c.project) and c.daemon.active_run(c.project):
        raise IllegalTransition(f"{c.project} already has a run in progress")
    return {"run_id": c.daemon.start_run(c.project, "build")}


def noop(c):
    return {}


def run_cancel(c):
    c.engine.cancel_run(c.actor)
    return {}


def unit_cancel(c):
    c.engine.cancel_unit(c.args.unit_id, c.actor)
    return {}


def unit_redispatch(c):
    c.engine.redispatch_unit(c.args.unit_id)
    return {}


def gate_answer(c):
    engine = c.engine
    gate = engine.gates.get(c.args.gate_id)["content"]
    if gate["checkpoint_type"] in PERSON_ONLY_GATES and c.actor == "chat":
        raise NotAllowedForActor("A production release is never answered by the chat line.")
    engine.gates.answer(c.args.gate_id, c.args.option, c.actor, c.args.free_text, c.args.rule_change,
                        [d.model_dump() for d in c.args.decisions])
    previous = gate.get("context", {}).get("previous_brief")
    if previous and c.args.option == "discard":
        c.brief.restore(previous)
    if c.args.rule_change:
        c.daemon.home.audit({"type": "risk.rule_change", "gate_id": c.args.gate_id, "rule": c.args.rule_change,
                             "actor": c.actor, "project": c.project}, c.daemon.now())
    return {}


def mark_viewed(c):
    for gate_id in c.args.gate_ids:
        c.engine.gates.close_digest(gate_id, c.actor)
    return {}


def move_line(c):
    c.backlog.move_mvp_line(c.args.after_feature_id)
    return {}


def defer_feature(c):
    c.backlog.set_deferred(c.args.feature_id, True)
    return {}


def restore_feature(c):
    c.backlog.set_deferred(c.args.feature_id, False)
    return {}


def reorder(c):
    c.backlog.reorder(c.args.story_id, c.args.position)
    return {}


def add_bug(c):
    return {"story_id": c.backlog.add_bug(c.args.title, c.args.description, c.args.severity)}


def answer_unknown(c):
    c.backlog.answer_unknown(c.args.unknown_id, c.args.answer)
    return {}


def set_secret(c):
    items = None
    for run_id in reversed(c.daemon.run_ids(c.project)):
        items = read_json(c.daemon.project_path(c.project) / "runs" / run_id / "provisioning.json")
        if items:
            break
    item = next((i for i in items or [] if i["item_id"] == c.args.item_id), None)
    if item is None:
        raise InvalidArgs(f"no provisioning item {c.args.item_id}")
    c.daemon.secrets.set(c.project, item["secret_name"], c.args.value)
    return {"item_id": c.args.item_id, "present": True}


def set_role_model(c):
    config = c.daemon.home.config()
    config["role_models"][c.args.role] = c.args.model
    c.daemon.home.save_config(config)
    return {}


def set_gate_channels(c):
    config = c.daemon.home.config()
    config["gate_channels"][c.args.level] = c.args.channels
    c.daemon.home.save_config(config)
    return {}


def _after_start(c):
    return c.daemon.started(c.project)


def _outside_scope_review(c):
    return not c.scope_review_open()


def _rule_change(c):
    return bool(c.args.rule_change)


CATALOG = {op.type: op for op in [
    Operation("project.create", ProjectCreate, project_create, "Scaffolds or adopts the repository and registers it.",
              scope="none", confirm=True, confirm_rule="yes"),
    Operation("project.configure", ProjectConfigure, project_configure,
              "Sets the project's CI signal and staging host. A changed host is shown and confirmed again.",
              confirm=True, confirm_rule="yes"),
    Operation("staging.deploy", StagingDeploy, staging_deploy,
              "A dry run lists the deploy's commands and runs nothing. A real deploy needs a dry run first and is "
              "confirmed once per project. After that, a merge deploys on its own.",
              confirm=_deploy_needs_confirming, confirm_rule="the first real deploy", preview=_deploy_commands),
    Operation("project.archive", NoArgs, project_archive, "Hides the project and refuses a new run. Deletes nothing.",
              confirm=True, confirm_rule="yes"),
    Operation("brief.update_section", UpdateSection, update_section,
              "Writes the section and marks it confirmed. After run.start it opens a scope-change gate.",
              confirm=_after_start, confirm_rule="after start"),
    Operation("brief.update_facts", UpdateFacts, update_facts,
              "Writes the frontmatter and recomputes derived. After run.start it opens a scope-change gate.",
              confirm=_after_start, confirm_rule="after start"),
    Operation("brief.confirm_section", ConfirmSection, confirm_section, "Marks a proposed section confirmed unchanged."),
    Operation("brief.run_discovery", RunDiscovery, run_discovery, "Dispatches Discovery against the named sections.",
              confirm=True, confirm_rule="yes", status="accepted"),
    Operation("brief.dismiss_recommendation", NoArgs, dismiss_recommendation, "Hides the go or no-go banner."),
    Operation("run.start", RunStart, run_start, "Commits the brief and opens the run.",
              confirm=True, confirm_rule="yes", status="accepted"),
    Operation("run.pause", RunPause, noop, "Stops claiming and dispatching. In-flight sessions finish and Check still runs.",
              scope="run"),
    Operation("run.resume", NoArgs, noop, "Clears the pause.", scope="run"),
    Operation("run.cancel", NoArgs, run_cancel, "Cancels every unfinished unit and ends the run, so a new one can start. "
              "Open PRs stay open.", scope="run", confirm=True, confirm_rule="yes"),
    Operation("unit.cancel", UnitRef, unit_cancel, "Kills the live session and moves the unit to cancelled.",
              scope="run", confirm=True, confirm_rule="yes"),
    Operation("unit.redispatch", UnitRedispatch, unit_redispatch,
              "Kills the live session if any and moves the unit to redispatch. No retry is spent.",
              scope="run", confirm=True, confirm_rule="yes"),
    Operation("gate.answer", GateAnswer, gate_answer, "Records the response and releases what the gate holds.",
              scope="run", confirm=_rule_change, confirm_rule="with rule_change"),
    Operation("digest.mark_viewed", MarkViewed, mark_viewed, "Closes digest entries.", scope="run"),
    Operation("backlog.move_mvp_line", MoveLine, move_line, "Moves the MVP line.", scope="run",
              confirm=_outside_scope_review, confirm_rule="outside scope review"),
    Operation("backlog.defer_feature", FeatureRef, defer_feature, "Tags the feature deferred. Its tasks stay in the graph.",
              scope="run", confirm=_outside_scope_review, confirm_rule="outside scope review"),
    Operation("backlog.restore_feature", FeatureRef, restore_feature, "Clears the deferred tag.", scope="run",
              confirm=_outside_scope_review, confirm_rule="outside scope review"),
    Operation("backlog.reorder", Reorder, reorder, "Reorders within a wave.", scope="run"),
    Operation("backlog.add_bug", AddBug, add_bug, "Adds a bug to the backlog.", scope="run"),
    Operation("backlog.answer_unknown", AnswerUnknown, answer_unknown, "Records the answer.", scope="run"),
    Operation("provisioning.set_secret", SetSecret, set_secret,
              "Stores the value in the OS keyring. The value is never logged, returned, or recorded.",
              chat=False, secret_fields=("value",)),
    Operation("config.set_role_model", RoleModel, set_role_model, "Changes the model for a role.", scope="none",
              confirm=True, confirm_rule="yes"),
    Operation("config.set_gate_channels", GateChannels, set_gate_channels, "Changes where gates of that level notify.",
              scope="none", confirm=True, confirm_rule="yes"),
]}


def catalog_view():
    return [{"type": op.type, "effect": op.effect, "scope": op.scope, "confirm": op.confirm_rule, "chat": op.chat,
             "args_schema": op.args.model_json_schema()} for op in CATALOG.values()]


class Operations:
    def __init__(self, daemon):
        self.daemon = daemon
        self.tokens = {}
        self.applied = {line["op_id"]: line["outcome"] for line in daemon.home.audit_lines() if line.get("op_id")}

    def _bind(self, kind, project, run_id, args):
        payload = json.dumps([kind, project, run_id, args], sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()

    def _validate(self, op, raw):
        try:
            return op.args.model_validate(raw)
        except ValidationError as exc:
            raise InvalidArgs(f"{op.type}: args do not match its schema",
                              {"errors": exc.errors(include_url=False, include_context=False, include_input=False)}) from None

    def _scope(self, op, project, run_id):
        if op.scope in ("project", "run"):
            if not project:
                raise InvalidArgs(f"{op.type} needs a project")
            self.daemon.home.project(project)
        if op.scope == "run":
            if not run_id:
                raise InvalidArgs(f"{op.type} needs a run_id")
            engine = self.daemon.engine(project, run_id)
            engine.require_writable()

    def _needs_confirmation(self, op, ctx, actor):
        if actor == "chat":
            return True
        return op.confirm(ctx) if callable(op.confirm) else op.confirm

    def _spend_token(self, token, bound):
        record = self.tokens.pop(token, None)
        if record is None or record["bound"] != bound or self.daemon.now() > record["expires"]:
            raise ConfirmationInvalid("The confirm token is expired, used, or bound to other args.")

    def apply(self, op_id, kind, project, run_id, raw_args, confirm_token, actor):
        op = CATALOG.get(kind)
        if op is None:
            raise UnknownOperation(f"{kind} is not in the catalog")
        with self.daemon.lock:
            if op_id in self.applied:
                return self.applied[op_id]
            args = self._validate(op, raw_args)
            if actor == "chat" and not op.chat:
                raise NotAllowedForActor(f"{kind} is refused for the chat line.")
            self._scope(op, project, run_id)
            ctx = Context(self.daemon, op, args, project, run_id, actor)
            bound = self._bind(kind, project, run_id, raw_args)
            if self._needs_confirmation(op, ctx, actor):
                if confirm_token is None:
                    token = stdlib_secrets.token_urlsafe(24)
                    self.tokens[token] = {"bound": bound, "expires": self.daemon.now() + CONFIRM_SECONDS}
                    return {"op_id": op_id, "type": kind, "status": "needs_confirmation", "confirm_token": token,
                            "preview": {"summary": op.effect, "consequences": op.preview(ctx) if op.preview else
                                        [f"{k}: {v}" for k, v in self._redact(op, raw_args).items()]}}
                self._spend_token(confirm_token, bound)
            result = op.handler(ctx)
            return self._record(op, op_id, project, run_id, raw_args, actor, result)

    def _redact(self, op, raw_args):
        return {k: v for k, v in raw_args.items() if k not in op.secret_fields}

    def _record(self, op, op_id, project, run_id, raw_args, actor, result):
        run = run_id or result.get("run_id")
        args = self._redact(op, raw_args)
        cursor = None
        if project and run:
            engine = self.daemon.engine(project, run)
            _, cursor = engine.ledger.append("operation_applied", op_id=op_id, type=op.type, actor=actor, args=args)
            engine.project()
        outcome = {"op_id": op_id, "type": op.type, "status": op.status, "cursor": cursor, "result": result}
        self.applied[op_id] = outcome
        self.daemon.home.audit({"op_id": op_id, "type": op.type, "actor": actor, "project": project or
                                result.get("project"), "run_id": run, "args": args, "outcome": outcome},
                               self.daemon.now())
        return outcome
