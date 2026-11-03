"""Slack, over Socket Mode: the daemon opens an outbound websocket, so nothing listens
on a public port. Gate messages go to a direct message with the one person allowed to
answer. A button press is a gate.answer from the channel actor, refused for anyone
else. /springer answers status, gates, pause, and resume.

The block builders and the two handlers are plain functions over dicts, so they are
tested without Slack. Only SlackService touches slack_sdk.
"""

import json
import uuid

from ..errors import HarnessError

BOT_TOKEN = "slack-bot-token"
APP_TOKEN = "slack-app-token"
SECRET_SCOPE = "_harness"
ACTOR = "channel:slack"
DANGER = ("cancel", "discard", "send_back")
PRIMARY = ("approve", "proceed", "accept")

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
    if not view["answerable"]:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
                                                        "text": "This one has decisions to fill in. Answer it in the TUI."}]})
        return blocks
    buttons = []
    for option in view["options"][:5]:
        button = {"type": "button", "action_id": f"gate:{option['option']}",
                  "text": {"type": "plain_text", "text": option["option"].replace("_", " ")[:75]},
                  "value": json.dumps({"p": view["project"], "r": view["run_id"], "g": view["gate_id"],
                                       "o": option["option"]})}
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

    def __init__(self, bot_token, app_token, user, daemon, operations):
        from slack_sdk import WebClient
        from slack_sdk.socket_mode import SocketModeClient

        super().__init__(WebClient(token=bot_token), user)
        self.daemon, self.operations = daemon, operations
        self.socket = SocketModeClient(app_token=app_token, web_client=self.web)
        self.socket.socket_mode_request_listeners.append(self._on_request)
        self.socket.connect()

    def close(self):
        self.socket.close()

    def _on_request(self, client, request):
        from slack_sdk.socket_mode.response import SocketModeResponse

        payload = request.payload or {}
        if request.type == "slash_commands":
            text = handle_command(payload.get("text", ""), self.daemon, self.operations, payload.get("user_id"),
                                  self.user)
            client.send_socket_mode_response(SocketModeResponse(envelope_id=request.envelope_id,
                                                                payload={"text": text}))
            return
        client.send_socket_mode_response(SocketModeResponse(envelope_id=request.envelope_id))
        if request.type == "interactive" and payload.get("type") == "block_actions":
            note = handle_action(payload, self.operations, self.user)
            message = payload.get("container", {})
            if note and message.get("channel_id"):
                self.web.chat_postMessage(channel=message["channel_id"], thread_ts=message.get("message_ts"),
                                          text=note)
            notifier = getattr(self.daemon, "notifier", None)
            if notifier is not None:
                notifier.kick.set()


def tokens(secrets):
    return secrets.get(SECRET_SCOPE, BOT_TOKEN), secrets.get(SECRET_SCOPE, APP_TOKEN)


def slack_channel_factory(daemon, operations):
    def build(settings):
        bot, app = tokens(daemon.secrets)
        if not bot or not app:
            raise RuntimeError("Slack is set up but its tokens are not in the keychain. "
                               "Run: springer notifications setup")
        return SlackService(bot, app, settings["slack"]["user"], daemon, operations)
    return build
