"""The harness state schemas: each accepts a valid record, rejects a
representative invalid one, accepts what the runtime writes today, and agrees
with the tables in the state-model reference."""

import json
import re
import tempfile
import unittest
from pathlib import Path

from helpers import REPO, SCHEMAS, RunStore, header, load_script, read_events, run_hook

try:
    import jsonschema  # noqa: F401
    from jsonschema import Draft202012Validator
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

REFERENCE = (REPO / "runtime" / "references" / "state-model.md").read_text()
TS = "2026-11-01T12:00:00Z"


def schema(name):
    return json.loads((SCHEMAS / f"{name}.json").read_text())


def table_first_column(section):
    """The first-column values of the table under one heading of the reference."""
    body = REFERENCE.split(f"## {section}\n", 1)[1].split("\n## ", 1)[0]
    rows = [line for line in body.splitlines() if line.startswith("|")][2:]
    return [row.split("|")[1].strip() for row in rows]


def unit_spec():
    return {"artifact_type": "unit-spec", "schema_version": "v1", "unit_id": "U-0412", "cycle_id": "CYCLE-0007",
            "agent": "spgr-agent-backend-developer", "role_prompt_ref": ".claude/agents/spgr-agent-backend-developer.md",
            "model_tier": "sonnet", "brief": "Build the orders route.", "input_artifact_refs": ["story-brief-1"],
            "expected_outcome": "an open PR with green receipts", "workstream": "core",
            "declared_paths": ["packages/api/orders/"], "allowlist": ["Bash(pnpm test:*)"], "mcp_config_ref": None,
            "budget": {"tokens": 200000, "wall_clock_seconds": 3600}, "risk_baseline": "L0",
            "dependencies": ["U-0411"], "executable_check": "pnpm test orders"}


def unit_state():
    return {"artifact_type": "unit-state", "schema_version": "v1", "unit_id": "U-0412", "state": "running",
            "entered_at": TS, "history": [{"state": "planned", "at": TS, "reason": "cycle planned"}],
            "retries_spent": 0, "sessions": ["S-0001"], "pr": None, "merge": None, "cancelled_by": None}


def session():
    return {"artifact_type": "session", "schema_version": "v1", "session_id": "S-0001", "unit_id": "U-0412",
            "provider": "claude-code", "provider_session_id": "abc", "pid": 4242, "model": "claude-sonnet-5-5",
            "tier": "sonnet", "state": "exited", "started_at": TS, "ended_at": TS, "exit_code": 0, "outcome": "return",
            "input_tokens": 10, "output_tokens": 5, "context_percent_at_exit": 12.5, "cost_usd_list_price": 0.01}


def usage_window():
    return {"artifact_type": "usage-window", "schema_version": "v1", "provider": "claude-code", "window_start": TS,
            "resets_at": TS, "used_fraction": 0.4, "own_tokens": 1000, "dispatch_rate": 2}


def gate(**content):
    obj = header("G-0001", "hil-checkpoint", "gate")
    obj["schema_version"] = "v2"
    obj["content"] = {"checkpoint_id": "G-0001", "checkpoint_type": "pr-merge", "artifact_ref": "pull-request-1",
                      "decision_prompt": "Merge this auth change?",
                      "options": [{"option": "approve", "consequence": "It merges.", "recommended_because": "Reviewed."}],
                      "pipeline_status": "paused", "level": "L2", "holds": ["U-0412"], "digest": False, **content}
    return obj


def run_state(**content):
    obj = header("run-state-demo", "run-state", "run_state")
    obj["schema_version"] = "v2"
    obj["content"] = {"run_id": "demo", "regenerable": True, "active_phase": "development", "cycle_counter": 3,
                      "wip_board": {"backlog": [], "development": ["S-1"], "review": [], "validation": [], "done": []},
                      "units": {"running": 1, "done": 4}, "paused": False, "waiting_on": None,
                      "in_flight": [{"unit_id": "U-0412", "session_id": "S-0001", "agent": "spgr-agent-qa-tester",
                                     "model": "claude-sonnet-5-5", "started_at": TS, "context_percent": 10, "cost": 0.2,
                                     "last_tool_call": "Bash"}],
                      "open_gates": [{"id": "G-0001", "level": "L2", "holds": ["U-0412"], "age_seconds": 60}],
                      "worktrees": [{"unit_id": "U-0412", "path": "/tmp/w/U-0412"}], "mvp_line": None, "deferred": [],
                      "window": {"provider": "claude-code", "used_fraction": None, "resets_at": TS},
                      "generated_from_seq": 91, **content}
    return obj


def event(name, **fields):
    return {"ts": TS, "event": name, "seq": 1, "run_id": "demo", **fields}


DAEMON_EVENTS = {
    "cleaned_up": {"released": ["U-0412"], "kept": [], "branches": ["unit/U-0412", "origin/unit/U-0412"]},
    "check_warning": {"unit_id": "U-0412", "detail": "unit exited 0 but printed no test count"},
    "release_started": {"sha": "abc123", "by": "channel:slack", "reason": "G-0009", "command": "npm run deploy"},
    "release_finished": {"sha": "abc123", "by": "channel:slack", "exit_code": 0, "detail": "shipped"},
    "release_failed": {"by": "channel:slack", "sha": None, "exit_code": None, "detail": "dirty checkout"},
    "release_declined": {"gate_id": "G-0009", "by": "channel:slack"},
    "unit_state": {"unit_id": "U-0412", "from": None, "to": "planned", "reason": "cycle planned"},
    "session_started": {"unit_id": "U-0412", "session_id": "S-0001", "provider": "claude-code", "pid": 42, "model": "m", "tier": "opus"},
    "session_usage": {"unit_id": "U-0412", "session_id": "S-0001", "input_tokens": 1, "output_tokens": 1, "context_percent": 3, "cost": 0},
    "session_exited": {"unit_id": "U-0412", "session_id": "S-0001", "code": None, "outcome": "dead"},
    "worktree_claimed": {"unit_id": "U-0412", "path": "/w", "branch": "b"},
    "worktree_released": {"unit_id": "U-0412", "path": "/w", "branch": "b"},
    "worktree_kept": {"unit_id": "U-0412", "path": "/w", "reason": "dirty"},
    "gate_opened": {"gate_id": "G-0001", "level": "L2", "holds": ["U-0412"]},
    "merge_failed": {"unit_id": "U-0412", "pr": 7, "detail": "not mergeable"},
    "restacked": {"unit_id": "U-0412", "pr": 7, "onto": "U-0411"},
    "restack_failed": {"unit_id": "U-0412", "pr": 7, "detail": "CONFLICT"},
    "tick_failed": {"detail": "RuntimeError: boom"},
    "tick_stalled": {"count": 3, "detail": "RuntimeError: boom"},
    "gate_answered": {"gate_id": "G-0001", "response": "approve", "by": "human"},
    "merge": {"unit_id": "U-0412", "pr": 7, "sha": "abc"},
    "retrieval": {"unit_id": "U-0412", "record_ids": ["adr-1"]},
    "window_sample": {"provider": "claude-code", "used_fraction": 0.5, "resets_at": TS},
    "operation_applied": {"op_id": "op-1", "type": "run.pause", "actor": "tui", "args": {"reason": "lunch"}},
}


@unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed in this interpreter")
class StateSchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validate = load_script(SCHEMAS / "validate.py")
        cls.registry = cls.validate.load_registry()

    def errors(self, name, obj):
        return list(Draft202012Validator(schema(name), registry=self.registry).iter_errors(obj))

    def assertValid(self, name, obj):
        self.assertEqual([e.message for e in self.errors(name, obj)], [])

    def assertInvalid(self, name, obj):
        self.assertTrue(self.errors(name, obj), f"{name} accepted {obj}")

    def changed(self, base, **fields):
        return {**base, **fields}

    def test_valid_records_pass(self):
        for name, obj in (("unit-spec-v1", unit_spec()), ("unit-state-v1", unit_state()), ("session-v1", session()),
                          ("usage-window-v1", usage_window()), ("hil-checkpoint-v2", gate()), ("run-state-v2", run_state())):
            with self.subTest(name):
                self.assertValid(name, obj)

    def test_records_validate_through_the_registry_entry_point(self):
        for obj in (unit_spec(), unit_state(), session(), usage_window(), gate(), run_state()):
            with self.subTest(obj["artifact_type"]), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "record.json"
                path.write_text(json.dumps(obj))
                self.assertEqual(self.validate.validate_artifact(path), ([], "content"))

    def test_unit_spec_rejections(self):
        spec = unit_spec()
        self.assertInvalid("unit-spec-v1", {k: v for k, v in spec.items() if k != "declared_paths"})
        self.assertInvalid("unit-spec-v1", self.changed(spec, risk_baseline="L9"))
        self.assertInvalid("unit-spec-v1", self.changed(spec, dependencies=["STORY-1"]))
        self.assertInvalid("unit-spec-v1", self.changed(spec, declared_path=["typo/"]))

    def test_unit_state_rejections(self):
        state = unit_state()
        self.assertInvalid("unit-state-v1", self.changed(state, state="paused"))
        self.assertInvalid("unit-state-v1", self.changed(state, state="cancelled"))
        self.assertValid("unit-state-v1", self.changed(state, state="cancelled", cancelled_by="human"))

    def test_session_rejections(self):
        self.assertInvalid("session-v1", self.changed(session(), state="running"))
        self.assertInvalid("session-v1", self.changed(session(), outcome="crashed"))
        self.assertInvalid("session-v1", self.changed(session(), unit_id="0412"))

    def test_usage_window_rejections(self):
        self.assertInvalid("usage-window-v1", self.changed(usage_window(), used_fraction=1.5))
        self.assertValid("usage-window-v1", self.changed(usage_window(), used_fraction=None))

    def test_every_daemon_event_passes_and_needs_seq(self):
        for name, fields in DAEMON_EVENTS.items():
            with self.subTest(name):
                self.assertValid("events-v1", event(name, **fields))
                line = event(name, **fields)
                del line["seq"]
                self.assertInvalid("events-v1", line)
                line = event(name, **fields)
                del line[next(iter(fields))]
                self.assertInvalid("events-v1", line)

    def test_unknown_event_is_rejected(self):
        self.assertInvalid("events-v1", event("unit_teleported"))

    def test_lines_the_real_hook_writes_validate(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RunStore(tmp)
            (Path(tmp) / ".claude" / "agents").mkdir(parents=True)
            base = {"session_id": "s", "tool_use_id": "t1", "cwd": tmp,
                    "tool_input": {"subagent_type": "spgr-agent-qa-tester", "description": "demo",
                                   "prompt": f"runs/{store.run_id}/x"}}
            for hook_event in ("PreToolUse", "PostToolUse", "SubagentStop"):
                run_hook("log-agent-events.py", {**base, "hook_event_name": hook_event}, tmp)
            lines = read_events(store.run_dir)
        self.assertEqual({line["event"] for line in lines}, {"agent_dispatched", "agent_completed", "agent_stopped"})
        for line in lines:
            with self.subTest(line["event"]):
                self.assertValid("events-v1", line)

    def test_lines_the_runtime_appends_validate(self):
        for line in ({"ts": TS, "event": "agent_joined", "tool_use_id": "t1"},
                     {"ts": TS, "event": "agent_abandoned", "tool_use_id": "t1"},
                     {"ts": TS, "event": "agent_backgrounded", "run_id": None, "tool_use_id": "t1", "agent_id": "a"},
                     {"ts": TS, "event": "product_check", "run_id": "demo", "cycle_id": "CYCLE-0001", "check_id": "c",
                      "result": "pass", "duration_s": 1.2, "results_ref": "runs/demo/r.json"}):
            with self.subTest(line["event"]):
                self.assertValid("events-v1", line)

    def test_gate_rejections(self):
        self.assertInvalid("hil-checkpoint-v2", gate(level="L7"))
        self.assertInvalid("hil-checkpoint-v2", gate(holds=["all"]))
        self.assertInvalid("hil-checkpoint-v2", gate(holds=[]))
        no_level = gate()
        del no_level["content"]["level"]
        self.assertInvalid("hil-checkpoint-v2", no_level)
        v1_header = gate()
        v1_header["schema_version"] = "v1"
        self.assertInvalid("hil-checkpoint-v2", v1_header)

    def test_a_digest_gate_holds_nothing_and_never_pauses(self):
        digest = dict(level="L1", holds=[], digest=True, pipeline_status="resumed")
        self.assertValid("hil-checkpoint-v2", gate(**digest))
        self.assertInvalid("hil-checkpoint-v2", gate(**{**digest, "holds": ["U-0412"]}))
        self.assertInvalid("hil-checkpoint-v2", gate(**{**digest, "level": "L2", "holds": ["U-0412"]}))
        self.assertInvalid("hil-checkpoint-v2", gate(**{**digest, "pipeline_status": "paused"}))

    def test_gate_response_names_who_answered(self):
        answered = {"option": "approve", "free_text": None, "rule_change": None, "by": "human", "at": TS}
        self.assertValid("hil-checkpoint-v2", gate(response=answered))
        self.assertInvalid("hil-checkpoint-v2", gate(response={"option": "approve"}))

    def test_run_state_rejections(self):
        self.assertInvalid("run-state-v2", run_state(open_gates=["G-0001"]))
        self.assertInvalid("run-state-v2", run_state(units={"paused": 1}))
        self.assertInvalid("run-state-v2", run_state(regenerable=False))
        self.assertInvalid("run-state-v2", run_state(waiting_on="lunch"))

    def test_review_may_exceed_the_wip_limit_because_a_hold_never_blocks_the_agent(self):
        board = {"backlog": [], "development": [], "review": ["U-0001", "U-0002", "U-0003"], "validation": [], "done": []}
        self.assertValid("run-state-v2", run_state(wip_board=board))

    def test_every_gate_in_the_contract_has_a_type(self):
        for kind in ("direction-review", "pr-merge", "scope-change", "discovery-go-no-go", "structure-confirmation",
                     "scope-review", "taste-review", "production-release", "provisioning-required", "routine-decision"):
            self.assertValid("hil-checkpoint-v2", gate(checkpoint_type=kind))
        self.assertInvalid("hil-checkpoint-v2", gate(checkpoint_type="brief-submit"))

    def test_v1_records_still_validate_against_v1(self):
        validate = self.validate
        for sample in (validate._sample_run_state(), validate._sample_pdca_cycle()):
            self.assertEqual(validate._validate_object(sample, self.registry), [])

    def test_a_cycle_may_already_carry_unit_id(self):
        cycle = self.validate._sample_pdca_cycle()
        cycle["content"]["plan"]["routed_batch"][0]["unit_id"] = "U-0412"
        self.assertEqual(self.validate._validate_object(cycle, self.registry), [])


class ReferenceAgreementTest(unittest.TestCase):
    def test_unit_states_match_the_lifecycle_table(self):
        self.assertEqual(table_first_column("Unit lifecycle"), schema("unit-state-v1")["properties"]["state"]["enum"])

    def test_session_states_match_the_lifecycle_table(self):
        self.assertEqual(table_first_column("Session lifecycle"), schema("session-v1")["properties"]["state"]["enum"])

    def test_daemon_events_match_the_events_table(self):
        names = {name.strip() for cell in table_first_column("Events") for name in cell.split(",")}
        defined = {name for name, d in schema("events-v1")["$defs"].items() if "seq" in d["required"]}
        self.assertEqual(names, defined)
        self.assertEqual(names, set(DAEMON_EVENTS))

    def test_legacy_events_named_in_the_reference_are_defined(self):
        named = re.search(r"existing event names \(([^)]*)\)", REFERENCE).group(1).split(", ")
        defined = {name for name, d in schema("events-v1")["$defs"].items() if "seq" not in d["required"]}
        self.assertEqual(set(named), defined)

    def test_every_schema_the_reference_names_exists(self):
        names = table_first_column("Schemas to add")
        self.assertEqual(len(names), 7)
        for name in names:
            self.assertTrue((SCHEMAS / name).exists(), name)
            self.assertEqual(schema(name.removesuffix(".json"))["$id"], f"https://springer.local/schemas/{name}")


if __name__ == "__main__":
    unittest.main()
