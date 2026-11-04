"""Notifications: gate messages, the digest, reminders, and the Slack handlers, against
the real daemon with the mock provider and a fake channel. Nothing here reaches Slack."""

import json
from pathlib import Path
import time
import unittest

from harness_support import Clock
from test_harness_api import ApiCase, op_id

from springer_harness.notify import setup as notify_setup
from springer_harness.notify.notifier import Notifier, load_settings, quiet, save_settings
from springer_harness.notify.slack import (APP_TOKEN, BOT_TOKEN, MANIFEST, SECRET_SCOPE, closed_blocks, gate_blocks,
                                           handle_action, handle_command, route)
from springer_harness.notify.slack import slack_channel_factory
from springer_harness.providers.secrets import MemorySecrets
from slack_fake import FakeSlack

ME, SOMEONE = "U0ME", "U0OTHER"
OPTIONS = [{"option": "approve", "consequence": "Merges the change."},
           {"option": "send_back", "consequence": "Returns it to the builder."}]


class FakeChannel:
    def __init__(self, user=ME):
        self.user = user
        self.sent = []

    def post_gate(self, view):
        self.sent.append(("gate", view))
        return {"channel": "D1", "ts": str(len(self.sent))}

    def close_gate(self, ref, view):
        self.sent.append(("close", view))

    def reply(self, ref, text):
        self.sent.append(("reply", text))

    def post(self, text):
        self.sent.append(("post", text))


def hours_around(now, inside):
    hour = time.localtime(now).tm_hour
    return [hour, (hour + 1) % 24] if inside else [(hour + 2) % 24, (hour + 3) % 24]


class NotifyCase(ApiCase):
    def setUp(self):
        super().setUp()
        self.run_id = self.start()
        self.engine = self.daemon.engine("acme", self.run_id)
        self.channel = FakeChannel()
        self.notifier = Notifier(self.daemon, lambda settings: self.channel, clock=self.clock)

    def set_up_slack(self, **extra):
        save_settings(self.daemon.home.root, {"slack": {"user": ME}, "quiet_hours": hours_around(self.clock(), False),
                                              **extra})

    def merge_gate(self, findings=()):
        context = {"review": "approve", "findings": list(findings)}
        return self.engine.gates.open("pr-merge", "L2", ["U-0001"], "Merge change 1 for U-0001?", OPTIONS,
                                      context=context)["content"]["checkpoint_id"]

    def kinds(self):
        return [kind for kind, _ in self.channel.sent]


class GateMessageTest(NotifyCase):
    def test_nothing_is_sent_until_slack_is_set_up(self):
        self.merge_gate()
        self.assertEqual(self.notifier.poll(), [])
        self.assertIsNone(load_settings(self.daemon.home.root))

    def test_a_gate_is_posted_once_and_closed_when_answered_from_the_channel(self):
        self.set_up_slack()
        gate_id = self.merge_gate()
        self.notifier.poll()
        self.notifier.poll()
        posted = [view for kind, view in self.channel.sent if kind == "gate" and view["gate_id"] == gate_id]
        self.assertEqual(len(posted), 1)
        self.assertEqual(posted[0]["review"], "approve")
        payload = {"user": {"id": ME}, "actions": [{"action_ts": "1.1", "value": json.dumps(
            {"p": "acme", "r": self.run_id, "g": gate_id, "o": "approve"})}]}
        self.assertIsNone(handle_action(payload, self.app.state.operations, ME))
        self.assertEqual(self.engine.gates.get(gate_id)["content"]["response"]["by"], "channel:slack")
        self.notifier.poll()
        closed = [view for kind, view in self.channel.sent if kind == "close"]
        self.assertEqual(closed[0]["response"]["option"], "approve")
        self.assertIn("Answered approve from Slack", json.dumps(closed_blocks(closed[0])))

    def test_a_gate_already_open_when_slack_is_set_up_is_still_posted(self):
        gate_id = self.merge_gate()
        self.set_up_slack()
        self.notifier.poll()
        self.assertIn(gate_id, [view["gate_id"] for kind, view in self.channel.sent if kind == "gate"])

    def test_a_waiting_gate_gets_one_reminder(self):
        self.set_up_slack(remind_hours=1)
        self.merge_gate()
        self.notifier.poll()
        self.clock.advance(3601)
        self.notifier.poll()
        self.clock.advance(3601)
        self.notifier.poll()
        self.assertEqual(self.kinds().count("reply"), 1)

    def test_a_channel_failure_is_retried_on_the_next_poll(self):
        self.set_up_slack()
        self.merge_gate()
        real = self.channel.post_gate
        self.channel.post_gate = lambda view: (_ for _ in ()).throw(OSError("slack is down"))
        self.notifier.poll()
        self.assertIn("slack is down", self.notifier.last_error)
        self.channel.post_gate = real
        self.notifier.poll()
        self.assertIn("gate", self.kinds())


class EventTest(NotifyCase):
    def test_a_stall_goes_at_once_and_a_merge_waits_for_the_digest(self):
        self.set_up_slack(quiet_hours=hours_around(self.clock(), True), digest_minutes=0)
        self.notifier.poll()
        self.engine.ledger.append("tick_failed", detail="RuntimeError: boom")
        self.engine.ledger.append("merge", unit_id="U-0001", pr=1, sha="abc")
        self.notifier.poll()
        stalled = [text for kind, text in self.channel.sent if kind == "post"]
        self.assertEqual(len(stalled), 1)
        self.assertIn("stalled", stalled[0])
        self.set_up_slack(digest_minutes=0)
        self.notifier.poll()
        digest = [text for kind, text in self.channel.sent if kind == "post"][-1]
        self.assertIn("U-0001 merged (#1)", digest)

    def test_a_finished_run_is_announced_once(self):
        self.set_up_slack()
        self.notifier.poll()
        self.engine.cycles.is_complete = lambda: True
        self.notifier.poll()
        self.notifier.poll()
        self.assertEqual([t for k, t in self.channel.sent if k == "post"], [f"{self.run_id} is complete."])

    def test_quiet_hours_wrap_past_midnight(self):
        noon = time.mktime((2026, 11, 3, 12, 0, 0, 0, 0, -1))
        night = time.mktime((2026, 11, 3, 23, 0, 0, 0, 0, -1))
        self.assertEqual((quiet([22, 7], noon), quiet([22, 7], night)), (False, True))


class SlackHandlerTest(NotifyCase):
    def test_only_the_set_up_person_can_answer(self):
        gate_id = self.merge_gate()
        payload = {"user": {"id": SOMEONE}, "actions": [{"action_ts": "2.2", "value": json.dumps(
            {"p": "acme", "r": self.run_id, "g": gate_id, "o": "approve"})}]}
        self.assertIn("Only the person", handle_action(payload, self.app.state.operations, ME))
        self.assertIsNone(self.engine.gates.get(gate_id)["content"]["response"])

    def test_a_second_tap_says_the_gate_is_answered(self):
        gate_id = self.merge_gate()
        value = json.dumps({"p": "acme", "r": self.run_id, "g": gate_id, "o": "approve"})
        first = {"user": {"id": ME}, "actions": [{"action_ts": "3.1", "value": value}]}
        second = {"user": {"id": ME}, "actions": [{"action_ts": "3.2", "value": value}]}
        ops = self.app.state.operations
        self.assertIsNone(handle_action(first, ops, ME))
        self.assertIsNone(handle_action(first, ops, ME), "a retried delivery is the same operation")
        self.assertIn("already answered", handle_action(second, ops, ME))

    def test_status_gates_pause_and_resume(self):
        gate_id = self.merge_gate()
        ops = self.app.state.operations
        self.assertIn(self.run_id, handle_command("status", self.daemon, ops, ME, ME))
        self.assertIn(gate_id, handle_command("gates", self.daemon, ops, ME, ME))
        self.assertIn("Only the person", handle_command("pause acme", self.daemon, ops, SOMEONE, ME))
        self.assertEqual(handle_command("pause acme", self.daemon, ops, ME, ME), f"{self.run_id} paused.")
        self.assertIn("paused", handle_command("status", self.daemon, ops, ME, ME))
        self.assertEqual(handle_command("resume acme", self.daemon, ops, ME, ME), f"{self.run_id} resumed.")
        self.assertIn("No project", handle_command("pause nope", self.daemon, ops, ME, ME))

    def test_the_ack_goes_before_the_daemon_lock_is_taken(self):
        order = []
        lock = self.daemon.lock

        class Watched:
            def __enter__(self):
                order.append("lock")
                return lock.__enter__()

            def __exit__(self, *exc):
                return lock.__exit__(*exc)

        self.daemon.lock = Watched()
        try:
            route("slash_commands", {"text": "status", "user_id": ME, "response_url": "https://hooks.example/r"},
                  lambda: order.append("ack"), lambda url, text: order.append(("reply", url, text)), None,
                  self.daemon, self.app.state.operations, ME)
        finally:
            self.daemon.lock = lock
        self.assertEqual(order[0], "ack")
        self.assertIn("lock", order)
        self.assertEqual(order[-1][:2], ("reply", "https://hooks.example/r"))
        self.assertIn(self.run_id, order[-1][2])

    def test_the_message_shows_review_counts_and_no_file_paths(self):
        findings = [{"severity": "P2", "file": "src/secret/path.ts", "detail": "log fields missing"},
                    {"severity": "P3", "file": "src/other.ts", "detail": "dead config"}]
        self.set_up_slack()
        self.merge_gate(findings)
        self.notifier.poll()
        view = next(v for k, v in self.channel.sent if k == "gate")
        blocks = json.dumps(gate_blocks(view))
        self.assertIn("1 P2, 1 P3", blocks)
        self.assertIn("log fields missing", blocks)
        self.assertNotIn("src/", blocks)
        actions = gate_blocks(view)[-1]
        self.assertEqual([(b["action_id"], b.get("style")) for b in actions["elements"]],
                         [("gate:approve", "primary"), ("gate:send_back", "danger")])

    def test_a_gate_with_decisions_is_left_to_the_tui(self):
        self.set_up_slack()
        self.engine.gates.open("direction-review", "L3", [], "Review the direction", OPTIONS,
                               decisions=[{"decision_id": "D-1", "prompt": "Which option?", "response": None}])
        self.notifier.poll()
        view = next(v for k, v in self.channel.sent if k == "gate")
        self.assertFalse(view["answerable"])
        self.assertNotIn("actions", [b["type"] for b in gate_blocks(view)])


class SocketModeTest(NotifyCase):
    """The real slack_sdk client over a real websocket to a local fake Slack: a gate is
    posted with buttons, a tap is acked and answers the gate, the message closes, and
    /springer replies through its response_url."""

    def setUp(self):
        super().setUp()
        self.slack = FakeSlack()
        self.addCleanup(self.slack.close)
        self.secrets.set(SECRET_SCOPE, BOT_TOKEN, "xoxb-fake")
        self.secrets.set(SECRET_SCOPE, APP_TOKEN, "xapp-fake")
        self.set_up_slack()
        factory = slack_channel_factory(self.daemon, self.app.state.operations, self.slack.base_url)
        self.notifier = Notifier(self.daemon, factory, clock=self.clock)
        self.addCleanup(lambda: self.notifier.channel and self.notifier.channel.close())

    def test_a_tap_and_a_command_round_trip_through_socket_mode(self):
        gate_id = self.merge_gate()
        self.notifier.poll()
        posted = self.slack.wait(lambda: self.slack.methods("chat.postMessage"))[0]
        self.assertEqual(posted["channel"], "D0SPRINGER")
        actions = next(block for block in posted["blocks"] if block["type"] == "actions")
        approve = next(e for e in actions["elements"] if e["action_id"] == "gate:approve")
        self.slack.wait(lambda: self.slack.client)

        self.slack.push("e-other", "interactive", {
            "type": "block_actions", "user": {"id": SOMEONE},
            "actions": [{"action_id": approve["action_id"], "value": approve["value"], "action_ts": "2.1"}],
            "container": {"channel_id": "D0SPRINGER", "message_ts": "1700000000.000001"}})
        self.slack.wait(lambda: any("Only the person" in m.get("text", "")
                                    for m in self.slack.methods("chat.postMessage")))
        self.assertIsNone(self.engine.gates.get(gate_id)["content"]["response"])

        self.slack.push("e-tap", "interactive", {
            "type": "block_actions", "user": {"id": ME},
            "actions": [{"action_id": approve["action_id"], "value": approve["value"], "action_ts": "2.2"}],
            "container": {"channel_id": "D0SPRINGER", "message_ts": "1700000000.000001"}})
        self.slack.wait(lambda: any(a.get("envelope_id") == "e-tap" for a in self.slack.acks))
        self.slack.wait(lambda: self.engine.gates.get(gate_id)["content"]["response"])
        self.assertEqual(self.engine.gates.get(gate_id)["content"]["response"]["by"], "channel:slack")
        self.notifier.poll()
        updated = self.slack.wait(lambda: self.slack.methods("chat.update"))[0]
        self.assertIn("Answered approve from Slack", json.dumps(updated["blocks"]))

        self.slack.push("e-cmd", "slash_commands", {"command": "/springer", "text": "status", "user_id": ME,
                                                    "response_url": self.slack.response_url})
        self.slack.wait(lambda: any(a.get("envelope_id") == "e-cmd" for a in self.slack.acks))
        reply = self.slack.wait(lambda: self.slack.responses)[0]
        self.assertEqual(reply["response_type"], "ephemeral")
        self.assertIn(self.run_id, reply["text"])


class SetupTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = self.tmp.name
        self.secrets = MemorySecrets()

    class Web:
        def __init__(self, token, refuse=False):
            self.token, self.refuse, self.sent = token, refuse, []

        def auth_test(self):
            if self.refuse:
                raise RuntimeError("invalid_auth")
            return {"team": "Acme"}

        def conversations_open(self, users):
            return {"channel": {"id": "D1"}}

        def chat_postMessage(self, **kwargs):
            self.sent.append(kwargs)

        def apps_connections_open(self, app_token):
            if app_token == "xapp-config-only":
                raise RuntimeError("missing_scope: needed connections:write")
            return {"url": "wss://example/link"}

    def run_setup(self, answers, refuse=False):
        secrets = iter(answers[:2])
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            return notify_setup.setup(self.home, self.secrets, ask=lambda _: answers[2],
                                      ask_secret=lambda prompt, prefix: _check(next(secrets), prefix),
                                      client=lambda token: self.Web(token, refuse))

    def test_tokens_go_to_the_keychain_and_never_to_a_file(self):
        self.assertEqual(self.run_setup(["xoxb-1", "xapp-2", "U0ME"]), 0)
        self.assertEqual((self.secrets.get(SECRET_SCOPE, BOT_TOKEN), self.secrets.get(SECRET_SCOPE, APP_TOKEN)),
                         ("xoxb-1", "xapp-2"))
        stored = (load_settings(self.home), (Path(self.home) / "notifications.json").read_text())
        self.assertEqual(stored[0]["slack"], {"user": "U0ME"})
        self.assertNotIn("xox", stored[1])

    def test_a_refused_token_saves_nothing(self):
        self.assertEqual(self.run_setup(["xoxb-1", "xapp-2", "U0ME"], refuse=True), 1)
        self.assertIsNone(load_settings(self.home))
        self.assertIsNone(self.secrets.get(SECRET_SCOPE, BOT_TOKEN))

    def test_an_app_token_without_connections_write_saves_nothing(self):
        self.assertEqual(self.run_setup(["xoxb-1", "xapp-config-only", "U0ME"]), 1)
        self.assertIsNone(load_settings(self.home))
        self.assertIsNone(self.secrets.get(SECRET_SCOPE, APP_TOKEN))

    def test_off_removes_the_settings_and_the_tokens(self):
        self.run_setup(["xoxb-1", "xapp-2", "U0ME"])
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            notify_setup.off(self.home, self.secrets)
        self.assertIsNone(load_settings(self.home))
        self.assertIsNone(self.secrets.get(SECRET_SCOPE, BOT_TOKEN))

    def test_the_manifest_uses_socket_mode_and_least_scopes(self):
        self.assertTrue(MANIFEST["settings"]["socket_mode_enabled"])
        self.assertEqual(sorted(MANIFEST["oauth_config"]["scopes"]["bot"]), ["chat:write", "commands", "im:write"])
        self.assertNotIn("url", json.dumps(MANIFEST["features"]["slash_commands"]))


def _check(value, prefix):
    if not value.startswith(prefix):
        raise ValueError(prefix)
    return value


if __name__ == "__main__":
    unittest.main()
