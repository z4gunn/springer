"""Shared fixtures for the harness script tests.

The harness scripts live under .claude/skills/spgr-run-harness/scripts/ and
.claude/hooks/ with hyphenated file names, so they are loaded by path. A
RunStore builds a runs/<run-id>/ tree in a temporary directory with the exact
shapes derive-ready-queue.py and rebuild-projection.py read, one call per
fact: a cycle, a gate, an escalation, an event, a lock, a defaults ledger.
"""

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / ".claude" / "skills" / "spgr-run-harness" / "scripts"
HOOKS = REPO / ".claude" / "hooks"
SCHEMAS = REPO / "schemas"


def load_script(path):
    """Import a script file as a module, whatever its file name."""
    path = Path(path)
    name = path.stem.replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def header(artifact_id, artifact_type, section="main", producing_agent="spgr-agent-orchestrator"):
    return {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "schema_version": "v1",
        "producing_agent": producing_agent,
        "timestamp": "2026-06-02T12:00:00Z",
        "parent_artifact_ref": None,
        "version": "v0.1-draft",
        "version_type": "draft",
        "confidence_map": {section: "confirmed"},
        "decision_log": [],
    }


def utc_stamp(seconds_ago=0):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - seconds_ago))


class RunStore:
    """A runs/<run-id>/ tree under a temporary project root."""

    def __init__(self, root, run_id="demo", profile="brochure", autonomy=None, flags=None):
        self.root = Path(root)
        self.run_id = run_id
        self.run_dir = self.root / "runs" / run_id
        for sub in ("artifacts", "checkpoints", "escalations", "archive"):
            (self.run_dir / sub).mkdir(parents=True, exist_ok=True)
        self.cycle_count = 0
        if profile is not None:
            brief = header(f"run-brief-{run_id}", "run-brief", "run_brief")
            brief["content"] = {
                "run_id": run_id,
                "profile": profile,
                "phase_set": ["requirements", "design", "development"],
                "flags": dict(flags or {}),
                "caps": {"max_stories": 10, "max_artifact_tokens": 30000,
                         "max_cycle_record_tokens": 2000, "max_review_passes": 2},
                "pinned_rulings": [],
                "operative_artifacts": {},
                "pr_unit": "page",
            }
            if autonomy:
                brief["content"]["flags"]["autonomy"] = autonomy
            self.write("run-brief.json", brief)

    def write(self, rel, obj):
        path = self.run_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, indent=2))
        return path

    def write_raw(self, rel, text):
        path = self.run_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def add_cycle(self, phase="requirements", next_phase="architecture", verdict="pass",
                  transition="advance"):
        self.cycle_count += 1
        n = self.cycle_count
        obj = header(f"CYCLE-{n:04d}", "pdca-cycle", "cycle")
        obj["content"] = {
            "cycle_id": f"CYCLE-{n:04d}",
            "cycle_number": n,
            "run_id": self.run_id,
            "phase": phase,
            "plan": {"routed_batch": [], "rationale": "fixture"},
            "do": {"dispatched": []},
            "check": {"verdict": verdict, "validations": [], "audits": [],
                      "expectation_match": True},
            "act": {"transition": transition, "state_changes": [], "versioned_refs": [],
                    "escalation_ref": None, "checkpoint_ref": None, "pending_batch": None},
            "next_phase": next_phase,
        }
        return self.write(f"artifacts/CYCLE-{n:04d}.json", obj)

    def add_gate(self, checkpoint_id="HIL-0001", checkpoint_type="pr-merge", holds=None,
                 answered=False, status="paused", subdir="checkpoints"):
        obj = header(checkpoint_id, "hil-checkpoint", "checkpoint")
        obj["content"] = {
            "checkpoint_id": checkpoint_id,
            "checkpoint_type": checkpoint_type,
            "artifact_ref": "PR-0001",
            "decision_prompt": "Merge?",
            "options": [{"id": "merge", "label": "merge"}],
            "pipeline_status": status,
            "response_received": {"choice": "merge"} if answered else None,
            "decisions": [],
        }
        if holds is not None:
            obj["content"]["holds"] = holds
        return self.write(f"{subdir}/{checkpoint_id}.json", obj)

    def add_escalation(self, escalation_id="ESC-0001", status="open", subdir="escalations"):
        obj = header(escalation_id, "escalation", "escalation", "spgr-agent-architect")
        obj["content"] = {
            "escalation_id": escalation_id,
            "escalation_type": "missing-input",
            "description": "fixture",
            "artifact_ref": "prd-v1",
            "urgency": "urgent",
            "routing_target": "orchestrator",
            "originating_agent": "spgr-agent-architect",
            "status": status,
        }
        return self.write(f"{subdir}/{escalation_id}.json", obj)

    def add_artifact(self, artifact_id, artifact_type, confirmed=True):
        obj = header(artifact_id, artifact_type, "body")
        obj["confidence_map"] = {"body": "confirmed" if confirmed else "proposed"}
        obj["content"] = {}
        return self.write(f"artifacts/{artifact_id}.json", obj)

    def add_event(self, event, tool_use_id=None, agent="spgr-agent-backend-developer",
                  agent_id=None, **extra):
        ev = {"ts": utc_stamp(), "event": event, "tool_use_id": tool_use_id, "agent": agent,
              "description": extra.pop("description", "unit")}
        if agent_id:
            ev["agent_id"] = agent_id
        ev.update(extra)
        with open(self.run_dir / "events.jsonl", "a") as fh:
            fh.write(json.dumps(ev) + "\n")

    def set_lock(self, session_id, seconds_ago=0):
        self.write(".lock", {"session_id": session_id, "claimed_at": utc_stamp(seconds_ago)})

    def set_defaults(self, lines):
        self.write_raw("pending-defaults.md", "\n".join(lines) + "\n")

    def set_state(self, wip_board=None, learnings=None, profile=None):
        obj = header(f"run-state-{self.run_id}", "run-state", "run_state")
        obj["content"] = {
            "run_id": self.run_id,
            "regenerable": True,
            "generated_from_cycle": self.cycle_count,
            "active_phase": "requirements",
            "workstreams": [],
            "wip_board": wip_board or {"backlog": [], "development": [], "review": [],
                                       "validation": [], "done": []},
            "ready_queue": [],
            "open_gates": [],
            "open_escalations": [],
            "cycle_counter": self.cycle_count,
            "learnings_pinned": learnings or [],
        }
        if profile:
            obj["content"]["profile"] = profile
        return self.write("run-state.json", obj)


def run_hook(hook_name, payload, project_dir, env=None):
    """Run a hook script the way Claude Code does: JSON on stdin, project dir
    in the environment. Returns (exit_code, stdout, stderr)."""
    full_env = dict(os.environ)
    full_env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    full_env.update(env or {})
    proc = subprocess.run(
        [sys.executable, str(HOOKS / hook_name)],
        input=json.dumps(payload), capture_output=True, text=True, env=full_env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def read_events(run_dir):
    path = Path(run_dir) / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
