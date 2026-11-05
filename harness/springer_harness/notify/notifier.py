"""Notifications to a person away from the TUI, and the run feed that lets them follow
a run from a phone.

Each open gate a person must answer gets one message on the channel, which is changed
when the gate is answered or withdrawn, and gets one reminder when it waits too long.
Gate messages come from the gate records themselves and not from the event stream, so
a restart or a first setup picks up what is already open without replaying history.

Everything else comes from the event ledger into one feed thread per run: a short line
per unit started, finished, sent back, blocked, merged, and per pause, resume, and
finish. Feed lines wait out quiet hours. A gate, a block, a stall, an escalation with no
gate, and a daemon that came back from a crash go out at once. A channel failure is
retried on the next poll, because nothing is marked sent until the channel took it.
"""

import sys
import threading
import time
from pathlib import Path

from ..common import read_json, write_json

POLL_SECONDS = 5
SETTINGS_FILE = "notifications.json"
NOTES_FILE = "slack-notes.json"
DEFAULTS = {"quiet_hours": [22, 7], "remind_hours": 4}
FINDINGS_SHOWN = 3
PROMPT_CHARS = 1200
LINE_CHARS = 160


def load_settings(home_root):
    """The notification settings, or None when no channel is set up."""
    found = read_json(Path(home_root) / SETTINGS_FILE)
    if not isinstance(found, dict) or not found.get("slack"):
        return None
    return {**DEFAULTS, **found}


def save_settings(home_root, settings):
    write_json(Path(home_root) / SETTINGS_FILE, settings)


def quiet(hours, epoch):
    """True inside the quiet window, which may wrap past midnight."""
    start, end = hours
    hour = time.localtime(epoch).tm_hour
    return start <= hour < end if start < end else hour >= start or hour < end


def trim(text, limit):
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else flat[:limit - 1].rstrip() + "…"


def summarize_findings(findings):
    """Counts by severity and the first few details. No file paths, no code."""
    findings = [f for f in findings if isinstance(f, dict)]
    counts = {}
    for f in findings:
        severity = str(f.get("severity") or f.get("rule") or "note")
        counts[severity] = counts.get(severity, 0) + 1
    top = []
    for f in findings[:FINDINGS_SHOWN]:
        detail = " ".join(str(f.get("detail", "")).split())
        top.append(f"{f.get('severity', '')} {detail[:140]}".strip())
    return {"counts": counts, "top": top, "total": len(findings)}


def gate_view(project, run_id, content):
    context = content.get("context") or {}
    return {
        "key": f"{project}/{run_id}/{content['checkpoint_id']}",
        "project": project, "run_id": run_id, "gate_id": content["checkpoint_id"],
        "level": content["level"], "type": content["checkpoint_type"],
        # A blocked unit's prompt carries the whole block detail, which can be a page of
        # receipts. The message shows the head of it.
        "prompt": trim(content["decision_prompt"], PROMPT_CHARS),
        "options": [{"option": o["option"], "consequence": o.get("consequence", ""),
                     "recommended": bool(o.get("recommended_because"))} for o in content["options"]],
        "review": context.get("review"), "findings": summarize_findings(context.get("findings") or []),
        # A gate with decisions to fill in is answered through the form, not one tap.
        "answerable": not content.get("decisions"),
        "response": content.get("response"), "retired": bool(context.get("retired")),
    }


def feed_line(line):
    """The feed's line for one ledger entry, or None when the entry is not news."""
    name, unit = line.get("event"), line.get("unit_id", "")
    if name == "unit_state":
        to, reason = line.get("to"), line.get("reason", "")
        if to == "running":
            return f"{unit} started"
        if to == "done":
            # A merge has its own line.
            return None if reason.startswith("merged") else f"{unit} done: {trim(reason, LINE_CHARS)}"
        if to == "gated":
            return f"{unit} {trim(reason, LINE_CHARS)}"
        if to == "retry":
            return f"{unit} sent back: {trim(reason, LINE_CHARS)}"
        if to == "blocked":
            return f"{unit} blocked: {trim(reason, LINE_CHARS)}"
        if to == "cancelled":
            return f"{unit} cancelled"
        return None
    if name == "merge":
        return f"{unit} merged (#{line.get('pr', '')})"
    if name == "merge_failed":
        return f"{unit} could not merge (#{line.get('pr', '')}): {trim(line.get('detail'), LINE_CHARS)}"
    if name == "restack_failed":
        return f"{unit} could not be restacked (#{line.get('pr', '')})"
    if name == "tick_failed":
        return f"the daemon could not advance the run: {trim(line.get('detail'), LINE_CHARS)}"
    if name == "operation_applied" and line.get("type") == "run.pause":
        reason = (line.get("args") or {}).get("reason")
        return "paused" + (f": {trim(reason, LINE_CHARS)}" if reason else "")
    if name == "operation_applied" and line.get("type") == "run.resume":
        return "resumed"
    if name == "operation_applied" and line.get("type") == "run.note":
        return f"note from {line.get('actor')}: {trim((line.get('args') or {}).get('text'), LINE_CHARS)}"
    return None


class NoteStore:
    """Notes a person replied in a gate's thread before answering it. They ride on the
    answer as its notes. Two threads write here, the socket and the notifier, so a lock
    guards the file."""

    def __init__(self, home_root):
        self.path = Path(home_root) / NOTES_FILE
        self._lock = threading.Lock()

    def _load(self):
        found = read_json(self.path)
        return found if isinstance(found, dict) else {}

    def add(self, key, text, message_ts):
        with self._lock:
            notes = self._load()
            held = notes.setdefault(key, [])
            if any(n["ts"] == message_ts for n in held):
                return False  # Slack delivers an event again when the ack was slow
            held.append({"ts": message_ts, "text": text})
            write_json(self.path, notes)
            return True

    def take(self, key):
        """The held notes joined, and forgotten."""
        with self._lock:
            notes = self._load()
            held = notes.pop(key, [])
            if held:
                write_json(self.path, notes)
            return "\n".join(n["text"] for n in held) or None

    def drop(self, key):
        self.take(key)


def join_notes(*parts):
    found = [p.strip() for p in parts if p and p.strip()]
    return "\n".join(found) or None


class Notifier:
    def __init__(self, daemon, channel_factory=None, clock=time.time):
        self.daemon = daemon
        self.root = Path(daemon.home.root)
        self.state_path = self.root / "notify-state.json"
        self.channel_factory = channel_factory
        self.channel = None
        self.clock = clock
        self.notes = NoteStore(self.root)
        self.kick = threading.Event()
        self._stop = threading.Event()
        self._state_lock = threading.Lock()
        self.last_error = None
        self.restart_noted = False

    # --- state ---

    def _state(self):
        state = read_json(self.state_path) or {}
        for key, default in (("gates", {}), ("cursors", {}), ("feeds", {}), ("open_runs", []),
                             ("done_runs", []), ("escalations", [])):
            state.setdefault(key, default)
        return state

    def _save(self, state):
        write_json(self.state_path, state)

    def thread_for(self, ts):
        """What a Slack thread is about: ("gate", project, run_id, gate_id), ("run",
        project, run_id), or None. A reply arrives with its thread's ts and nothing else."""
        if not ts:
            return None
        with self._state_lock:
            state = self._state()
        for key, record in state["gates"].items():
            if record.get("ref", {}).get("ts") == ts:
                project, run_id, gate_id = key.split("/", 2)
                return ("gate", project, run_id, gate_id)
        for key, record in state["feeds"].items():
            if (record.get("ref") or {}).get("ts") == ts:
                project, run_id = key.split("/", 1)
                return ("run", project, run_id)
        return None

    # --- the loop ---

    def run_forever(self):
        while not self._stop.is_set():
            self.poll()
            self.kick.wait(POLL_SECONDS)
            self.kick.clear()

    def stop(self):
        self._stop.set()
        self.kick.set()

    def poll(self):
        """One pass. Returns what was sent, for the tests."""
        settings = load_settings(self.root)
        wanted = (settings or {}).get("slack", {}).get("user")
        if self.channel is not None and getattr(self.channel, "user", wanted) != wanted:
            # Turned off, or set up again for another person.
            getattr(self.channel, "close", lambda: None)()
            self.channel = None
        if settings is None:
            return []
        if self.channel is None:
            try:
                self.channel = self.channel_factory(settings) if self.channel_factory else None
            except Exception as exc:  # noqa: BLE001, a channel that cannot start is retried
                self._failed(exc)
                return []
            if self.channel is None:
                return []
        sent = []
        with self._state_lock:
            state = self._state()
            gates, events, runs, escalations = self._gather(state)
            try:
                sent += self._send_restart()
                sent += self._send_gates(state, gates, settings)
                sent += self._send_escalations(state, escalations)
                sent += self._send_events(state, events, runs, settings)
                self.last_error = None
            except Exception as exc:  # noqa: BLE001, the channel is retried on the next poll
                self._failed(exc)
            finally:
                self._save(state)
        return sent

    def _failed(self, exc):
        detail = f"{type(exc).__name__}: {exc}"[-300:]
        if detail != self.last_error:
            sys.stderr.write(f"springer notifications: {detail}\n")
        self.last_error = detail

    def _gather(self, state):
        """Read under the daemon lock, send outside it."""
        gates, events, runs, escalations = [], [], [], []
        with self.daemon.lock:
            for slug, record in self.daemon.home.projects().items():
                if record.get("archived"):
                    continue
                for run_id in self.daemon.run_ids(slug):
                    engine = self.daemon.engine(slug, run_id)
                    key = f"{slug}/{run_id}"
                    all_gates = engine.gates.all()
                    for gate in all_gates:
                        if not gate["content"]["digest"]:
                            gates.append(gate_view(slug, run_id, gate["content"]))
                    escalations += self._escalations(slug, run_id, engine, all_gates)
                    if key not in state["cursors"]:
                        state["cursors"][key] = engine.ledger.head()
                    else:
                        for entry in engine.ledger.read(after=state["cursors"][key]):
                            state["cursors"][key] = entry.cursor
                            events.append((slug, run_id, entry.line))
                    runs.append((slug, run_id, engine.cycles.is_complete()))
        return gates, events, runs, escalations

    def _escalations(self, slug, run_id, engine, gates):
        """Escalation records that no gate carries. A block opens a gate naming its
        escalation, and that gate is the message. One a session raised on its own has
        nothing else that reaches a person."""
        carried = {g["content"].get("artifact_ref") for g in gates}
        found = []
        for path in sorted((engine.run_dir / "artifacts").glob("E-*.json")):
            content = (read_json(path) or {}).get("content") or {}
            escalation_id = content.get("escalation_id") or path.stem
            if escalation_id in carried or content.get("status", "open") != "open":
                continue
            found.append({"key": f"{slug}/{run_id}/{escalation_id}", "run_id": run_id, "id": escalation_id,
                          "type": content.get("escalation_type", "escalation"),
                          "agent": str(content.get("originating_agent", "")).removeprefix("spgr-agent-"),
                          "description": trim(content.get("description"), 600)})
        return found

    def _send_restart(self):
        """Once per start, when the last daemon did not stop cleanly."""
        crash = getattr(self.daemon, "unclean_start", None)
        if not crash or self.restart_noted:
            return []
        self.channel.post(f"The daemon restarted after it stopped without a clean shutdown "
                          f"(last heartbeat {crash.get('at', 'unknown')}). Runs pick up where they were.")
        self.restart_noted = True
        return [("restarted", crash.get("at"))]

    def _send_gates(self, state, gates, settings):
        sent, now = [], self.clock()
        for view in gates:
            record = state["gates"].get(view["key"])
            closed = view["response"] is not None or view["retired"]
            if record is None:
                if closed:
                    continue
                ref = self.channel.post_gate(view)
                state["gates"][view["key"]] = {"ref": ref, "posted_at": now, "reminded": False, "closed": False}
                sent.append(("gate", view["gate_id"]))
            elif closed and not record["closed"]:
                self.channel.close_gate(record["ref"], view)
                record["closed"] = True
                # Notes held for a gate answered somewhere else must not ride on a later one.
                self.notes.drop(view["key"])
                sent.append(("closed", view["gate_id"]))
            elif not closed and not record["reminded"] and \
                    now - record["posted_at"] >= settings["remind_hours"] * 3600 and \
                    not quiet(settings["quiet_hours"], now):
                self.channel.reply(record["ref"], f"Still waiting on you: {view['gate_id']} in {view['run_id']}.")
                record["reminded"] = True
                sent.append(("reminder", view["gate_id"]))
        return sent

    def _send_escalations(self, state, escalations):
        sent = []
        for item in escalations:
            if item["key"] in state["escalations"]:
                continue
            self.channel.post(f"{item['id']} in {item['run_id']}, raised by {item['agent'] or 'a session'} "
                              f"({item['type']}): {item['description']}")
            state["escalations"].append(item["key"])
            sent.append(("escalation", item["id"]))
        return sent

    def _send_events(self, state, events, runs, settings):
        sent, now = [], self.clock()
        for slug, run_id, line in events:
            if line.get("event") == "tick_stalled":
                self.channel.post(f"{run_id} is stalled. The daemon has failed to advance it "
                                  f"{line.get('count', 3)} times in a row: {trim(line.get('detail'), 300)}")
                sent.append(("stalled", run_id))
            text = feed_line(line)
            if text:
                state["feeds"].setdefault(f"{slug}/{run_id}", {"ref": None, "pending": []})["pending"].append(text)
        for slug, run_id, complete in runs:
            key = f"{slug}/{run_id}"
            if not complete and key not in state["open_runs"]:
                state["open_runs"].append(key)
            elif complete and key in state["open_runs"] and key not in state["done_runs"]:
                self.channel.post(f"{run_id} is complete.")
                state["feeds"].setdefault(key, {"ref": None, "pending": []})["pending"].append("complete")
                state["done_runs"].append(key)
                state["open_runs"].remove(key)
                sent.append(("complete", run_id))
        if quiet(settings["quiet_hours"], now):
            return sent
        for key, feed in state["feeds"].items():
            if not feed["pending"]:
                continue
            run_id = key.split("/", 1)[1]
            feed["ref"] = self.channel.feed(feed["ref"], run_id, "\n".join(feed["pending"]))
            sent.append(("feed", run_id, len(feed["pending"])))
            feed["pending"] = []
        return sent


def start_notifications(daemon, operations):
    """The notifier thread, with Slack built from the settings and the keychain."""
    from .slack import slack_channel_factory

    notifier = Notifier(daemon, slack_channel_factory(daemon, operations))
    daemon.notifier = notifier
    threading.Thread(target=notifier.run_forever, daemon=True, name="springer-notify").start()
    return notifier

