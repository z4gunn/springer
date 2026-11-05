"""Notifications to a person away from the TUI.

Each open gate a person must answer gets one message on the channel, which is changed
when the gate is answered or withdrawn, and gets one reminder when it waits too long.
Gate messages come from the gate records themselves and not from the event stream, so
a restart or a first setup picks up what is already open without replaying history.
Merges, merge failures, and finished runs come from the event ledger: a stall or a
finished run is sent at once, the rest is gathered into a digest that waits out quiet
hours. A channel failure is retried on the next poll, because nothing is marked sent
until the channel took it.
"""

import sys
import threading
import time
from pathlib import Path

from ..common import read_json, write_json

POLL_SECONDS = 5
SETTINGS_FILE = "notifications.json"
DEFAULTS = {"quiet_hours": [22, 7], "digest_minutes": 60, "remind_hours": 4}
DIGEST_EVENTS = ("merge", "merge_failed", "restack_failed")
FINDINGS_SHOWN = 3


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
        "level": content["level"], "type": content["checkpoint_type"], "prompt": content["decision_prompt"],
        "options": [{"option": o["option"], "consequence": o.get("consequence", "")} for o in content["options"]],
        "review": context.get("review"), "findings": summarize_findings(context.get("findings") or []),
        # A gate with decisions to fill in is answered through a form, not one tap.
        "answerable": not content.get("decisions"),
        "response": content.get("response"), "retired": bool(context.get("retired")),
    }


class Notifier:
    def __init__(self, daemon, channel_factory=None, clock=time.time):
        self.daemon = daemon
        self.root = Path(daemon.home.root)
        self.state_path = self.root / "notify-state.json"
        self.channel_factory = channel_factory
        self.channel = None
        self.clock = clock
        self.kick = threading.Event()
        self._stop = threading.Event()
        self.last_error = None

    # --- state ---

    def _state(self):
        state = read_json(self.state_path) or {}
        for key, default in (("gates", {}), ("cursors", {}), ("digest", []), ("last_digest", 0),
                             ("open_runs", []), ("done_runs", [])):
            state.setdefault(key, default)
        return state

    def _save(self, state):
        write_json(self.state_path, state)

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
        state = self._state()
        gates, events, runs = self._gather(state)
        sent = []
        try:
            sent += self._send_gates(state, gates, settings)
            sent += self._send_events(state, events, runs)
            sent += self._send_digest(state, settings)
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
        gates, events, runs = [], [], []
        with self.daemon.lock:
            for slug, record in self.daemon.home.projects().items():
                if record.get("archived"):
                    continue
                for run_id in self.daemon.run_ids(slug):
                    engine = self.daemon.engine(slug, run_id)
                    key = f"{slug}/{run_id}"
                    for gate in engine.gates.all():
                        if not gate["content"]["digest"]:
                            gates.append(gate_view(slug, run_id, gate["content"]))
                    if key not in state["cursors"]:
                        state["cursors"][key] = engine.ledger.head()
                    else:
                        for entry in engine.ledger.read(after=state["cursors"][key]):
                            state["cursors"][key] = entry.cursor
                            events.append((slug, run_id, entry.line))
                    runs.append((slug, run_id, engine.cycles.is_complete()))
        return gates, events, runs

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
                sent.append(("closed", view["gate_id"]))
            elif not closed and not record["reminded"] and \
                    now - record["posted_at"] >= settings["remind_hours"] * 3600 and \
                    not quiet(settings["quiet_hours"], now):
                self.channel.reply(record["ref"], f"Still waiting on you: {view['gate_id']} in {view['run_id']}.")
                record["reminded"] = True
                sent.append(("reminder", view["gate_id"]))
        return sent

    def _send_events(self, state, events, runs):
        sent = []
        for slug, run_id, line in events:
            name = line.get("event")
            if name == "tick_failed":
                self.channel.post(f"{run_id} is stalled. The daemon could not advance it: {line.get('detail', '')}")
                sent.append(("stalled", run_id))
            elif name in DIGEST_EVENTS:
                state["digest"].append(digest_line(run_id, line))
        for slug, run_id, complete in runs:
            key = f"{slug}/{run_id}"
            if not complete and key not in state["open_runs"]:
                state["open_runs"].append(key)
            elif complete and key in state["open_runs"] and key not in state["done_runs"]:
                self.channel.post(f"{run_id} is complete.")
                state["done_runs"].append(key)
                state["open_runs"].remove(key)
                sent.append(("complete", run_id))
        return sent

    def _send_digest(self, state, settings):
        now = self.clock()
        if not state["digest"] or quiet(settings["quiet_hours"], now) or \
                now - state["last_digest"] < settings["digest_minutes"] * 60:
            return []
        self.channel.post("Since the last digest:\n" + "\n".join(f"- {line}" for line in state["digest"]))
        count = len(state["digest"])
        state["digest"], state["last_digest"] = [], now
        return [("digest", count)]


def digest_line(run_id, line):
    name, unit, pr = line.get("event"), line.get("unit_id", ""), line.get("pr", "")
    if name == "merge":
        return f"{run_id}: {unit} merged (#{pr})"
    if name == "merge_failed":
        return f"{run_id}: {unit} could not merge (#{pr}): {line.get('detail', '')[:120]}"
    return f"{run_id}: {unit} could not be restacked (#{pr})"


def start_notifications(daemon, operations):
    """The notifier thread, with Slack built from the settings and the keychain."""
    from .slack import slack_channel_factory

    notifier = Notifier(daemon, slack_channel_factory(daemon, operations))
    daemon.notifier = notifier
    threading.Thread(target=notifier.run_forever, daemon=True, name="springer-notify").start()
    return notifier
