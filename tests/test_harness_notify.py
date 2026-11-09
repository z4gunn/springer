"""Notifications and the Slack control plane: gate messages, the run feed, reminders,
escalations, thread replies, the commands, and daemon health, against the real daemon
with the mock provider and a fake channel. Nothing here reaches Slack."""

import json
from pathlib import Path
import time
import unittest

from harness_support import Clock
from test_harness_api import ApiCase, op_id

from springer_harness.notify import setup as notify_setup
from springer_harness.notify.notifier import Notifier, load_settings, quiet, save_settings
from springer_harness.notify.slack import (APP_TOKEN, BOT_TOKEN, MANIFEST, SECRET_SCOPE, closed_blocks, gate_blocks,
                                           handle_action, handle_command, handle_confirm, handle_message,
                                           handle_submission, open_form, route)
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

    def feed(self, ref, run_id, text):
        self.sent.append(("feed", text))
        return ref or {"channel": "D1", "ts": f"feed-{run_id}"}


def actions_of(blocks):
    return next(b for b in blocks if b["type"] == "actions")


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
    def test_a_stall_goes_at_once_and_the_feed_waits_out_quiet_hours(self):
        self.set_up_slack(quiet_hours=hours_around(self.clock(), True))
        self.notifier.poll()
        self.engine.ledger.append("tick_failed", detail="RuntimeError: boom")
        self.engine.ledger.append("tick_stalled", count=3, detail="RuntimeError: boom")
        self.engine.ledger.append("merge", unit_id="U-0001", pr=1, sha="abc")
        self.notifier.poll()
        self.assertEqual([k for k in self.kinds() if k != "gate"], ["post"])
        self.assertIn("stalled", self.channel.sent[-1][1])
        self.set_up_slack()
        self.notifier.poll()
        feed = [text for kind, text in self.channel.sent if kind == "feed"]
        self.assertEqual(len(feed), 1, "one batch for the run")
        self.assertIn("U-0001 merged (#1)", feed[0])
        self.assertIn("could not advance the run", feed[0])

    def test_the_feed_tells_the_run_as_it_goes_in_one_thread(self):
        self.set_up_slack()
        self.notifier.poll()
        self.engine.ledger.append("unit_state", unit_id="U-0002", to="running", reason="claimed")
        self.notifier.poll()
        self.engine.ledger.append("unit_state", unit_id="U-0002", to="retry", reason="defect: receipts do not hold")
        self.engine.ledger.append("unit_state", unit_id="U-0002", to="gated", reason="PR open, risk L2")
        self.engine.ledger.append("merge", unit_id="U-0002", pr=7, sha="abc")
        self.engine.ledger.append("unit_state", unit_id="U-0002", to="done", reason="merged at L2")
        self.notifier.poll()
        feed = [text for kind, text in self.channel.sent if kind == "feed"]
        self.assertEqual(feed[0], "U-0002 started")
        self.assertEqual(feed[1].splitlines(), ["U-0002 sent back: defect: receipts do not hold",
                                                "U-0002 PR open, risk L2", "U-0002 merged (#7)"])
        state = json.loads((Path(self.daemon.home.root) / "notify-state.json").read_text())
        self.assertEqual(state["feeds"][f"acme/{self.run_id}"]["ref"]["ts"], f"feed-{self.run_id}")
        self.assertEqual(self.notifier.thread_for(f"feed-{self.run_id}"), ("run", "acme", self.run_id))

    def test_an_escalation_no_gate_carries_is_posted_once(self):
        self.set_up_slack()
        artifacts = self.engine.run_dir / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "E-0007.json").write_text(json.dumps({"content": {
            "escalation_id": "E-0007", "escalation_type": "missing-input", "description": "No brand guide was supplied.",
            "originating_agent": "spgr-agent-design", "status": "open"}}))
        self.notifier.poll()
        self.notifier.poll()
        posts = [text for kind, text in self.channel.sent if kind == "post"]
        self.assertEqual(len(posts), 1)
        self.assertIn("E-0007", posts[0])
        self.assertIn("raised by design (missing-input): No brand guide", posts[0])

    def test_a_daemon_back_from_a_crash_says_so_once(self):
        self.set_up_slack()
        self.daemon.beat()
        self.daemon.unclean_start = None
        self.daemon.note_start()
        self.assertIsNotNone(self.daemon.unclean_start, "the last heartbeat was not marked clean")
        self.notifier.poll()
        self.notifier.poll()
        posts = [text for kind, text in self.channel.sent if kind == "post"]
        self.assertEqual(len(posts), 1)
        self.assertIn("restarted after it stopped without a clean shutdown", posts[0])
        self.daemon.mark_clean_stop()
        self.daemon.unclean_start = None
        self.daemon.note_start()
        self.assertIsNone(self.daemon.unclean_start, "a clean stop is not a crash")

    def crash_start(self):
        self.daemon.beat()  # a heartbeat never marked clean, as a killed daemon leaves it
        self.daemon.unclean_start = self.daemon.crash_loop = None
        self.notifier.restart_noted = False
        self.daemon.note_start()
        return self.daemon.hold_for_crash_loop()

    def test_a_crash_loop_pauses_every_run_and_says_so_once(self):
        self.set_up_slack()
        for _ in range(2):
            self.assertEqual(self.crash_start(), [])
            self.clock.advance(30)
        self.assertFalse(self.engine.paused(), "two crashes are not yet a loop")
        self.assertEqual(self.crash_start(), [self.run_id])
        self.assertTrue(self.engine.paused())
        self.notifier.poll()
        self.crash_start()
        self.notifier.poll()
        posts = [text for kind, text in self.channel.sent if kind == "post"]
        self.assertEqual(len(posts), 1, "the restart that reached the limit says so, later ones are quiet")
        self.assertIn("restarted 3 times", posts[0])
        self.assertIn(self.run_id, posts[0])

    def test_crashes_outside_the_window_or_after_a_clean_stop_do_not_loop(self):
        for _ in range(2):
            self.crash_start()
            self.clock.advance(400)
        self.assertEqual(self.crash_start(), [], "the first crash fell out of the ten-minute window")
        self.daemon.mark_clean_stop()
        self.daemon.note_start()
        self.assertEqual(self.crash_start(), [], "a clean stop starts the count again")
        self.assertFalse(self.engine.paused())

    def test_three_failed_ticks_in_a_row_mark_the_run_stalled(self):
        self.engine.tick = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        for _ in range(4):
            self.daemon.tick_all()
        stalls = [e.line for e in self.engine.ledger.read() if e.line.get("event") == "tick_stalled"]
        self.assertEqual(len(stalls), 1)
        self.assertEqual(stalls[0]["count"], 3)

    def test_a_finished_run_is_announced_once(self):
        self.set_up_slack()
        self.notifier.poll()
        self.engine.cycles.is_complete = lambda: True
        self.notifier.poll()
        self.notifier.poll()
        posts = [t for k, t in self.channel.sent if k == "post"]
        self.assertEqual(len(posts), 1)
        self.assertRegex(posts[0], rf"^{self.run_id} is complete: .+ · 0 merged · \d+ sessions\.$")

    def test_status_lists_finished_runs(self):
        from springer_harness.notify.slack import handle_command
        self.assertNotIn("Finished:", handle_command("status", self.daemon, None, ME, ME))
        self.engine.cycles.plan(self.engine.cycles.next_id(), "build", [], "the last batch")
        self.engine.cycles.complete_run()
        reply = handle_command("status", self.daemon, None, ME, ME)
        self.assertIn("No run in progress.", reply)
        self.assertRegex(reply, rf"Finished:\n{self.run_id}: \w{{3}} \d\d \d\d:\d\d · .+ merged · \d+ sessions")

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
        actions = actions_of(gate_blocks(view))
        self.assertEqual([(b["action_id"], b.get("style")) for b in actions["elements"]],
                         [("gate:approve", None), ("gate:send_back", "danger"), ("gate_form", None)])

    def test_only_the_recommended_option_is_styled_and_labeled(self):
        """A styled first button drew a tap the person did not mean."""
        self.set_up_slack()
        self.engine.gates.open("scope-change", "L3", ["U-0001"], "U-0001 is blocked: " + "receipt " * 400, [
            {"option": "lower the floor", "consequence": "Accept 81."},
            {"option": "drop hydration", "consequence": "Ship no runtime.", "recommended_because": "R-1106"}])
        self.notifier.poll()
        view = next(v for k, v in self.channel.sent if k == "gate")
        self.assertLessEqual(len(view["prompt"]), 1200, "a block's long detail is trimmed")
        buttons = actions_of(gate_blocks(view))["elements"]
        self.assertEqual([(b["text"]["text"], b.get("style")) for b in buttons],
                         [("1. lower the floor", None), ("2. drop hydration (recommended)", "primary"),
                          ("Answer with notes", None)])

    def direction_gate(self):
        options = [dict(OPTIONS[0], recommended_because="fits"), OPTIONS[1]]
        return self.engine.gates.open("direction-review", "L3", [], "Review the direction", options, decisions=[
            {"decision_id": "D-1", "kind": "question", "prompt": "Which setup?", "response": None},
            {"decision_id": "D-2", "kind": "question", "prompt": "Hydrate?", "response": None}])["content"]["checkpoint_id"]

    def tap(self, gate_id, user=ME):
        return {"user": {"id": user}, "trigger_id": "t-1", "actions": [
            {"action_id": "gate_form", "value": json.dumps({"p": "acme", "r": self.run_id, "g": gate_id})}]}

    def submission(self, view, option="0", answers=("A", "yes"), notes="", user=ME):
        values = {"option": {"pick": {"selected_option": {"value": option}}},
                  "notes": {"answer": {"value": notes}}}
        for block, answer in zip(["d:D-1", "d:D-2"], answers):
            values[block] = {"answer": {"value": answer}}
        return {"type": "view_submission", "user": {"id": user},
                "view": {"id": "V1", "callback_id": "gate_answer", "private_metadata": view["private_metadata"],
                         "state": {"values": values}}}

    def test_a_gate_with_decisions_gets_one_answer_button_that_opens_a_form(self):
        self.set_up_slack()
        gate_id = self.direction_gate()
        self.notifier.poll()
        view = next(v for k, v in self.channel.sent if k == "gate")
        self.assertFalse(view["answerable"])
        actions = actions_of(gate_blocks(view))
        self.assertEqual([e["action_id"] for e in actions["elements"]], ["gate_form"])
        form, note = open_form(self.tap(gate_id), self.daemon, ME)
        self.assertIsNone(note)
        inputs = [b["block_id"] for b in form["blocks"] if b["type"] == "input"]
        self.assertEqual(inputs, ["option", "d:D-1", "d:D-2", "notes"])
        pick = form["blocks"][2]["element"]
        self.assertEqual(pick["initial_option"]["value"], "0", "the recommended option is preselected")
        self.assertEqual(open_form(self.tap(gate_id, SOMEONE), self.daemon, ME)[1][:15], "Only the person")

    def test_the_form_answers_the_gate_with_its_decisions_and_notes(self):
        gate_id = self.direction_gate()
        form, _ = open_form(self.tap(gate_id), self.daemon, ME)
        ops = self.app.state.operations
        self.assertIn("Only the person", handle_submission(self.submission(form, user=SOMEONE), self.daemon, ops, ME))
        self.assertIsNone(self.engine.gates.get(gate_id)["content"]["response"])
        self.assertIsNone(handle_submission(self.submission(form, notes="ship it"), self.daemon, ops, ME))
        content = self.engine.gates.get(gate_id)["content"]
        self.assertEqual((content["response"]["option"], content["response"]["by"], content["response"]["free_text"]),
                         ("approve", "channel:slack", "ship it"))
        self.assertEqual([d["response"] for d in content["decisions"]], ["A", "yes"])
        self.assertIn("already answered", open_form(self.tap(gate_id), self.daemon, ME)[1])

    def test_a_form_that_names_no_real_gate_answers_nothing(self):
        bad = {"user": {"id": ME}, "trigger_id": "t", "actions": [
            {"action_id": "gate_form", "value": json.dumps({"p": "acme", "r": "../x", "g": "G-0001"})}]}
        self.assertEqual(open_form(bad, self.daemon, ME), (None, "That button carried no gate."))
        missing = self.tap("G-9999")
        self.assertIn("not a gate", open_form(missing, self.daemon, ME)[1])


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
        self.daemon.notifier = self.notifier  # as start_notifications does
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

    def test_the_answer_form_opens_and_submits_through_socket_mode(self):
        gate_id = self.engine.gates.open("direction-review", "L3", [], "Review the direction", OPTIONS, decisions=[
            {"decision_id": "D-1", "kind": "question", "prompt": "Which setup?", "response": None}])["content"]["checkpoint_id"]
        self.notifier.poll()
        posted = self.slack.wait(lambda: self.slack.methods("chat.postMessage"))[0]
        button = next(b for b in posted["blocks"] if b["type"] == "actions")["elements"][0]
        self.slack.wait(lambda: self.slack.client)
        self.slack.push("e-form", "interactive", {
            "type": "block_actions", "user": {"id": ME}, "trigger_id": "trig-1",
            "actions": [{"action_id": button["action_id"], "value": button["value"], "action_ts": "4.1"}],
            "container": {"channel_id": "D0SPRINGER", "message_ts": "1700000000.000001"}})
        opened = self.slack.wait(lambda: self.slack.methods("views.open"))[0]
        self.assertEqual(opened["trigger_id"], "trig-1")
        view = opened["view"] if isinstance(opened["view"], dict) else json.loads(opened["view"])
        self.slack.push("e-submit", "interactive", {
            "type": "view_submission", "user": {"id": ME},
            "view": {"id": "V9", "callback_id": view["callback_id"], "private_metadata": view["private_metadata"],
                     "state": {"values": {"option": {"pick": {"selected_option": {"value": "1"}}},
                                          "d:D-1": {"answer": {"value": "B"}},
                                          "notes": {"answer": {"value": None}}}}}})
        self.slack.wait(lambda: self.engine.gates.get(gate_id)["content"]["response"])
        content = self.engine.gates.get(gate_id)["content"]
        self.assertEqual((content["response"]["option"], content["decisions"][0]["response"]), ("send_back", "B"))
        self.notifier.poll()
        updated = self.slack.wait(lambda: self.slack.methods("chat.update"))[0]
        self.assertIn("Answered send back from Slack", json.dumps(updated["blocks"]))

    def test_a_thread_reply_and_a_confirmed_command_round_trip_through_socket_mode(self):
        gate_id = self.merge_gate()
        self.notifier.poll()
        posted = self.slack.wait(lambda: self.slack.methods("chat.postMessage"))[0]
        thread = "1700000000.000001"
        self.slack.wait(lambda: self.slack.client)
        self.slack.push("e-msg", "events_api", {"type": "event_callback", "event": {
            "type": "message", "channel_type": "im", "channel": posted["channel"], "user": ME,
            "text": "1: ship it", "thread_ts": thread, "ts": "1700000001.000001"}})
        self.slack.wait(lambda: any(a.get("envelope_id") == "e-msg" for a in self.slack.acks))
        self.slack.wait(lambda: self.engine.gates.get(gate_id)["content"]["response"])
        response = self.engine.gates.get(gate_id)["content"]["response"]
        self.assertEqual((response["option"], response["free_text"]), ("approve", "ship it"))
        answered = self.slack.wait(lambda: [m for m in self.slack.methods("chat.postMessage")
                                            if m.get("thread_ts") == thread and "Answered" in m.get("text", "")])
        self.assertEqual(answered[0]["text"], "Answered approve.")

        self.slack.push("e-pause", "slash_commands", {"command": "/springer", "text": "pause acme", "user_id": ME,
                                                      "response_url": self.slack.response_url})
        reply = self.slack.wait(lambda: self.slack.responses)[-1]
        self.assertEqual(reply["text"], f"{self.run_id} paused.")
        self.assertTrue(self.engine.paused())
        before = len(self.slack.responses)
        self.slack.push("e-restart", "slash_commands", {"command": "/springer", "text": "restart", "user_id": ME,
                                                        "response_url": self.slack.response_url})
        confirm = self.slack.wait(lambda: self.slack.responses[before:])[0]
        button = next(b for b in confirm["blocks"] if b["type"] == "actions")["elements"][1]
        self.assertEqual(button["action_id"], "op_cancel")
        self.slack.push("e-cancel", "interactive", {"type": "block_actions", "user": {"id": ME},
                                                    "response_url": self.slack.response_url,
                                                    "actions": [{"action_id": "op_cancel", "value": button["value"]}]})
        done = self.slack.wait(lambda: [r for r in self.slack.responses if r.get("text") == "Cancelled daemon.restart."])
        self.assertTrue(done[0]["replace_original"])


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
        self.assertEqual(sorted(MANIFEST["oauth_config"]["scopes"]["bot"]),
                         ["chat:write", "commands", "im:history", "im:write"])
        self.assertEqual(MANIFEST["settings"]["event_subscriptions"]["bot_events"], ["message.im"])
        self.assertFalse(MANIFEST["features"]["app_home"]["messages_tab_read_only_enabled"],
                         "a thread reply is how a person adds notes")
        self.assertNotIn("url", json.dumps(MANIFEST["features"]["slash_commands"]))


def _check(value, prefix):
    if not value.startswith(prefix):
        raise ValueError(prefix)
    return value


if __name__ == "__main__":
    unittest.main()


class ControlPlaneTest(NotifyCase):
    """Everything a person does from Slack: notes, answers by reply, commands, confirms."""

    def setUp(self):
        super().setUp()
        self.set_up_slack()
        self.ops = self.app.state.operations

    def gate_thread(self, gate_id):
        self.notifier.poll()
        state = json.loads((Path(self.daemon.home.root) / "notify-state.json").read_text())
        return state["gates"][f"acme/{self.run_id}/{gate_id}"]["ref"]["ts"]

    def message(self, text, thread, ts, user=ME):
        return {"type": "message", "channel_type": "im", "channel": "D1", "user": user, "text": text,
                "thread_ts": thread, "ts": ts}

    def test_a_thread_note_rides_on_the_tap_that_answers(self):
        gate_id = self.merge_gate()
        thread = self.gate_thread(gate_id)
        reply, where = handle_message(self.message("Check the header overflow later.", thread, "9.1"),
                                      self.daemon, self.ops, ME, self.notifier)
        self.assertEqual((reply, where), (f"Noted. It goes with your answer to {gate_id}.", thread))
        handle_message(self.message("Check the header overflow later.", thread, "9.1"), self.daemon, self.ops, ME,
                       self.notifier)
        tap = {"user": {"id": ME}, "actions": [{"action_ts": "9.2", "value": json.dumps(
            {"p": "acme", "r": self.run_id, "g": gate_id, "o": "approve"})}]}
        self.assertIsNone(handle_action(tap, self.ops, ME, self.notifier.notes))
        response = self.engine.gates.get(gate_id)["content"]["response"]
        self.assertEqual(response["free_text"], "Check the header overflow later.", "a redelivered event is one note")
        self.assertIsNone(self.notifier.notes.take(f"acme/{self.run_id}/{gate_id}"))

    def test_a_reply_with_an_option_answers_with_notes(self):
        gate_id = self.merge_gate()
        thread = self.gate_thread(gate_id)
        reply, _ = handle_message(self.message("2: fix the nav first", thread, "9.3"), self.daemon, self.ops, ME,
                                  self.notifier)
        self.assertEqual(reply, "Answered send back.")
        response = self.engine.gates.get(gate_id)["content"]["response"]
        self.assertEqual((response["option"], response["free_text"], response["by"]),
                         ("send_back", "fix the nav first", "channel:slack"))
        again, _ = handle_message(self.message("approve", thread, "9.4"), self.daemon, self.ops, ME, self.notifier)
        self.assertIn("already answered", again)

    def test_someone_else_in_the_thread_changes_nothing(self):
        gate_id = self.merge_gate()
        thread = self.gate_thread(gate_id)
        reply, _ = handle_message(self.message("approve", thread, "9.5", user=SOMEONE), self.daemon, self.ops, ME,
                                  self.notifier)
        self.assertIn("Only the person", reply)
        self.assertIsNone(self.engine.gates.get(gate_id)["content"]["response"])

    def test_a_note_in_the_run_thread_reaches_every_open_unit(self):
        unit_id = self.tick_to_unit(self.run_id)["unit_id"]
        self.notifier.poll()
        self.engine.ledger.append("unit_state", unit_id=unit_id, to="running", reason="claimed")
        self.notifier.poll()
        reply, _ = handle_message(self.message("Keep the hero copy as is.", f"feed-{self.run_id}", "9.6"),
                                  self.daemon, self.ops, ME, self.notifier)
        self.assertEqual(reply, f"Noted for {unit_id}.")
        notes = (self.engine.units.unit_dir(unit_id) / "redispatch-notes.txt").read_text()
        self.assertIn("A note from the human (channel:slack): Keep the hero copy as is.", notes)
        self.notifier.poll()
        self.assertIn("note from channel:slack: Keep the hero copy", self.channel.sent[-1][1])

    def test_a_message_outside_any_thread_gets_the_help(self):
        reply, _ = handle_message(self.message("hello", None, "9.7"), self.daemon, self.ops, ME, self.notifier)
        self.assertIn("/springer", reply)
        self.assertIsNone(handle_message({**self.message("x", None, "9.8"), "bot_id": "B1"}, self.daemon, self.ops,
                                         ME, self.notifier), "the bot's own messages are ignored")

    def confirm(self, reply, user=ME, action="op_confirm"):
        key = actions_of(reply["blocks"])["elements"][0]["value"]
        return handle_confirm({"user": {"id": user}, "actions": [{"action_id": action, "value": key}]}, self.ops, ME)

    def test_units_log_redispatch_and_cancel(self):
        unit_id = self.tick_to_unit(self.run_id)["unit_id"]
        self.assertIn(unit_id, handle_command("units", self.daemon, self.ops, ME, ME))
        state = self.engine.units.state(unit_id)
        session_dir = self.engine.sessions(unit_id).dir(state["sessions"][-1])
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "result.md").write_text(f"Status: DONE\nWrote {self.project_path}/src/app.ts and "
                                               f"/Users/someone/private/x.txt\n")
        log = handle_command(f"log {unit_id}", self.daemon, self.ops, ME, ME)
        self.assertIn("Wrote src/app.ts and <path>", log)
        self.assertNotIn(str(self.project_path), log)
        self.assertIn("Only the person", handle_command(f"log {unit_id}", self.daemon, self.ops, SOMEONE, ME))
        reply = handle_command(f"redispatch {unit_id} opus", self.daemon, self.ops, ME, ME)
        self.assertIn("Confirm unit.redispatch", reply["text"])
        self.assertIn("Only the person", self.confirm(reply, user=SOMEONE))
        self.assertEqual(self.confirm(reply), f"{unit_id} goes out again with a fresh session.")
        self.assertIn("expired or was already used", self.confirm(reply))
        reply = handle_command(f"cancel acme:{unit_id}", self.daemon, self.ops, ME, ME)
        self.assertEqual(self.confirm(reply, action="op_cancel"), "Cancelled unit.cancel.")
        self.assertNotEqual(self.engine.units.state(unit_id)["state"], "cancelled")
        self.assertIn("is not a unit", handle_command("cancel nonsense", self.daemon, self.ops, ME, ME))
        self.assertIn("No run in progress has U-0999", handle_command("log U-0999", self.daemon, self.ops, ME, ME))

    def test_polish_and_build_start_a_run_after_a_confirm(self):
        self.assertIn("already has", handle_command('polish acme "x"', self.daemon, self.ops, ME, ME))
        self.confirmed("run.cancel", run_id=self.run_id)
        self.assertIn("Only the person", handle_command('polish acme "x"', self.daemon, self.ops, SOMEONE, ME))
        self.assertIn("What is the issue?", handle_command("polish acme", self.daemon, self.ops, ME, ME))
        self.assertIn("Which project?", handle_command("build", self.daemon, self.ops, ME, ME))
        self.assertIn("No project named nope", handle_command("build nope", self.daemon, self.ops, ME, ME))
        reply = handle_command('polish acme "the footer link is the wrong color"', self.daemon, self.ops, ME, ME)
        self.assertIn("Confirm run.start", reply["text"])
        self.assertIsNone(self.daemon.active_run("acme"), "nothing starts before the tap")
        done = self.confirm(reply)
        run_id = self.daemon.active_run("acme")
        self.assertEqual(done, f"Started {run_id}. Its progress thread opens in this DM.")
        self.assertNotEqual(run_id, self.run_id)
        self.confirmed("run.cancel", run_id=run_id)
        record = self.daemon.home.project("acme")
        front, _ = self.daemon.brief("acme").load()
        self.daemon.home.save_project("acme", {**record, "adopted": True,
                                               "adopted_brief_version": front["brief_version"]})
        self.assertIn("has not changed since it was adopted", handle_command("build acme", self.daemon, self.ops, ME,
                                                                              ME))
        self.daemon.home.save_project("acme", {**record, "adopted": False})
        self.assertTrue(self.confirm(handle_command("build acme", self.daemon, self.ops, ME, ME)).startswith("Started"))

    def test_a_curly_quoted_issue_reaches_the_run_without_its_quotes(self):
        """Slack sent \u201cDEFERRED-2: ...\u201d, so the issue kept its quotes and did not
        carry the backlog item it named."""
        from springer_harness.notify.slack import _words
        self.assertEqual(_words("polish acme \u201cDEFERRED-2: the issue\u2019s words\u201d"),
                         ["polish", "acme", "DEFERRED-2: the issue's words"])
        self.assertEqual(_words('polish acme "unbalanced'), ["polish", "acme", '"unbalanced'])

    def test_a_refused_start_lists_the_brief_errors(self):
        from springer_harness.errors import HarnessError
        from springer_harness.notify.slack import _refusal
        exc = HarnessError("The brief has blocking errors.", {"critique": {"errors": [
            {"rule": "r", "section": "goals", "message": "Goals is empty."}]}})
        self.assertEqual(_refusal(exc), "Not done: The brief has blocking errors.\n- goals: Goals is empty.")

    def test_release_from_slack_runs_the_command_and_posts_the_result(self):
        self.notifier.poll()
        self.assertIn("has no release command", handle_command("release acme", self.daemon, self.ops, ME, ME))
        script = "import sys; a = input('Type go: '); print('shipped' if a == 'go' else 'no-go'); sys.exit(a != 'go')"
        (self.project_path / "deploy.py").write_text(script)
        reply = handle_command('release-command acme "python3 deploy.py" go', self.daemon, self.ops, SOMEONE, ME)
        self.assertIn("Only the person", reply)
        reply = handle_command('release-command acme "python3 deploy.py" go', self.daemon, self.ops, ME, ME)
        self.assertEqual(self.confirm(reply), "acme releases with: python3 deploy.py, typing go at its prompt.")
        self.assertEqual(self.daemon.settings("acme")["release_confirm"], "go")
        reply = handle_command("release acme", self.daemon, self.ops, ME, ME)
        self.assertIn("Confirm project.release", reply["text"])
        self.assertIn("Deploying acme", self.confirm(reply))
        for _ in range(200):
            if self.daemon.releases.running("acme") is False and \
                    [e for e in self.engine.ledger.read() if e.line.get("event") == "release_finished"]:
                break
            time.sleep(0.05)
        finished = [e.line for e in self.engine.ledger.read() if e.line.get("event") == "release_finished"]
        self.assertEqual(len(finished), 1, [e.line for e in self.engine.ledger.read()][-3:])
        self.assertIn("shipped", finished[0]["detail"])
        self.notifier.poll()
        posts = [t for k, t in self.channel.sent if k == "post"]
        self.assertTrue(any("released" in p and "to production" in p for p in posts), posts)

    def test_checks_from_slack(self):
        self.assertIn("has no project checks", handle_command("checks acme", self.daemon, self.ops, ME, ME))
        reply = handle_command('checks acme "npm run check"', self.daemon, self.ops, ME, ME)
        self.assertEqual(self.confirm(reply), "acme runs on every code change: npm run check")
        self.assertIn("npm run check", handle_command("checks acme", self.daemon, self.ops, ME, ME))
        self.assertIn("Only the person", handle_command("checks acme none", self.daemon, self.ops, SOMEONE, ME))
        self.assertEqual(self.confirm(handle_command("checks acme none", self.daemon, self.ops, ME, ME)),
                         "acme has no project checks now.")

    def test_a_ruling_pins_through_the_brief_and_opens_its_gate(self):
        reply = handle_command('ruling "R-2001: keep the 2:1 hero"', self.daemon, self.ops, ME, ME)
        done = self.confirm(reply)
        self.assertIn("Pinned.", done)
        gate_id = done.split()[1]
        gate = self.engine.gates.get(gate_id)["content"]
        self.assertEqual(gate["checkpoint_type"], "scope-change")
        front, _ = self.daemon.brief("acme").load()
        self.assertIn("R-2001: keep the 2:1 hero", front["pinned_rulings"])

    def test_unlock_writes_the_ruling_file_and_refuses_paths_outside(self):
        reply = handle_command('unlock acme eslint.config.js "the scaffold needs import order"', self.daemon,
                               self.ops, ME, ME)
        self.assertEqual(self.confirm(reply), "eslint.config.js is unlocked for the next session that needs it.")
        record = json.loads((self.project_path / "runs" / "_config-unlock.json").read_text())
        self.assertEqual(record["paths"][0]["path"], "eslint.config.js")
        self.assertIn("the scaffold needs import order", record["paths"][0]["reason"])
        for bad in ("../outside.json", "/etc/passwd", "runs/_config-unlock.json"):
            reply = handle_command(f'unlock acme {bad} "no"', self.daemon, self.ops, ME, ME)
            self.assertIn("Not done", self.confirm(reply))
        with self.assertRaises(Exception):
            self.ops.apply(op_id(), "project.unlock_config", "acme", None, {"path": "x.json", "reason": "y"}, None,
                           "chat")

    def test_restart_drains_then_restarts_and_the_next_start_resumes(self):
        restarted = []
        self.daemon.restart_process = lambda: restarted.append(True)
        self.engine.units.by_state = lambda *states: []
        reply = handle_command("restart", self.daemon, self.ops, ME, ME)
        self.assertIn("Draining", self.confirm(reply))
        for _ in range(100):
            if restarted:
                break
            time.sleep(0.05)
        self.assertEqual(restarted, [True])
        self.assertTrue(self.engine.paused())
        self.assertEqual(self.daemon.resume_after_restart(), [self.run_id])
        self.assertFalse(self.engine.paused())
        self.assertFalse((Path(self.daemon.home.root) / "restart.json").exists())

