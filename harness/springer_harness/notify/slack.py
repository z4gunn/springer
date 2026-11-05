"""Slack, over Socket Mode: the daemon opens an outbound websocket, so nothing listens
on a public port. Gate messages go to a direct message with the one person allowed to
answer. A button press is a gate.answer from the channel actor, refused for anyone
else. A gate with decisions gets one Answer button that opens a form instead. /springer answers status, gates, pause, and resume.

The block builders and the two handlers are plain functions over dicts, so they are
tested without Slack. Only SlackService touches slack_sdk.
"""

import json
from pathlib import Path
import re
import uuid

from ..errors import HarnessError

BOT_TOKEN = "slack-bot-token"
APP_TOKEN = "slack-app-token"
SECRET_SCOPE = "_harness"
ACTOR = "channel:slack"
DANGER = ("cancel", "discard", "send_back")
PRIMARY = ("approve", "proceed", "accept")
FORM_ACTION = "gate_form"
FORM_CALLBACK = "gate_answer"
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

MANIFEST = {
    "display_information": {"name": "Springer", "description": "Gates and run status from the Springer harness"},
    "features": {
        "app_home": {"home_tab_enabled": False, "messages_tab_enabled": True, "messages_tab_read_only_enabled": True},
        "bot_user": {"display_name": "springer", "always_online": True},
        "slash_commands": [{"command": "/springer", "description": "Run status, open gates, pause or resume a run",
                            "usage_hint": "status | gates | pause <project> | resume <project>",
                            "should_escape": False}],
    },
    "oauth_config": {"scopes": {"bot": ["chat:write", "im:write", "commands"]}},
    "settings": {"interactivity": {"is_enabled": True}, "org_deploy_enabled": False, "socket_mode_enabled": True,
                 "token_rotation_enabled": False},
}


# --- messages ---

def gate_text(view):
    return f"{view['project']} · {view['run_id']} · {view['gate_id']} ({view['level']}): {view['prompt']}"


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
    consequences = [f"{o['option'].replace('_', ' ')}: {o['consequence']}" for o in view["options"] if o["consequence"]]
    if consequences:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "\n".join(consequences)[:2900]}]})
    target = {"p": view["project"], "r": view["run_id"], "g": view["gate_id"]}
    if not view["answerable"]:
        # Decisions take written answers, so the tap opens a form instead of answering.
        blocks.append({"type": "actions", "block_id": f"gate-{view['gate_id']}", "elements": [
            {"type": "button", "action_id": FORM_ACTION, "style": "primary", "value": json.dumps(target),
             "text": {"type": "plain_text", "text": "Answer"}}]})
        return blocks
    buttons = []
    for option in view["options"][:5]:
        button = {"type": "button", "action_id": f"gate:{option['option']}",
                  "text": {"type": "plain_text", "text": option["option"].replace("_", " ")[:75]},
                  "value": json.dumps({**target, "o": option["option"]})}
        if option["option"] in PRIMARY:
            button["style"] = "primary"
        elif option["option"] in DANGER:
            button["style"] = "danger"
        buttons.append(button)
    blocks.append({"type": "actions", "block_id": f"gate-{view['gate_id']}", "elements": buttons})
    return blocks


def closed_blocks(view):
    if view["response"]:
        response = view["response"]
        by = {"channel:slack": "from Slack", "tui": "in the TUI"}.get(response.get("by"), f"by {response.get('by')}")
        outcome = f"Answered {response['option'].replace('_', ' ')} {by}."
    else:
        outcome = "Withdrawn: the work went back to its builder."
    return [{"type": "section", "text": {"type": "mrkdwn", "text": f"~{view['gate_id']}~ ({view['level']}) in "
                                                                  f"{view['run_id']}\n{view['prompt']}"}},
            {"type": "context", "elements": [{"type": "mrkdwn", "text": outcome}]}]


# --- the answer form, for a gate with decisions ---

def form_view(target, content):
    """A modal: the option as a dropdown, one text box per decision, and optional notes."""
    options = content["options"]
    listing = "\n".join(f"*{n}.* {o['option']}" + (f"\n{o['consequence']}" if o.get("consequence") else "")
                        for n, o in enumerate(options, 1))
    choices = [{"text": {"type": "plain_text", "text": f"{n}. {o['option']}"[:75]}, "value": str(n - 1)}
               for n, o in enumerate(options, 1)]
    pick = {"type": "static_select", "action_id": "pick", "options": choices[:100],
            "placeholder": {"type": "plain_text", "text": "Pick an option"}}
    recommended = next((c for c, o in zip(choices, options) if o.get("recommended_because")), None)
    if recommended:
        pick["initial_option"] = recommended
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": content["decision_prompt"][:3000]}},
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


def handle_submission(payload, daemon, operations, allowed_user):
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
    notes = (values.get("notes", {}).get("answer", {}).get("value") or "").strip()
    args = {"gate_id": target["g"], "option": option, "decisions": decisions}
    if notes:
        args["free_text"] = notes
    op_id = f"slack-{view.get('id') or uuid.uuid4().hex}"
    try:
        outcome = operations.apply(op_id, "gate.answer", target["p"], target["r"], args, None, ACTOR)
    except HarnessError as exc:
        return f"{target['g']} not answered: {exc}"
    if outcome.get("status") == "needs_confirmation":
        return f"{target['g']} needs a confirmation. Answer it in the TUI."
    return None


# --- handlers ---

def handle_action(payload, operations, allowed_user):
    """A button press. Returns the line to post back in the gate's thread."""
    if payload.get("user", {}).get("id") != allowed_user:
        return "Only the person this app was set up for can answer gates."
    action = (payload.get("actions") or [{}])[0]
    try:
        target = json.loads(action.get("value", ""))
    except ValueError:
        return "That button carried no gate."
    op_id = f"slack-{action.get('action_ts') or uuid.uuid4().hex}"
    try:
        outcome = operations.apply(op_id, "gate.answer", target["p"], target["r"],
                                   {"gate_id": target["g"], "option": target["o"]}, None, ACTOR)
    except HarnessError as exc:
        return f"Not answered: {exc}"
    if outcome.get("status") == "needs_confirmation":
        return "This answer needs a confirmation. Answer it in the TUI."
    return None


def handle_command(text, daemon, operations, user, allowed_user):
    """/springer. Returns the reply, shown only to the person who typed it."""
    words = (text or "").split()
    verb = words[0].lower() if words else "status"
    if verb in ("status", "gates"):
        return _status(daemon) if verb == "status" else _gates(daemon)
    if verb in ("pause", "resume"):
        if user != allowed_user:
            return "Only the person this app was set up for can pause or resume a run."
        if len(words) < 2:
            return f"Which project? /springer {verb} <project>"
        slug = words[1]
        with daemon.lock:
            try:
                daemon.home.project(slug)
            except HarnessError:
                return f"No project named {slug}."
            run_id = daemon.active_run(slug)
        if not run_id:
            return f"{slug} has no run in progress."
        args = {"reason": "paused from Slack"} if verb == "pause" else {}
        try:
            operations.apply(f"slack-{uuid.uuid4().hex}", f"run.{verb}", slug, run_id, args, None, ACTOR)
        except HarnessError as exc:
            return f"Not done: {exc}"
        return f"{run_id} {'paused' if verb == 'pause' else 'resumed'}."
    return "Try /springer status, /springer gates, /springer pause <project>, or /springer resume <project>."


def _runs(daemon):
    with daemon.lock:
        for slug, record in daemon.home.projects().items():
            if record.get("archived"):
                continue
            run_id = daemon.active_run(slug)
            if run_id:
                yield slug, run_id, daemon.engine(slug, run_id).project()["content"]


def _status(daemon):
    lines = []
    for slug, run_id, run in _runs(daemon):
        units = ", ".join(f"{n} {state}" for state, n in sorted(run["units"].items()) if n)
        flags = " · paused" if run["paused"] else ""
        lines.append(f"{run_id}: {run['active_phase']}{flags} · {len(run['open_gates'])} waiting on you · "
                     f"{len(run['in_flight'])} running · {units}")
    return "\n".join(lines) or "No run in progress."


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


class SlackService(SlackChannel):
    """The channel plus the Socket Mode listener for buttons and /springer."""

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

        def respond(url, text):
            WebhookClient(url).send(text=text, response_type="ephemeral")

        def open_view(trigger_id, view):
            self.web.views_open(trigger_id=trigger_id, view=view)

        route(request.type, request.payload or {}, ack, respond, self.web.chat_postMessage, self.daemon,
              self.operations, self.user, open_view=open_view, dm=self.dm)


def route(kind, payload, ack, respond, post, daemon, operations, allowed_user, open_view=None, dm=None):
    """One Socket Mode request. Slack wants the ack within 3 seconds and a tick holds the
    daemon lock through git and merge work, so the ack goes first and the answer after:
    a command's reply through its response_url, a button's note in the gate's thread, a
    form's note in the direct message. The Answer tap opens its form without the lock,
    because the trigger it carries expires 3 seconds after the tap."""
    ack()
    if kind == "slash_commands":
        text = handle_command(payload.get("text", ""), daemon, operations, payload.get("user_id"), allowed_user)
        if payload.get("response_url"):
            respond(payload["response_url"], text)
        return
    notifier = getattr(daemon, "notifier", None)
    if kind == "interactive" and payload.get("type") == "view_submission":
        if (payload.get("view") or {}).get("callback_id") != FORM_CALLBACK:
            return
        note = handle_submission(payload, daemon, operations, allowed_user)
        if note and dm is not None:
            post(channel=dm(), text=note)
        if notifier is not None:
            notifier.kick.set()
        return
    if kind == "interactive" and payload.get("type") == "block_actions":
        message = payload.get("container", {})
        if (payload.get("actions") or [{}])[0].get("action_id") == FORM_ACTION:
            view, note = open_form(payload, daemon, allowed_user)
            if view is not None and open_view is not None:
                open_view(payload.get("trigger_id"), view)
            elif note and message.get("channel_id"):
                post(channel=message["channel_id"], thread_ts=message.get("message_ts"), text=note)
            return
        note = handle_action(payload, operations, allowed_user)
        if note and message.get("channel_id"):
            post(channel=message["channel_id"], thread_ts=message.get("message_ts"), text=note)
        if notifier is not None:
            notifier.kick.set()


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
