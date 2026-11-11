"""Session records. A unit may run across several sessions, and a session may die
without returning, so each has its own directory and lifecycle."""

import json
from pathlib import Path

from ..common import iso, next_id, read_json, write_json

TERMINAL = {"handoff", "exited", "killed", "dead"}


class SessionStore:
    def __init__(self, unit_dir, now):
        self.root = Path(unit_dir) / "sessions"
        self.unit_id = Path(unit_dir).name
        self.now = now

    def ids(self):
        if not self.root.is_dir():
            return []
        return sorted(p.name for p in self.root.iterdir() if p.is_dir())

    def dir(self, session_id):
        return self.root / session_id

    def create(self, provider, model, tier, pid=None, provider_session_id=None, session_id=None):
        session_id = session_id or next_id("S", self.ids())
        record = {"artifact_type": "session", "schema_version": "v1", "session_id": session_id,
                  "unit_id": self.unit_id, "provider": provider, "provider_session_id": provider_session_id,
                  "pid": pid, "model": model, "tier": tier, "state": "spawned", "started_at": iso(self.now()),
                  "ended_at": None, "exit_code": None, "outcome": None, "input_tokens": 0, "output_tokens": 0,
                  "context_percent_at_exit": None, "cost_usd_list_price": 0}
        self.save(record)
        return record

    def get(self, session_id):
        return read_json(self.dir(session_id) / "usage.json")

    def save(self, record):
        write_json(self.dir(record["session_id"]) / "usage.json", record)

    def all(self):
        """Every session with a record. The folder exists before usage.json (the brief is
        written into it first), so a session being spawned is skipped, not None."""
        return [r for r in (self.get(s) for s in self.ids()) if r is not None]

    def finish(self, record, state, outcome, code=None):
        record.update(state=state, outcome=outcome, exit_code=code, ended_at=iso(self.now()))
        self.save(record)

    def append_stream(self, session_id, events):
        path = self.dir(session_id) / "stream.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as fh:
            for event in events:
                fh.write(json.dumps(event) + "\n")

    def last_tool_call(self, session_id):
        path = self.dir(session_id) / "stream.jsonl"
        if not path.exists():
            return None
        for raw in reversed(path.read_text().splitlines()):
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "tool_use":
                return event.get("name")
        return None
