"""Slack, over Socket Mode: the daemon opens an outbound websocket, so nothing listens
on a public port. Slack is the whole control plane for a person away from the TUI.

Gate messages go to a direct message with the one person allowed to answer. Every gate
has one-tap option buttons where it can take one, and an Answer with notes button that
opens a form with the option, any decisions, and notes. A reply in a gate's thread is a
note held for the answer, or the answer itself when it starts with an option number or
name. A reply in a run's feed thread is a note for the next session of each open unit.
/springer reads status and drives runs and units. A change that needs confirming comes
back with a Confirm button. Every change is an operation from the channel actor,
refused for anyone but the set-up person.

The block builders and the handlers are plain functions over dicts, so they are tested
without Slack. Only SlackService touches slack_sdk.
"""

import json
import re
import shlex
import threading
import time
import uuid
from pathlib import Path

from .. import reconcile
from ..errors import HarnessError
from .notifier import finished_at, join_notes, run_summary, trim

BOT_TOKEN = "slack-bot-token"
APP_TOKEN = "slack-app-token"
SECRET_SCOPE = "_harness"
ACTOR = "channel:slack"
DANGER = ("cancel", "discard", "send_back")
FORM_ACTION = "gate_form"
FORM_CALLBACK = "gate_answer"
CONFIRM_ACTION = "op_confirm"
CANCEL_ACTION = "op_cancel"
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
UNIT_ID = re.compile(r"^(?:([A-Za-z0-9][A-Za-z0-9._-]*):)?(U-\d{4})$")
TIERS = ("haiku", "sonnet", "opus")
LOG_CHARS = 1800
ONLY_YOU = "Only the person this app was set up for can do that."
USAGE = ("status | gates | units [project] | polish <project> <issue> | build <project> | release <project> | "
         "release-command <project> <command> [word] | checks <project> [command...] | pause <project> | "
         "resume <project> | reconcile <project> <change> <option> [text] | "
         "redispatch <unit> [tier] | cancel <unit> | log <unit> | ruling [project] <text> | "
         "unlock [project] <path> <reason> | restart")

MANIFEST = {
    "display_information": {"name": "Springer", "description": "Gates, run progress, and run control for Springer"},
    "features": {
        # The messages tab is writable, because a reply in a thread is how a person adds notes.
        "app_home": {"home_tab_enabled": False, "messages_tab_enabled": True, "messages_tab_read_only_enabled": False},
        "bot_user": {"display_name": "springer", "always_online": True},
        "slash_commands": [{"command": "/springer", "description": "Run status, gates, and run and unit control",
                            "usage_hint": USAGE[:100], "should_escape": False}],
    },
    "oauth_config": {"scopes": {"bot": ["chat:write", "im:write", "im:history", "commands"]}},
    "settings": {"event_subscriptions": {"bot_events": ["message.im"]},
                 "interactivity": {"is_enabled": True}, "org_deploy_enabled": False, "socket_mode_enabled": True,
                 "token_rotation_enabled": False},
}


# --- messages ---

def gate_text(view):
    return f"{view['project']} · {view['run_id']} · {view['gate_id']} ({view['level']}): {trim(view['prompt'], 300)}"


def option_label(number, option):
    name = option["option"].replace("_", " ")
    return f"{number}. {name}" + (" (recommended)" if option.get("recommended") else "")


def _review_lines(view):
    lines = []
    if view.get("review"):
        lines.append(f"Code review: {view['review'].replace('_', ' ')}")
    findings = view["findings"]
    if findings["total"]:
        counts = ", ".join(f"{n} {severity}" for severity, n in findings["counts"].items())
        lines.append(f"Findings: {counts}")
        lines += [f"• {line}" for line in findings["top"]]
    return lines


def gate_blocks(view):
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": f"*{view['gate_id']}* ({view['level']}) "
                                                                      f"in {view['run_id']}\n{view['prompt']}"}}]
    review = _review_lines(view)
    if review:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(review)}})
    listing = [option_label(n, o) + (f": {o['consequence']}" if o["consequence"] else "")
               for n, o in enumerate(view["options"], 1)]
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "\n".join(listing)[:2900]}]})
    target = {"p": view["project"], "r": view["run_id"], "g": view["gate_id"]}
    elements = []
    if view["answerable"]:
        for number, option in enumerate(view["options"][:5], 1):
            button = {"type": "button", "action_id": f"gate:{option['option']}",
                      "text": {"type": "plain_text", "text": option_label(number, option)[:75]},
                      "value": json.dumps({**target, "o": option["option"]})}
            # Only the recommended option is styled to draw the eye. A styled first
            # button drew a tap the person did not mean.
            if option.get("recommended"):
                button["style"] = "primary"
            elif option["option"] in DANGER:
                button["style"] = "danger"
            elements.append(button)
    form = {"type": "button", "action_id": FORM_ACTION, "value": json.dumps(target),
            "text": {"type": "plain_text", "text": "Answer with notes" if view["answerable"] else "Answer"}}
    if not view["answerable"]:
        form["style"] = "primary"
    elements.append(form)
    blocks.append({"type": "actions", "block_id": f"gate-{view['gate_id']}", "elements": elements})
    hint = ("Reply in this thread to add a note to your answer, or reply with an option number or name and "
            "a colon to answer with notes, for example `1: looks good`.")
    if not view["answerable"]:
        hint = "This one has decisions to fill in. Tap Answer. A reply in this thread is added as a note."
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": hint}]})
    return blocks


def closed_blocks(view):
    if view["response"]:
        response = view["response"]
        by = {"channel:slack": "from Slack", "tui": "in the TUI"}.get(response.get("by"), f"by {response.get('by')}")
        outcome = f"Answered {response['option'].replace('_', ' ')} {by}."
        if response.get("free_text"):
            outcome += f" Notes: {trim(response['free_text'], 300)}"
    else:
        outcome = "Withdrawn: the work went back to its builder."
    return [{"type": "section", "text": {"type": "mrkdwn", "text": f"~{view['gate_id']}~ ({view['level']}) in "
                                                                  f"{view['run_id']}\n{view['prompt']}"}},
            {"type": "context", "elements": [{"type": "mrkdwn", "text": outcome}]}]


# --- the answer form ---

def form_view(target, content):
    """A modal: the option as a dropdown, one text box per decision, and optional notes."""
    options = content["options"]
    listing = "\n".join(f"*{n}.* {o['option']}" + (" (recommended)" if o.get("recommended_because") else "")
                        + (f"\n{o['consequence']}" if o.get("consequence") else "")
                        for n, o in enumerate(options, 1))
    choices = [{"text": {"type": "plain_text", "text": f"{n}. {o['option']}"[:75]}, "value": str(n - 1)}
               for n, o in enumerate(options, 1)]
    pick = {"type": "static_select", "action_id": "pick", "options": choices[:100],
            "placeholder": {"type": "plain_text", "text": "Pick an option"}}
    recommended = next((c for c, o in zip(choices, options) if o.get("recommended_because")), None)
    if recommended:
        pick["initial_option"] = recommended
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": trim(content["decision_prompt"], 2900)}},
              {"type": "section", "text": {"type": "mrkdwn", "text": listing[:3000]}},
              {"type": "input", "block_id": "option", "label": {"type": "plain_text", "text": "Option"},
               "element": pick}]
    for decision in content.get("decisions") or []:
        blocks.append({"type": "input", "block_id": f"d:{decision['decision_id']}",
                       "label": {"type": "plain_text", "text": decision["prompt"][:2000]},
                       "hint": {"type": "plain_text", "text": decision["decision_id"]},
                       "element": {"type": "plain_text_input", "action_id": "answer", "multiline": True}})
    blocks.append({"type": "input", "block_id": "notes", "optional": True,
                   "label": {"type": "plain_text", "text": "Notes"},
                   "hint": {"type": "plain_text", "text": "Notes you replied in the gate's thread are added too."},
                   "element": {"type": "plain_text_input", "action_id": "answer", "multiline": True}})
    return {"type": "modal", "callback_id": FORM_CALLBACK, "private_metadata": json.dumps(target),
            "title": {"type": "plain_text", "text": f"Answer {target['g']}"[:24]},
            "submit": {"type": "plain_text", "text": "Answer"},
            "close": {"type": "plain_text", "text": "Cancel"}, "blocks": blocks}


def _gate_content(daemon, target):
    """The gate record, read without the daemon lock: a modal must open within 3 seconds
    of the tap and a tick can hold the lock longer. Records are written atomically."""
    names = (target.get("p"), target.get("r"), target.get("g"))
    if not all(isinstance(n, str) and SAFE_NAME.match(n) for n in names):
        raise HarnessError("That button carried no gate.")
    path = Path(daemon.project_path(target["p"])) / "runs" / target["r"] / "artifacts" / f"{target['g']}.json"
    try:
        return json.loads(path.read_text())["content"]
    except (OSError, ValueError, KeyError):
        raise HarnessError(f"{target['g']} is not a gate of {target['r']}.") from None


def _key(target):
    return f"{target['p']}/{target['r']}/{target['g']}"


def _answer(operations, op_id, target, option, notes=None, decisions=(), extra=None):
    """One gate.answer from the channel, with any notes held from the thread on it."""
    held = notes.take(_key(target)) if notes is not None else None
    args = {"gate_id": target["g"], "option": option, "decisions": list(decisions)}
    free_text = join_notes(held, extra)
    if free_text:
        args["free_text"] = free_text
    try:
        outcome = operations.apply(op_id, "gate.answer", target["p"], target["r"], args, None, ACTOR)
    except HarnessError as exc:
        if held and notes is not None:
            notes.add(_key(target), held, f"returned-{op_id}")
        return f"{target['g']} not answered: {exc}"
    if outcome.get("status") == "needs_confirmation":
        return f"{target['g']} needs a confirmation. Answer it in the TUI."
    return None


def open_form(payload, daemon, allowed_user):
    """The Answer tap. Returns (view, None) to open, or (None, note) to post instead."""
    if payload.get("user", {}).get("id") != allowed_user:
        return None, "Only the person this app was set up for can answer gates."
    try:
        target = json.loads((payload.get("actions") or [{}])[0].get("value", ""))
        content = _gate_content(daemon, target)
    except (ValueError, AttributeError):
        return None, "That button carried no gate."
    except HarnessError as exc:
        return None, str(exc)
    if content.get("response"):
        return None, f"{target['g']} is already answered."
    return form_view(target, content), None


def handle_submission(payload, daemon, operations, allowed_user, notes=None):
    """The form's Answer. Returns a note to post when it did not answer the gate."""
    if payload.get("user", {}).get("id") != allowed_user:
        return "Only the person this app was set up for can answer gates."
    view = payload.get("view") or {}
    values = (view.get("state") or {}).get("values") or {}
    try:
        target = json.loads(view.get("private_metadata") or "")
        content = _gate_content(daemon, target)
        index = int(values["option"]["pick"]["selected_option"]["value"])
        option = content["options"][index]["option"]
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        return "That form carried no gate or no option."
    except HarnessError as exc:
        return str(exc)
    decisions = [{"decision_id": block[2:], "response": (field.get("answer", {}).get("value") or "").strip()}
                 for block, field in values.items() if block.startswith("d:")]
    typed = (values.get("notes", {}).get("answer", {}).get("value") or "").strip()
    return _answer(operations, f"slack-{view.get('id') or uuid.uuid4().hex}", target, option, notes, decisions, typed)


def handle_action(payload, operations, allowed_user, notes=None):
    """A button press. Returns the line to post back in the gate's thread."""
    if payload.get("user", {}).get("id") != allowed_user:
        return "Only the person this app was set up for can answer gates."
    action = (payload.get("actions") or [{}])[0]
    try:
        target = json.loads(action.get("value", ""))
        target["o"]
    except (ValueError, KeyError, TypeError):
        return "That button carried no gate."
    return _answer(operations, f"slack-{action.get('action_ts') or uuid.uuid4().hex}", target, target["o"], notes)


# --- thread replies ---

def _match_option(head, options):
    """An option by its number or its name, spaces and underscores alike."""
    head = head.strip().lower().replace("_", " ")
    if head.isdigit() and 1 <= int(head) <= len(options):
        return options[int(head) - 1]["option"]
    for option in options:
        if option["option"].lower().replace("_", " ") == head:
            return option["option"]
    return None


def handle_message(event, daemon, operations, allowed_user, notifier):
    """A message in the direct message. Returns (reply, thread_ts) or None to stay quiet."""
    if event.get("bot_id") or event.get("subtype") or not event.get("text"):
        return None
    thread = event.get("thread_ts")
    if event.get("user") != allowed_user:
        return ONLY_YOU, thread or event.get("ts")
    text = event["text"].strip()
    about = notifier.thread_for(thread) if notifier is not None and thread else None
    if about is None:
        return ("Reply in a gate's thread to add a note or answer it, reply in a run's progress thread to leave "
                f"a note for its next sessions, or use /springer: {USAGE}"), thread or event.get("ts")
    if about[0] == "gate":
        _, project, run_id, gate_id = about
        target = {"p": project, "r": run_id, "g": gate_id}
        try:
            content = _gate_content(daemon, target)
        except HarnessError as exc:
            return str(exc), thread
        if content.get("response"):
            return f"{gate_id} is already answered. The note was not kept.", thread
        head, colon, rest = text.partition(":")
        option = _match_option(head if colon else text, content["options"])
        if option and not content.get("decisions"):
            note = _answer(operations, f"slack-msg-{event.get('ts')}", target, option, notifier.notes,
                           extra=rest if colon else None)
            return note or f"Answered {option.replace('_', ' ')}.", thread
        notifier.notes.add(_key(target), text, event.get("ts"))
        return f"Noted. It goes with your answer to {gate_id}.", thread
    _, project, run_id = about
    try:
        outcome = operations.apply(f"slack-msg-{event.get('ts')}", "run.note", project, run_id, {"text": text},
                                   None, ACTOR)
    except HarnessError as exc:
        return f"Not noted: {exc}", thread
    units = outcome.get("result", {}).get("units") or []
    return (f"Noted for {', '.join(units)}." if units else "Noted. No unit is open, so the next one planned reads it "
                                                            "in the run feed only."), thread


# --- commands ---

PENDING = {}
_PENDING_LOCK = threading.Lock()


def _pending_add(entry):
    key = uuid.uuid4().hex[:16]
    with _PENDING_LOCK:
        PENDING[key] = entry
    return key


def _pending_take(key):
    with _PENDING_LOCK:
        return PENDING.pop(key, None)


def _apply(operations, kind, project, run_id, args, done):
    """Apply an operation from a command. One that needs confirming comes back as a
    message with Confirm and Cancel buttons, and the token stays here."""
    op_id = f"slack-{uuid.uuid4().hex}"
    try:
        outcome = operations.apply(op_id, kind, project, run_id, args, None, ACTOR)
    except HarnessError as exc:
        return _refusal(exc)
    if outcome.get("status") != "needs_confirmation":
        return done(outcome)
    key = _pending_add({"op_id": op_id, "kind": kind, "project": project, "run_id": run_id, "args": args,
                        "token": outcome["confirm_token"], "done": done})
    summary = outcome.get("preview", {}).get("summary", kind)
    return {"text": f"Confirm {kind}: {summary}",
            "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": f"*Confirm {kind}*\n{summary}"}},
                       {"type": "actions", "elements": [
                           {"type": "button", "action_id": CONFIRM_ACTION, "style": "primary", "value": key,
                            "text": {"type": "plain_text", "text": "Confirm"}},
                           {"type": "button", "action_id": CANCEL_ACTION, "value": key,
                            "text": {"type": "plain_text", "text": "Cancel"}}]}]}


def _refusal(exc):
    """A refused operation, with the brief's blocking errors listed when a start is refused."""
    errors = (getattr(exc, "details", None) or {}).get("critique", {}).get("errors") or []
    lines = [f"Not done: {exc}"] + [f"- {e.get('section') or 'brief'}: {e.get('message')}" for e in errors[:10]]
    return "\n".join(lines)


def handle_confirm(payload, operations, allowed_user):
    """The Confirm or Cancel tap on a command's confirmation. Returns the reply."""
    if payload.get("user", {}).get("id") != allowed_user:
        return ONLY_YOU
    action = (payload.get("actions") or [{}])[0]
    entry = _pending_take(action.get("value", ""))
    if entry is None:
        return "That confirmation has expired or was already used. Run the command again."
    if action.get("action_id") == CANCEL_ACTION:
        return f"Cancelled {entry['kind']}."
    try:
        outcome = operations.apply(entry["op_id"], entry["kind"], entry["project"], entry["run_id"], entry["args"],
                                   entry["token"], ACTOR)
    except HarnessError as exc:
        return _refusal(exc)
    return entry["done"](outcome)


def _active(daemon):
    """(project, run_id, engine) for each run in progress."""
    found = []
    with daemon.lock:
        for slug, record in daemon.home.projects().items():
            if record.get("archived"):
                continue
            run_id = daemon.active_run(slug)
            if run_id:
                found.append((slug, run_id, daemon.engine(slug, run_id)))
    return found


def _find_unit(daemon, ref):
    """The run a unit belongs to, from `U-0001` or `project:U-0001`."""
    match = UNIT_ID.match(ref or "")
    if not match:
        raise HarnessError(f"{ref or 'nothing'} is not a unit. Name one like U-0004 or project:U-0004.")
    project, unit_id = match.groups()
    found = [(slug, run_id) for slug, run_id, engine in _active(daemon)
             if (project in (None, slug)) and unit_id in engine.units.ids()]
    if not found:
        raise HarnessError(f"No run in progress has {unit_id}.")
    if len(found) > 1:
        raise HarnessError(f"{unit_id} is in more than one run. Name it as project:{unit_id}.")
    return found[0][0], found[0][1], unit_id


def _one_project(daemon, words):
    """The project a command names first, or the only one with a run in progress, and the
    words after it."""
    projects = daemon.home.projects()
    if words and words[0] in projects:
        return words[0], words[1:]
    active = [slug for slug, _, _ in _active(daemon)]
    if len(active) == 1:
        return active[0], words
    raise HarnessError("Which project? Name it first.")


def _clean_log(text, project_path, home):
    text = text.replace(str(project_path).rstrip("/") + "/", "").replace(str(home), "~")
    return re.sub(r"/(?:Users|home|private|var|tmp|opt)/\S+", "<path>", text)


def _log(daemon, ref):
    slug, run_id, unit_id = _find_unit(daemon, ref)
    with daemon.lock:
        engine = daemon.engine(slug, run_id)
        state = engine.units.state(unit_id)
        if not state["sessions"]:
            return f"{unit_id} has not run a session yet. It is {state['state']}."
        session_dir = engine.sessions(unit_id).dir(state["sessions"][-1])
    path = session_dir / "result.md"
    if not path.exists():
        return f"{unit_id} {state['sessions'][-1]} left no result.md. It is {state['state']}."
    body = _clean_log(path.read_text(), daemon.project_path(slug), Path.home())
    if len(body) > LOG_CHARS:
        body = body[:LOG_CHARS].rstrip() + "\n…"
    return f"{unit_id} {state['sessions'][-1]} ({state['state']}):\n```{body}```"


def _units(daemon, words):
    runs = [(s, r, e) for s, r, e in _active(daemon) if not words or s == words[0]]
    lines = []
    with daemon.lock:
        for slug, run_id, engine in runs:
            lines.append(f"{run_id}:")
            for unit_id in engine.units.ids():
                state = engine.units.state(unit_id)
                agent = str(engine._spec(unit_id).get("agent", "")).removeprefix("spgr-agent-")
                lines.append(f"  {unit_id} {state['state']} · {agent}")
    return "\n".join(lines[:60]) or "No run in progress."


def handle_command(text, daemon, operations, user, allowed_user):
    """/springer. Returns the reply, shown only to the person who typed it: text, or a
    dict with text and blocks when it asks for a confirmation."""
    try:
        words = shlex.split(text or "")
    except ValueError:
        words = (text or "").split()
    verb = words[0].lower() if words else "status"
    rest = words[1:]
    if verb in ("status", "gates"):
        return _status(daemon) if verb == "status" else _gates(daemon)
    if verb == "units":
        return _units(daemon, rest)
    if verb == "help":
        return f"/springer {USAGE}"
    if verb not in ("polish", "build", "release", "release-command", "checks", "pause", "resume", "redispatch", "cancel",
                    "log", "ruling", "unlock", "reconcile", "restart"):
        return f"Try /springer {USAGE}"
    if user != allowed_user:
        return ONLY_YOU
    try:
        if verb in ("polish", "build"):
            return _start(daemon, operations, verb, rest)
        if verb in ("release", "release-command"):
            return _release(daemon, operations, verb, rest)
        if verb == "checks":
            return _checks(daemon, operations, rest)
        if verb in ("pause", "resume"):
            return _pause(daemon, operations, verb, rest)
        if verb == "log":
            return _log(daemon, rest[0] if rest else "")
        if verb in ("redispatch", "cancel"):
            slug, run_id, unit_id = _find_unit(daemon, rest[0] if rest else "")
            if verb == "cancel":
                return _apply(operations, "unit.cancel", slug, run_id, {"unit_id": unit_id},
                              lambda _: f"{unit_id} cancelled.")
            args = {"unit_id": unit_id}
            if len(rest) > 1:
                if rest[1] not in TIERS:
                    return f"The tier is one of {', '.join(TIERS)}."
                args["model_tier"] = rest[1]
            return _apply(operations, "unit.redispatch", slug, run_id, args,
                          lambda _: f"{unit_id} goes out again with a fresh session.")
        if verb == "ruling":
            slug, rest = _one_project(daemon, rest)
            ruling = " ".join(rest).strip()
            if not ruling:
                return 'What is the ruling? /springer ruling "R-1107: the hero keeps its 2:1 ratio"'
            front, _ = daemon.brief(slug).load()
            pinned = list(front.get("pinned_rulings") or []) + [ruling]
            return _apply(operations, "brief.update_facts", slug, None,
                          {"facts": {"pinned_rulings": pinned}, "base_version": front["brief_version"]},
                          lambda outcome: "Pinned." + (f" {outcome['result']['gate_id']} asks you to apply it."
                                                       if outcome.get("result", {}).get("gate_id") else ""))
        if verb == "reconcile":
            return _reconcile(daemon, operations, rest)
        if verb == "unlock":
            slug, rest = _one_project(daemon, rest)
            if len(rest) < 2:
                return "Name the path and the reason: /springer unlock eslint.config.js \"the scaffold needs import order\""
            path, reason = rest[0], " ".join(rest[1:])
            return _apply(operations, "project.unlock_config", slug, None, {"path": path, "reason": reason},
                          lambda _: f"{path} is unlocked for the next session that needs it.")
        return _apply(operations, "daemon.restart", None, None, {},
                      lambda _: "Draining: every run is paused, and the daemon restarts once no session is "
                                "running. The runs resume after it.")
    except HarnessError as exc:
        return str(exc)


def _start(daemon, operations, lane, rest):
    """polish <project> <issue> or build <project>: start a run, after a Confirm tap."""
    if not rest:
        return (f'Which project? /springer polish <project> "the issue in your words"' if lane == "polish"
                else "Which project? /springer build <project>")
    slug = rest[0]
    with daemon.lock:
        try:
            record = daemon.home.project(slug)
        except HarnessError:
            return f"No project named {slug}."
        if record.get("archived"):
            return f"{slug} is archived."
        running = daemon.active_run(slug)
        front, _ = daemon.brief(slug).load()
    if running:
        return f"{slug} already has {running} in progress. Wait for it to finish or cancel it first."
    args = {"base_version": front["brief_version"], "lane": lane}
    if lane == "polish":
        issue = " ".join(rest[1:]).strip()
        if not issue:
            return (f'What is the issue? /springer polish {slug} "the footer link is the wrong color". '
                    f'To build an open backlog item, start with its id: "DEFERRED-2: the issue"')
        args["issue"] = issue
    elif record.get("adopted") and front.get("brief_version") == record.get("adopted_brief_version"):
        return (f"{slug}'s brief has not changed since it was adopted, so a build has nothing to add. Describe the "
                f"change in the brief first, or use /springer polish {slug} \"the issue\" for one fix.")
    return _apply(operations, "run.start", slug, None, args,
                  lambda outcome: f"Started {outcome['result']['run_id']}. Its progress thread opens in this DM.")


def _reconcile(daemon, operations, rest):
    """reconcile <project> <change> <option> [text]: answer reconcile's question on an
    external change in a gate-list area."""
    slug, rest = _one_project(daemon, rest)
    if len(rest) < 2 or rest[1] not in reconcile.OPTIONS:
        return (f'How? /springer reconcile {slug} R-1 decision "ADR-002: the session cookie is SameSite strict", '
                f"/springer reconcile {slug} R-1 not-architecture, or /springer reconcile {slug} R-1 review")
    args = {"change_id": rest[0], "option": rest[1], "text": " ".join(rest[2:]) or None}
    replies = {"decision": "Recorded.", "not-architecture": "Noted, not an architecture change.",
               "review": "Started {run} to review it."}
    return _apply(operations, "project.reconcile_answer", slug, None, args,
                  lambda outcome: replies[rest[1]].format(run=(outcome.get("result") or {}).get("answer", {}).get("run_id")))


def _release(daemon, operations, verb, rest):
    """release <project>: deploy the default branch head now, after a Confirm tap.
    release-command <project> <command> [word]: set what release runs."""
    if not rest:
        return (f"Which project? /springer {verb} <project>" if verb == "release" else
                'Which project? /springer release-command <project> "npm run deploy" go')
    slug = rest[0]
    with daemon.lock:
        try:
            daemon.home.project(slug)
        except HarnessError:
            return f"No project named {slug}."
        command = daemon.settings(slug).get("release_command")
    if verb == "release-command":
        if len(rest) < 2:
            return f'Name the command: /springer release-command {slug} "npm run deploy" go'
        args = {"command": rest[1], "confirm": rest[2] if len(rest) > 2 else None}
        return _apply(operations, "project.set_release", slug, None, args,
                      lambda _: f"{slug} releases with: {rest[1]}"
                                + (f", typing {rest[2]} at its prompt." if len(rest) > 2 else "."))
    if not command:
        return f'{slug} has no release command. Set one: /springer release-command {slug} "npm run deploy" go'
    return _apply(operations, "project.release", slug, None, {},
                  lambda _: f"Deploying {slug} with {command}. The result posts in its run thread.")


def _checks(daemon, operations, rest):
    """checks <project>: show them. checks <project> <command>...: set them. checks <project> none: clear."""
    if not rest:
        return 'Which project? /springer checks <project> "npm run check"'
    slug = rest[0]
    with daemon.lock:
        try:
            daemon.home.project(slug)
        except HarnessError:
            return f"No project named {slug}."
        current = daemon.settings(slug).get("project_checks") or []
    if len(rest) == 1:
        return (f"{slug} runs on every code change: " + "; ".join(current)) if current else \
            f'{slug} has no project checks. Set one: /springer checks {slug} "npm run check"'
    commands = [] if rest[1:] == ["none"] else rest[1:]
    return _apply(operations, "project.set_checks", slug, None, {"commands": commands},
                  lambda _: (f"{slug} runs on every code change: " + "; ".join(commands)) if commands
                  else f"{slug} has no project checks now.")


def _pause(daemon, operations, verb, rest):
    if not rest:
        return f"Which project? /springer {verb} <project>"
    slug = rest[0]
    with daemon.lock:
        try:
            daemon.home.project(slug)
        except HarnessError:
            return f"No project named {slug}."
        run_id = daemon.active_run(slug)
    if not run_id:
        return f"{slug} has no run in progress."
    args = {"reason": "paused from Slack"} if verb == "pause" else {}
    return _apply(operations, f"run.{verb}", slug, run_id, args,
                  lambda _: f"{run_id} {'paused' if verb == 'pause' else 'resumed'}.")


def _runs(daemon):
    for slug, run_id, engine in _active(daemon):
        with daemon.lock:
            yield slug, run_id, engine.project()["content"]


FINISHED_SHOWN = 5


def _finished(daemon):
    """The most recently finished runs, newest first, as (epoch, run_id, summary)."""
    found = []
    with daemon.lock:
        for slug, record in daemon.home.projects().items():
            if record.get("archived"):
                continue
            for run_id in daemon.run_ids(slug):
                engine = daemon.engine(slug, run_id)
                if engine.cycles.is_complete():
                    found.append((finished_at(engine) or 0, run_id, engine))
        found.sort(key=lambda item: item[0], reverse=True)
        return [(at, run_id, run_summary(engine)) for at, run_id, engine in found[:FINISHED_SHOWN]]


def _status(daemon):
    lines = []
    for slug, run_id, run in _runs(daemon):
        units = ", ".join(f"{n} {state}" for state, n in sorted(run["units"].items()) if n)
        flags = " · paused" if run["paused"] else ""
        lines.append(f"{run_id}: {run['active_phase']}{flags} · {len(run['open_gates'])} waiting on you · "
                     f"{len(run['in_flight'])} running · {units}")
    if not lines:
        lines.append("No run in progress.")
    finished = _finished(daemon)
    if finished:
        lines.append("Finished:")
        lines += [f"{run_id}: {time.strftime('%b %d %H:%M', time.localtime(at)) if at else 'unknown'} · {summary}"
                  for at, run_id, summary in finished]
    return "\n".join(lines)


def _gates(daemon):
    lines = []
    with daemon.lock:
        for slug, record in daemon.home.projects().items():
            if record.get("archived"):
                continue
            for run_id in daemon.run_ids(slug):
                for gate in daemon.engine(slug, run_id).gates.open_gates():
                    content = gate["content"]
                    if not content["digest"]:
                        lines.append(f"{content['checkpoint_id']} ({content['level']}) {run_id}: "
                                     f"{content['decision_prompt'][:120]}")
    return "\n".join(lines) or "Nothing is waiting on you."


# --- the channel and the socket ---

class SlackChannel:
    """Posts to the direct message with the person."""

    def __init__(self, web, user):
        self.web, self.user = web, user
        self._dm = None

    def dm(self):
        if self._dm is None:
            self._dm = self.web.conversations_open(users=self.user)["channel"]["id"]
        return self._dm

    def post_gate(self, view):
        sent = self.web.chat_postMessage(channel=self.dm(), text=gate_text(view), blocks=gate_blocks(view))
        return {"channel": sent["channel"], "ts": sent["ts"]}

    def close_gate(self, ref, view):
        self.web.chat_update(channel=ref["channel"], ts=ref["ts"], text=gate_text(view), blocks=closed_blocks(view))

    def reply(self, ref, text):
        self.web.chat_postMessage(channel=ref["channel"], thread_ts=ref["ts"], text=text)

    def post(self, text):
        self.web.chat_postMessage(channel=self.dm(), text=text)

    def feed(self, ref, run_id, text):
        """Lines in the run's progress thread, which the first lines open."""
        if ref is None:
            sent = self.web.chat_postMessage(channel=self.dm(), text=f"{run_id} progress. Reply in this thread to "
                                                                       "leave a note for its next sessions.")
            ref = {"channel": sent["channel"], "ts": sent["ts"]}
        self.reply(ref, text)
        return ref


class SlackService(SlackChannel):
    """The channel plus the Socket Mode listener for buttons, forms, replies, and /springer."""

    def __init__(self, bot_token, app_token, user, daemon, operations, base_url=None):
        from slack_sdk import WebClient
        from slack_sdk.socket_mode import SocketModeClient

        super().__init__(WebClient(token=bot_token, base_url=base_url or WebClient.BASE_URL), user)
        self.daemon, self.operations = daemon, operations
        self.socket = SocketModeClient(app_token=app_token, web_client=self.web)
        self.socket.socket_mode_request_listeners.append(self._on_request)
        self.socket.connect()

    def close(self):
        self.socket.close()

    def _on_request(self, client, request):
        from slack_sdk.socket_mode.response import SocketModeResponse
        from slack_sdk.webhook import WebhookClient

        def ack():
            client.send_socket_mode_response(SocketModeResponse(envelope_id=request.envelope_id))

        def respond(url, reply):
            reply = reply if isinstance(reply, dict) else {"text": reply}
            WebhookClient(url).send(text=reply["text"], blocks=reply.get("blocks"), response_type="ephemeral",
                                    replace_original=bool(reply.get("replace")))

        def open_view(trigger_id, view):
            self.web.views_open(trigger_id=trigger_id, view=view)

        route(request.type, request.payload or {}, ack, respond, self.web.chat_postMessage, self.daemon,
              self.operations, self.user, open_view=open_view, dm=self.dm)


def route(kind, payload, ack, respond, post, daemon, operations, allowed_user, open_view=None, dm=None):
    """One Socket Mode request. Slack wants the ack within 3 seconds and a tick holds the
    daemon lock through git and merge work, so the ack goes first and the answer after:
    a command's reply through its response_url, a button's note in the gate's thread, a
    form's note in the direct message, a thread reply's answer in its thread. The Answer
    tap opens its form without the lock, because its trigger expires 3 seconds after the tap."""
    ack()
    notifier = getattr(daemon, "notifier", None)
    notes = getattr(notifier, "notes", None)

    def kick():
        if notifier is not None:
            notifier.kick.set()

    if kind == "slash_commands":
        reply = handle_command(payload.get("text", ""), daemon, operations, payload.get("user_id"), allowed_user)
        if payload.get("response_url"):
            respond(payload["response_url"], reply)
        kick()
        return
    if kind == "events_api":
        event = payload.get("event") or {}
        if event.get("type") != "message" or event.get("channel_type", "im") != "im":
            return
        answer = handle_message(event, daemon, operations, allowed_user, notifier)
        if answer:
            text, thread = answer
            post(channel=event.get("channel") or (dm() if dm else None), thread_ts=thread, text=text)
        kick()
        return
    if kind != "interactive":
        return
    if payload.get("type") == "view_submission":
        if (payload.get("view") or {}).get("callback_id") != FORM_CALLBACK:
            return
        note = handle_submission(payload, daemon, operations, allowed_user, notes)
        if note and dm is not None:
            post(channel=dm(), text=note)
        kick()
        return
    if payload.get("type") != "block_actions":
        return
    message = payload.get("container", {})
    action_id = (payload.get("actions") or [{}])[0].get("action_id")
    if action_id in (CONFIRM_ACTION, CANCEL_ACTION):
        reply = handle_confirm(payload, operations, allowed_user)
        if payload.get("response_url"):
            respond(payload["response_url"], {"text": reply, "replace": True})
        kick()
        return
    if action_id == FORM_ACTION:
        view, note = open_form(payload, daemon, allowed_user)
        if view is not None and open_view is not None:
            open_view(payload.get("trigger_id"), view)
        elif note and message.get("channel_id"):
            post(channel=message["channel_id"], thread_ts=message.get("message_ts"), text=note)
        return
    note = handle_action(payload, operations, allowed_user, notes)
    if note and message.get("channel_id"):
        post(channel=message["channel_id"], thread_ts=message.get("message_ts"), text=note)
    kick()


def tokens(secrets):
    return secrets.get(SECRET_SCOPE, BOT_TOKEN), secrets.get(SECRET_SCOPE, APP_TOKEN)


def slack_channel_factory(daemon, operations, base_url=None):
    def build(settings):
        bot, app = tokens(daemon.secrets)
        if not bot or not app:
            raise RuntimeError("Slack is set up but its tokens are not in the keychain. "
                               "Run: springer notifications setup")
        return SlackService(bot, app, settings["slack"]["user"], daemon, operations, base_url)
    return build
