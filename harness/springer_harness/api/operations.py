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

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..check.critique import critique
from ..common import iso, read_json, write_json
from ..errors import (ConfirmationInvalid, CritiqueErrors, IllegalTransition, InvalidArgs, NotAllowedForActor,
                      UnknownOperation)
from .. import risk_rules
from ..state.backlog import BacklogStore

CONFIRM_SECONDS = 300
PERSON_ONLY_GATES = {"production-release"}


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectConfigure(Args):
    ci_signal: Literal["receipts", "self-hosted-actions", "both"] | None = None
    source_host: Literal["local", "github"] | None = None


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
    lane: Literal["build", "polish"] | None = None  # the brief's lane when absent
    issue: str | None = Field(default=None, max_length=4000)  # the one issue a polish run takes
    burndown: bool = False  # a polish run over open backlog items instead of one issue
    story_ids: list[str] = []  # the items a burndown takes, or none for the open ones above the MVP line


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

    @field_validator("rule_change")
    @classmethod
    def _a_rule(cls, value):
        if value is None or not value.strip():
            return None
        risk_rules.parse(value)
        return value.strip()


class RunNote(Args):
    text: str = Field(min_length=1, max_length=4000)


class UnlockConfig(Args):
    path: str = Field(min_length=1, max_length=300)
    reason: str = Field(min_length=1, max_length=1000)


class SetRelease(Args):
    command: str = Field(min_length=1, max_length=500)  # the project's own deploy command
    confirm: str | None = Field(default=None, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")  # the word its prompt wants


class SetChecks(Args):
    commands: list[str] = Field(max_length=5)  # each a project command judged by its exit code; empty clears


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


class StoryRef(Args):
    story_id: str
    note: str | None = None


class ReconcileAnswer(Args):
    change_id: str
    option: Literal["decision", "not-architecture", "review"]
    text: str | None = Field(default=None, max_length=2000)


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


class RunRef(Args):
    run_id: str = Field(min_length=1, max_length=200)


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
        return BacklogStore(self.daemon.project_path(self.project))

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


# --- handlers ---

def project_create(c):
    return {"project": c.daemon.create_project(c.args.name, c.args.path, c.args.mode)}


def project_configure(c):
    """GitHub Actions can only report on a GitHub pull request, so a hosted CI signal
    needs the github source host. The host does not change under a run in progress,
    whose open changes belong to the host they were opened on."""
    changes = {k: v for k, v in (("ci_signal", c.args.ci_signal), ("source_host", c.args.source_host)) if v}
    merged = {**c.daemon.settings(c.project), **changes}
    if merged["ci_signal"] in ("self-hosted-actions", "both") and merged["source_host"] != "github":
        raise InvalidArgs("GitHub Actions as the CI signal needs the github source host")
    if "source_host" in changes and changes["source_host"] != c.daemon.settings(c.project)["source_host"] \
            and c.daemon.active_run(c.project):
        raise IllegalTransition(f"{c.project} has a run in progress, so its source host cannot change")
    # The daemon works from its own clone of a hosted project, and the working state
    # moves with it, so the clone is made or left before the setting says so.
    if changes.get("source_host") == "github":
        c.daemon.ensure_clone(c.project)
    elif changes.get("source_host") == "local":
        c.daemon.drop_clone(c.project)
    settings = c.daemon.save_settings(c.project, **changes)
    return {"settings": settings, "clone": c.daemon.home.project(c.project).get("clone")}


def project_archive(c):
    record = c.daemon.home.project(c.project)
    if c.daemon.active_run(c.project):
        raise IllegalTransition(f"{c.project} has a run in progress")
    c.daemon.home.save_project(c.project, {**record, "archived": True})
    return {}


def archive_run(c):
    c.daemon.archive_run(c.project, c.args.run_id)
    return {}


def restore_run(c):
    c.daemon.restore_run(c.project, c.args.run_id)
    return {}


def prune_run(c):
    return c.daemon.prune_run(c.project, c.args.run_id)


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
    if c.daemon.active_run(c.project):
        raise IllegalTransition(f"{c.project} already has a run in progress")
    if c.args.lane == "polish" and c.args.burndown:
        run_id = c.daemon.start_run(c.project, "build", lane="polish", burndown=True, story_ids=c.args.story_ids)
        brief = c.daemon.run_brief(c.project, run_id).get("content", {})
        return {"run_id": run_id, "story_ids": brief.get("story_ids", [])}
    if c.args.lane == "polish":
        # A polish run takes one issue in the person's words. The brief describes a
        # product that already exists, so it is context, not a gate on the start.
        if not (c.args.issue or "").strip():
            raise InvalidArgs("A polish run needs the issue, in your own words.")
        return {"run_id": c.daemon.start_run(c.project, "build", lane="polish", issue=c.args.issue.strip())}
    result = critique(front, sections)
    if result["errors"]:
        raise CritiqueErrors("The brief has blocking errors.", {"critique": result})
    return {"run_id": c.daemon.start_run(c.project, "build", lane=c.args.lane)}


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
    elif previous and c.args.option == "apply":
        c.daemon.commit_brief(c.project, c.daemon.project_path(c.project), c.run_id,
                              f"docs: the brief change applied at {c.args.gate_id}")
    if c.args.rule_change:
        c.daemon.apply_risk_rule(c.project, c.args.rule_change, c.args.gate_id)
        c.daemon.home.audit({"type": "risk.rule_change", "gate_id": c.args.gate_id, "rule": c.args.rule_change,
                             "actor": c.actor, "project": c.project}, c.daemon.now())
    return {}


def run_note(c):
    return {"units": c.engine.add_note(c.args.text.strip(), c.actor)}


UNLOCK_FILE = "runs/_config-unlock.json"


def unlock_config(c):
    """A ruling that lets a session edit one protected check file. The protection hook
    reads this file, and the harness copies it into every unit worktree."""
    rel = c.args.path.strip()
    rel = rel[2:] if rel.startswith("./") else rel
    parts = rel.split("/")
    if rel.startswith("/") or ".." in parts or rel == UNLOCK_FILE or not rel:
        raise InvalidArgs(f"{c.args.path} is not a path inside the project that can be unlocked")
    path = c.daemon.project_path(c.project) / UNLOCK_FILE
    record = read_json(path) or {}
    entries = [e for e in record.get("paths", []) if isinstance(e, dict) and e.get("path") != rel]
    entries.append({"path": rel, "reason": f"{c.args.reason.strip()} Ruled by {c.actor}."})
    write_json(path, {**record, "paths": entries})
    return {"path": rel, "unlocked": len(entries)}


def set_release(c):
    return {"settings": c.daemon.save_settings(c.project, release_command=c.args.command.strip(),
                                               release_confirm=c.args.confirm)}


def set_checks(c):
    commands = [command.strip() for command in c.args.commands if command.strip()]
    if any(len(command) > 300 for command in commands):
        raise InvalidArgs("a check command is at most 300 characters")
    return {"settings": c.daemon.save_settings(c.project, project_checks=commands)}


def project_release(c):
    """A release a person asked for, outside a run's release gate. The confirm on this
    operation is the go."""
    out_dir, why_not = c.daemon.release(c.project, c.actor, reason="asked for")
    if why_not:
        raise IllegalTransition(why_not)
    return {"started": True}


def daemon_restart(c):
    c.daemon.request_restart(c.actor)
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


def close_story(c):
    return {"closed": c.backlog.close_story(c.args.story_id, "human", iso(c.daemon.now()), note=c.args.note,
                                            by=c.actor)}


def reopen_story(c):
    c.backlog.reopen_story(c.args.story_id)
    return {}


def reconcile_answer(c):
    return {"answer": c.daemon.reconciler.answer(c.project, c.args.change_id, c.args.option, c.args.text, c.actor,
                                                 c.daemon.now())}


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
              "Sets the project's source host (local merges, or GitHub pull requests) and its CI signal, "
              "the check a change must pass before the harness merges it.",
              confirm=True, confirm_rule="yes"),
    Operation("project.archive", NoArgs, project_archive, "Hides the project and refuses a new run. Deletes nothing.",
              confirm=True, confirm_rule="yes"),
    Operation("project.archive_run", RunRef, archive_run,
              "Hides a finished run from the runs list. Deletes nothing, and restore brings it back."),
    Operation("project.restore_run", RunRef, restore_run, "Shows an archived run in the runs list again."),
    Operation("project.prune_run", RunRef, prune_run,
              "Removes an archived run's folder. Its tracked files leave in one pull request (one commit on a "
              "local project), except files the repository cites by path, and its ignored working state moves "
              "to the daemon's home under pruned/.",
              # A prune that will be refused is refused at once rather than after a confirmation.
              confirm=lambda c: c.args.run_id in c.daemon.archived_runs(c.project),
              confirm_rule="yes, once archived", chat=False),
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
    Operation("run.note", RunNote, run_note,
              "Adds a person's note to the next session brief of every open unit in the run.",
              scope="run", chat=False),
    Operation("project.unlock_config", UnlockConfig, unlock_config,
              "Records a ruling in runs/_config-unlock.json that lets a session edit one protected check file.",
              confirm=True, confirm_rule="yes", chat=False),
    Operation("project.set_release", SetRelease, set_release,
              "Sets the command the daemon runs to deploy to production after a person says go, and the word "
              "it types when that command asks for one.", confirm=True, confirm_rule="yes", chat=False),
    Operation("project.set_checks", SetChecks, set_checks,
              "Sets the checks the harness runs on every unit that changes code, after the plan's own gating "
              "commands. A failing check sends the unit back like a failing test.",
              confirm=True, confirm_rule="yes", chat=False),
    Operation("project.release", NoArgs, project_release,
              "Deploys the project's default branch head to production with its release command, now.",
              confirm=True, confirm_rule="yes", chat=False, status="accepted"),
    Operation("daemon.restart", NoArgs, daemon_restart,
              "Pauses every run, waits until no session is running, restarts the daemon, and resumes the runs.",
              scope="none", confirm=True, confirm_rule="yes", chat=False),
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
    Operation("backlog.close_story", StoryRef, close_story,
              "Closes the story by hand. Its column is done from then on, whatever its units do.", scope="run"),
    Operation("backlog.reopen_story", StoryRef, reopen_story, "Drops the closed record.", scope="run"),
    Operation("project.reconcile_answer", ReconcileAnswer, reconcile_answer,
              "Answers reconcile's question on an external change in a gate-list area: decision records the "
              "decision-log line, not-architecture records that it is none, review opens a polish run on it.",
              chat=False),
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
                            "preview": {"summary": op.effect, "consequences":
                                        [f"{k}: {v}" for k, v in self._redact(op, raw_args).items()]}}
                self._spend_token(confirm_token, bound)
            result = op.handler(ctx)
            if kind.startswith("backlog."):
                # A person's backlog edit is a tracked file, and left uncommitted it sits as a
                # change in the project checkout until a run's records happen to take it.
                self.daemon.commit_backlog(project, kind.split(".", 1)[1].replace("_", " "))
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
