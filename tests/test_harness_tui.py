"""The TUI against a real daemon over a real socket, read the way a person reads it:
what is on the screen after a key press. One test per row of the Screen coverage table
in docs/harness/api-contract.md, and a meta-test fails when a row has no test."""

import ast
import asyncio
import json
import os
import re
import shutil
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from harness_support import REPO, git_project

try:
    import uvicorn
    from textual.widgets import DataTable, Input, OptionList, Static, TextArea
    HAVE_TUI = True
except ImportError:
    HAVE_TUI = False

if HAVE_TUI:
    from springer_harness.api.app import create_app
    from springer_harness.daemon import Daemon
    from springer_harness.providers.mock import MockProvider, MockSourceHost
    from springer_harness.providers.mock_scenario import demo_planner_factory, demo_script
    from springer_harness.providers.secrets import MemorySecrets
    from springer_harness.state.brief import BriefStore
    from springer_harness.tui.app import LOST, SpringerApp
    from springer_harness.tui.client import ApiClient
    from springer_harness.tui.dialogs import ConfirmDialog, FormDialog, TextDialog

GOOD = {"Problem": "Freelancers lose track of invoices.", "Users": "- Fran: a freelancer",
        "Core flows": "### Send an invoice\nWho: Fran\nTrigger: The work is done.\n1. Write it\nOutcome: Sent.\nCritical: yes\n",
        "Non-goals": "None yet.", "Success criteria": "One invoice sent."}
BACKLOG = {"epics": [{"epic_id": "E-1", "title": "Invoice", "critical": True, "features": [
    {"feature_id": "F-1", "title": "Editor", "mvp": True, "deferred": False, "stories": [
        {"story_id": "S-1", "title": "Draft [wip]", "wave": 1, "unit_ids": [], "pr": {"number": 7, "url": "http://pr/7"}, "depends_on": []},
        {"story_id": "S-2", "title": "Send", "wave": 1, "unit_ids": [], "pr": None, "depends_on": []},
        {"story_id": "S-3", "title": "Remind", "wave": 2, "unit_ids": [], "pr": None, "depends_on": ["S-1"]}]},
    {"feature_id": "F-2", "title": "Reports", "mvp": False, "deferred": False, "stories": []}]}],
    "unknowns": [{"unknown_id": "UK-1", "question": "Which currency?", "answer": None}]}


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@unittest.skipUnless(HAVE_TUI, "the TUI dependencies are not installed")
class TuiCase(unittest.IsolatedAsyncioTestCase):
    SIZE = (120, 44)

    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.host = MockSourceHost()
        self.secrets = MemorySecrets()
        self.daemon = Daemon(self.root / "home", MockProvider(demo_script()), self.host, demo_planner_factory(),
                             self.secrets, time.time)
        self.api = create_app(self.daemon)
        self.api.state.heartbeat_seconds = 0.5
        self.port = free_port()
        self._serve()
        self.project = git_project(self.root / "acme")
        self.daemon.home.save_project("acme", {"slug": "acme", "name": "Acme", "path": str(self.project),
                                               "archived": False, "runtime_version": "abc"})
        store = BriefStore(self.project)
        store.create("Acme")
        self.version = 1
        for name, body in GOOD.items():
            self.version = store.update_section(name, body, self.version)
        self.client = ApiClient(f"http://127.0.0.1:{self.port}", self.daemon.home.token())
        self.opened = []
        self.app = SpringerApp(self.client, open_url=self.opened.append)

    def _serve(self):
        self.server = uvicorn.Server(uvicorn.Config(self.api, host="127.0.0.1", port=self.port, log_level="error"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        while not self.server.started:
            time.sleep(0.01)

    async def asyncTearDown(self):
        await self.client.close()
        self.server.should_exit = True
        self.server.force_exit = True  # an open stream would hold the shutdown for its timeout
        await asyncio.to_thread(self.thread.join, 5)

    def text(self):
        """What a person sees, top of the screen to the bottom."""
        strips = self.app.screen._compositor.render_strips()
        toasts = [str(n.message) for n in self.app._notifications]
        return "\n".join([strip.text.rstrip() for strip in strips] + toasts)

    async def see(self, pilot, *wanted, timeout=8):
        deadline = time.time() + timeout
        while time.time() < deadline:
            await pilot.pause(0.05)
            screen = self.text()
            if all(w in screen for w in wanted):
                return screen
        self.fail(f"never saw {wanted} on:\n{self.text()}")

    async def until(self, pilot, predicate, timeout=8):
        deadline = time.time() + timeout
        while time.time() < deadline:
            await pilot.pause(0.05)
            if predicate():
                return
        self.fail(f"condition never held. Screen:\n{self.text()}")

    async def dialog(self, pilot, kind):
        await self.until(pilot, lambda: isinstance(self.app.screen, kind))
        await pilot.pause(0.1)

    async def tick(self, count=1):
        for _ in range(count):
            await asyncio.to_thread(self.daemon.tick_all)

    async def open_acme(self, pilot):
        await self.see(pilot, "Acme")
        await pilot.press("enter")
        await self.until(pilot, lambda: self.app.project == "acme")

    def start_run(self):
        return self.daemon.start_run("acme", "build")

    def engine(self, run_id):
        return self.daemon.engine("acme", run_id)

    async def run_screen(self, pilot):
        """A started run, opened in the Run screen."""
        run_id = self.start_run()
        await self.open_acme(pilot)
        await self.see(pilot, f"RUN {run_id}")
        return run_id

    async def backlog_screen(self, pilot):
        run_id = await self.run_screen(pilot)
        (self.engine(run_id).run_dir / "backlog.json").write_text(json.dumps(BACKLOG))
        await pilot.press("k")
        await self.see(pilot, "MVP LINE")
        return run_id

    def merge_gate(self, run_id, unit_id="U-0001"):
        """A unit parked at an L2 merge gate, the state a risky PR reaches."""
        engine = self.engine(run_id)
        engine.units.create({"unit_id": unit_id, "agent": "spgr-agent-backend-developer", "model_tier": "sonnet",
                             "dependencies": [], "declared_paths": [], "expected_outcome": "the session change",
                             "risk_baseline": "L0", "brief": "b", "budget": {"tokens": 1, "wall_clock_seconds": 9999},
                             "role_prompt_ref": "r", "allowlist": [], "mcp_config_ref": None, "cycle_id": "CYCLE-0001",
                             "workstream": None, "input_artifact_refs": [], "executable_check": None})
        state = engine.units.state(unit_id)
        engine.units.save({**state, "state": "gated", "pr": {"number": 9, "branch": "b", "base": "main"}})
        return engine.gates.open(
            "pr-merge", "L2", [unit_id], "Merge PR 9?",
            [{"option": "approve", "consequence": "It merges.", "recommended_because": "Green."},
             {"option": "send_back", "consequence": "A fresh session fixes it."}],
            context={"unit_id": unit_id, "findings": [{"vertical": "spgr-agent-auth", "rule": "R1", "detail": "Sessions expire."}]},
        )["content"]["checkpoint_id"]


class ProjectsScreenTest(TuiCase):
    async def test_list_with_status(self):
        run_id = self.start_run()
        self.merge_gate(run_id)
        async with self.app.run_test(size=self.SIZE) as pilot:
            screen = await self.see(pilot, "Acme", "1 waiting on you")
            self.assertIn("NAME", screen)

    async def test_status_follows_the_daemon_with_no_key_pressed(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.see(pilot, "no run")
            run_id = self.start_run()
            self.merge_gate(run_id)
            await self.see(pilot, "1 waiting on you")

    async def create(self, pilot, path):
        await self.see(pilot, "Acme")
        await pilot.press("n")
        await self.dialog(pilot, FormDialog)
        self.app.screen.query_one("#field-name", Input).value = "Fresh"
        self.app.screen.query_one("#field-path", Input).value = path
        await pilot.press("enter")
        await self.dialog(pilot, ConfirmDialog)
        await pilot.press("y")

    async def test_a_tilde_path_means_the_home_directory(self):
        for typed in ("~/Repos/fresh", "~Repos/fresh"):
            with self.subTest(typed), mock.patch.dict(os.environ, {"HOME": str(self.root / "home-dir")}):
                self.daemon.home.projects_path.write_text(json.dumps(self.daemon.home.projects()))
                projects = self.daemon.home.projects()
                projects.pop("fresh", None)
                self.daemon.home.projects_path.write_text(json.dumps(projects))
                shutil.rmtree(self.root / "home-dir", ignore_errors=True)
                self.app = SpringerApp(self.client, open_url=self.opened.append)
                async with self.app.run_test(size=self.SIZE) as pilot:
                    await self.create(pilot, typed)
                    await self.see(pilot, "Fresh")
                self.assertTrue((self.root / "home-dir" / "Repos" / "fresh" / ".claude").is_dir())

    async def test_a_relative_path_is_relative_to_where_springer_ran(self):
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(self.root)
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.create(pilot, "apps/fresh")
            await self.see(pilot, "Fresh")
        self.assertTrue((self.root / "apps" / "fresh" / ".claude").is_dir())

    async def test_new_open_archive(self):
        target = self.root / "fresh"
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.see(pilot, "Acme")
            await pilot.press("n")
            await self.dialog(pilot, FormDialog)
            self.app.screen.query_one("#field-name", Input).value = "Fresh"
            self.app.screen.query_one("#field-path", Input).value = str(target)
            await pilot.press("enter")
            await self.dialog(pilot, ConfirmDialog)
            await pilot.press("y")
            await self.see(pilot, "Fresh")
            self.assertTrue((target / ".claude").is_dir())
            await pilot.press("down")
            await pilot.pause(0.1)
            await pilot.press("x")
            await self.dialog(pilot, ConfirmDialog)
            await pilot.press("y")
            await self.see(pilot, "archived")
            await pilot.press("up")
            await pilot.pause(0.1)
            await pilot.press("enter")
            await self.see(pilot, "BRIEF acme")


class BriefScreenTest(TuiCase):
    async def test_editor_facts_panel_and_derived_profile(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.open_acme(pilot)
            screen = await self.see(pilot, "BRIEF acme", "✓ Problem", "FACTS", "runs as brochure")
            self.assertNotIn("sentence", screen, "the derived sentence is not a fact")
            self.assertEqual(self.app.query_one("#editor", TextArea).text, GOOD["Problem"])
            await pilot.press("enter")
            await pilot.pause(0.1)
            await pilot.press("end", *" more")
            await pilot.press("ctrl+s")
            await self.until(pilot, lambda: BriefStore(self.project).load()[1]["Problem"].endswith("more"))
            await self.see(pilot, f"v{self.version + 1}")

    async def test_every_section_is_offered_even_when_empty(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.open_acme(pilot)
            await self.see(pilot, "○ Glossary", "○ Constraints", "○ Design preferences")

    async def test_moving_to_another_section_saves_the_one_you_left(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.open_acme(pilot)
            await self.see(pilot, "✓ Problem")
            self.app.query_one("#editor", TextArea).load_text("Edited in place.")
            await pilot.press("down")
            await self.until(pilot, lambda: BriefStore(self.project).load()[1]["Problem"] == "Edited in place.")
            await self.until(pilot, lambda: self.app.query_one("#editor", TextArea).text == GOOD["Users"])

    async def test_facts_edit_recomputes_the_profile(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.open_acme(pilot)
            await self.see(pilot, "runs as brochure")
            await pilot.press("f")
            await self.until(pilot, lambda: self.app.screen.query("#dialog-editor"))
            editor = self.app.screen.query_one("#dialog-editor", TextArea)
            editor.load_text(editor.text + "payments: subscription\n")
            await pilot.press("ctrl+s")
            await self.see(pilot, "runs as saas")

    async def test_narrow_terminal_hides_the_facts_panel_and_keeps_the_editor(self):
        async with self.app.run_test(size=(90, 40)) as pilot:
            await self.open_acme(pilot)
            await self.until(pilot, lambda: self.app.query_one("#editor", TextArea).text)
            self.assertFalse(self.app.query_one("#facts", Static).display)

    async def test_critique(self):
        store = BriefStore(self.project)
        store.update_section("Core flows", "### Bad\nWho: Nobody\nCritical: yes\n", self.version)
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.open_acme(pilot)
            await self.see(pilot, "! Core flows", "! Bad has no outcome.", "Start blocked: 2 error(s)")

    async def test_discovery_proposed_sections_and_go_or_no_go(self):
        store = BriefStore(self.project)
        front, sections = store.load()
        front["proposed"] = ["Users"]
        front["recommendation"] = {"verdict": "go", "summary": "Real pain.", "dismissed": False}
        store._write(front, sections)
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.open_acme(pilot)
            await self.see(pilot, "Discovery says go: Real pain.", "? Users", "Users is still a proposal")
            await pilot.press("down")
            await self.until(pilot, lambda: self.app.query_one("#brief-pane").section == "Users")
            await pilot.press("y")
            await self.see(pilot, "✓ Users")
            await pilot.press("x")
            await self.until(pilot, lambda: "Discovery says" not in self.text())
            await pilot.press("d")
            await self.dialog(pilot, ConfirmDialog)
            await pilot.press("y")
            await self.until(pilot, lambda: any("discovery" in r for r in self.daemon.run_ids("acme")))

    async def test_interview(self):
        """The chat agent is not built, so the line answers that, and the editor keeps
        room for a proposal beside the human's text."""
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.open_acme(pilot)
            await self.see(pilot, "✓ Problem")
            self.assertTrue(self.app.query("#proposal"))
            await pilot.press("slash")
            await pilot.press(*"who is it for", "enter")
            await self.see(pilot, "The chat agent is not built yet.")

    async def test_start_run(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.open_acme(pilot)
            await self.see(pilot, "Ready to start.")
            await pilot.press("s")
            await self.dialog(pilot, ConfirmDialog)
            await self.see(pilot, "Commits the brief")
            await pilot.press("y")
            await self.see(pilot, "RUN acme-1")

    async def test_start_is_refused_with_the_reason_while_an_error_stands(self):
        BriefStore(self.project).update_section("Core flows", "### Bad\nCritical: yes\n", self.version)
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.open_acme(pilot)
            await self.see(pilot, "Start blocked")
            await pilot.press("s")
            await self.dialog(pilot, ConfirmDialog)
            await pilot.press("y")
            await self.see(pilot, "Start is blocked: Bad has no outcome.")
            self.assertEqual(self.daemon.run_ids("acme"), [])

    async def test_provisioning_entry(self):
        run_id = self.start_run()
        (self.engine(run_id).run_dir / "provisioning.json").write_text(json.dumps(
            [{"item_id": "stripe", "secret_name": "STRIPE_KEY", "needed_by": "skeleton"}]))
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.open_acme(pilot)
            await self.see(pilot, f"RUN {run_id}")
            await pilot.press("b")
            await self.see(pilot, "BRIEF acme")
            await pilot.press("v")
            await self.dialog(pilot, FormDialog)
            field = self.app.screen.query_one("#field-value", Input)
            self.assertTrue(field.password, "a secret is masked")
            await pilot.press(*"sk_secret")
            await pilot.pause(0.1)
            self.assertNotIn("sk_secret", self.text())
            await pilot.press("enter")
            await self.until(pilot, lambda: ("acme", "STRIPE_KEY") in self.secrets.values)

    async def test_an_edit_that_lost_a_race_keeps_your_text(self):
        store = BriefStore(self.project)
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.open_acme(pilot)
            await self.see(pilot, "✓ Problem")
            pane = self.app.query_one("#brief-pane")
            self.app.query_one("#editor", TextArea).load_text("Mine.")
            store.update_section("Glossary", "Someone else wrote this.", self.version)
            await pilot.press("ctrl+s")
            await self.see(pilot, "changed elsewhere")
            self.assertEqual(self.app.query_one("#editor", TextArea).text, "Mine.")
            self.assertEqual(pane.version, self.version + 1)
            self.assertEqual(store.load()[1]["Problem"], GOOD["Problem"], "nothing was overwritten")
            await pilot.press("ctrl+s")
            await self.until(pilot, lambda: store.load()[1]["Problem"] == "Mine.")

    async def test_a_refresh_never_overwrites_what_you_are_typing(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.open_acme(pilot)
            await self.see(pilot, "✓ Problem")
            self.app.query_one("#editor", TextArea).load_text("Half a thought")
            self.app.mark_dirty()
            await pilot.pause(0.6)
            self.assertEqual(self.app.query_one("#editor", TextArea).text, "Half a thought")


class BacklogScreenTest(TuiCase):
    async def test_tree_board_graph_mvp_line_and_risk(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.backlog_screen(pilot)
            screen = await self.see(pilot, "E-1 Invoice  critical", "S-1 Draft [wip]", "PR #7", "needs S-1", "unknowns: 1")
            story = next(line for line in screen.splitlines() if "S-2 Send" in line)
            feature = next(line for line in screen.splitlines() if "F-1 Editor" in line)
            self.assertGreater(story.index("S-2"), feature.index("F-1"), "the tree shows its hierarchy")
            self.assertLess(screen.index("F-1 Editor"), screen.index("MVP LINE"))
            self.assertLess(screen.index("MVP LINE"), screen.index("F-2 Reports"))
            await pilot.press("v")
            await self.see(pilot, "view: board", "READY (3)", "IN_REVIEW (0)", "S-2 Send")
            await pilot.press("v")
            await self.see(pilot, "view: graph", "S-3 <- S-1")
            await pilot.press("v")
            await self.see(pilot, "view: tree")

    async def test_before_it_exists_it_says_so(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.run_screen(pilot)
            await pilot.press("k")
            await self.see(pilot, "The backlog is not generated yet.")

    async def select(self, pilot, key):
        pane = self.app.query_one("#backlog-pane")
        table = self.app.query_one("#backlog", DataTable)
        await self.until(pilot, lambda: pane.table_key(table) is not None)
        table.move_cursor(row=table.get_row_index(key))
        await self.until(pilot, lambda: pane.table_key(table) == key)

    async def test_move_line_defer_restore_reorder_add_bug_answer_unknown(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.backlog_screen(pilot)
            await self.select(pilot, "feature:F-2")
            await pilot.press("m")
            await self.dialog(pilot, ConfirmDialog)
            await pilot.press("y")
            await self.until(pilot, lambda: "MVP LINE" not in self.text())
            await pilot.press("d")
            await self.dialog(pilot, ConfirmDialog)
            await pilot.press("y")
            await self.see(pilot, "deferred")
            await pilot.press("d")
            await self.dialog(pilot, ConfirmDialog)
            await pilot.press("y")
            await self.until(pilot, lambda: "deferred" not in self.text())
            await self.select(pilot, "story:S-2")
            await pilot.press("K")
            await self.until(pilot, lambda: self.text().index("S-2 Send") < self.text().index("S-1 Draft"))
            await pilot.press("plus")
            await self.dialog(pilot, FormDialog)
            await pilot.press(*"It broke", "enter")
            await self.see(pilot, "BUG-1 It broke")
            await pilot.press("u")
            await self.dialog(pilot, FormDialog)
            await self.see(pilot, "Which currency?")
            await pilot.press(*"EUR", "enter")
            await self.see(pilot, "unknowns: 0")

    async def test_a_refused_reorder_shows_the_reason(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            run_id = await self.backlog_screen(pilot)
            backlog = json.loads(json.dumps(BACKLOG))
            backlog["epics"][0]["features"][0]["stories"][1]["depends_on"] = ["S-1"]
            (self.engine(run_id).run_dir / "backlog.json").write_text(json.dumps(backlog))
            self.app.mark_dirty()
            await self.see(pilot, "needs S-1")
            await self.select(pilot, "story:S-2")
            await pilot.press("K")
            await self.see(pilot, "depends on S-1")

    async def test_open_the_pr(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.backlog_screen(pilot)
            await self.select(pilot, "story:S-1")
            await pilot.press("o")
            await self.until(pilot, lambda: self.opened == ["http://pr/7"])


class RunScreenTest(TuiCase):
    async def test_phase_and_in_flight_rows(self):
        self.daemon.provider.default.ticks = 5
        async with self.app.run_test(size=self.SIZE) as pilot:
            run_id = await self.run_screen(pilot)
            await self.tick(3)
            await self.see(pilot, "requirements", run_id, "U-0001", "product-manager", "mock-sonnet", "ELAPSED", "LAST TOOL")
            row = re.compile(r"U-0001.*\d+%.*\$0\.\d\d.*(Read|Bash)")
            await self.until(pilot, lambda: row.search(self.text()))

    async def test_live_session_output(self):
        self.daemon.provider.default.ticks = 5
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.run_screen(pilot)
            await self.tick(3)
            await self.see(pilot, "U-0001")
            self.app.query_one("#units", DataTable).focus()
            await pilot.press("enter")
            await self.dialog(pilot, TextDialog)
            await self.see(pilot, "Live output of U-0001", "tool_use: Read")
            await pilot.press("escape")
            await self.until(pilot, lambda: not isinstance(self.app.screen, TextDialog))

    async def test_gate_cards_recommended_first_with_consequences(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            run_id = await self.run_screen(pilot)
            gate_id = self.merge_gate(run_id)
            screen = await self.see(pilot, "WAITING ON YOU (1)", f"{gate_id} L2 pr-merge", "Merge PR 9?",
                                    "auth: Sessions expire. (R1)", "1 approve  It merges. (recommended)",
                                    "2 send_back  A fresh session fixes it.")
            self.assertLess(screen.index("WAITING ON YOU"), screen.index("IN FLIGHT"), "gates come first")

    async def test_no_open_gate_collapses_the_card_area(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.run_screen(pilot)
            screen = await self.see(pilot, "IN FLIGHT")
            self.assertNotIn("WAITING ON YOU", screen)
            self.assertFalse(self.app.query_one("#gates-box").display)

    async def test_a_number_key_answers_the_gate(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            run_id = await self.run_screen(pilot)
            gate_id = self.merge_gate(run_id)
            await self.see(pilot, "1 approve")
            await pilot.press("1")
            await self.until(pilot, lambda: "WAITING ON YOU" not in self.text())
            self.assertEqual(self.engine(run_id).gates.get(gate_id)["content"]["response"]["option"], "approve")

    async def test_tab_moves_between_gates_and_the_number_answers_the_chosen_one(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            run_id = await self.run_screen(pilot)
            first = self.merge_gate(run_id)
            second = self.merge_gate(run_id, "U-0002")
            await self.see(pilot, "WAITING ON YOU (2)", f"› {first}")
            await pilot.press("tab")
            await self.see(pilot, f"› {second}")
            await pilot.press("2")
            await self.until(pilot, lambda: self.engine(run_id).gates.get(second)["content"]["response"])
            self.assertEqual(self.engine(run_id).gates.get(second)["content"]["response"]["option"], "send_back")
            self.assertIsNone(self.engine(run_id).gates.get(first)["content"]["response"])

    async def test_a_gate_with_decisions_asks_each_one(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            run_id = await self.run_screen(pilot)
            gate_id = self.engine(run_id).gates.open(
                "direction-review", "L3", [], "Pick.", [{"option": "accept", "consequence": "Freezes."}],
                decisions=[{"decision_id": "D1", "kind": "question", "prompt": "Which direction?"}])["content"]["checkpoint_id"]
            await self.see(pilot, "decision D1: Which direction?")
            await pilot.press("1")
            await self.dialog(pilot, FormDialog)
            await self.see(pilot, "Which direction?")
            await pilot.press(*"Second", "enter")
            await self.until(pilot, lambda: self.engine(run_id).gates.get(gate_id)["content"]["response"])
            self.assertEqual(self.engine(run_id).gates.get(gate_id)["content"]["decisions"][0]["response"], "Second")

    async def test_answering_with_notes_and_a_rule_change_confirms_first(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            run_id = await self.run_screen(pilot)
            gate_id = self.merge_gate(run_id)
            await self.see(pilot, "n answer with notes")
            await pilot.press("n")
            await self.dialog(pilot, FormDialog)
            self.app.screen.query_one("#field-notes", Input).value = "Fix expiry."
            self.app.screen.query_one("#field-rule_change", Input).value = "Auth tests suffice."
            self.app.screen.query_one("#field-notes", Input).focus()
            await pilot.press("enter")
            await self.dialog(pilot, ConfirmDialog)
            await pilot.press("y")
            await self.until(pilot, lambda: self.engine(run_id).gates.get(gate_id)["content"]["response"])
            response = self.engine(run_id).gates.get(gate_id)["content"]["response"]
            self.assertEqual((response["free_text"], response["rule_change"]), ("Fix expiry.", "Auth tests suffice."))

    async def test_risky_merge_diff(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            run_id = await self.run_screen(pilot)
            self.merge_gate(run_id)
            await self.see(pilot, "d diff")
            await pilot.press("d")
            await self.dialog(pilot, TextDialog)
            await self.see(pilot, "mock diff of PR 9")

    async def test_feed_of_routine_decisions(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            run_id = await self.run_screen(pilot)
            await self.see(pilot, "Nothing new.")
            self.engine(run_id).gates.open("routine-decision", "L1", [], "U-0006 merged at L1",
                                           [{"option": "viewed", "consequence": "Closes."}], digest=True)
            await self.see(pilot, "U-0006 merged at L1")
            self.assertNotIn("WAITING ON YOU", self.text(), "a digest entry is not a pause")
            await pilot.press("v")
            await self.see(pilot, "Nothing new.")

    async def test_cancel_redispatch_pause(self):
        self.daemon.provider.default.ticks = 50
        async with self.app.run_test(size=self.SIZE) as pilot:
            run_id = await self.run_screen(pilot)
            await self.tick(3)
            await self.see(pilot, "U-0001")
            self.app.query_one("#units", DataTable).focus()
            await pilot.press("R")
            await self.dialog(pilot, ConfirmDialog)
            await pilot.press("y")
            await self.until(pilot, lambda: self.engine(run_id).units.state("U-0001")["state"] == "redispatch")
            await self.tick(2)
            await self.until(pilot, lambda: self.engine(run_id).sessions("U-0001").all()[-1]["tier"] == "opus")
            await self.see(pilot, "mock-opus")
            await pilot.press("c")
            await self.dialog(pilot, ConfirmDialog)
            await pilot.press("y")
            await self.until(pilot, lambda: self.engine(run_id).units.state("U-0001")["state"] == "cancelled")
            await pilot.press("P")
            await self.see(pilot, "PAUSED")
            await pilot.press("P")
            await self.until(pilot, lambda: "PAUSED" not in self.text())

    async def test_declining_a_confirmation_changes_nothing(self):
        self.daemon.provider.default.ticks = 50
        async with self.app.run_test(size=self.SIZE) as pilot:
            run_id = await self.run_screen(pilot)
            await self.tick(3)
            await self.see(pilot, "U-0001")
            self.app.query_one("#units", DataTable).focus()
            await pilot.press("c")
            await self.dialog(pilot, ConfirmDialog)
            await pilot.press("n")
            await pilot.pause(0.2)
            self.assertEqual(self.engine(run_id).units.state("U-0001")["state"], "running")

    async def test_waiting_on_usage_window_and_list_price_spend(self):
        self.daemon.provider.signals = [{"used_fraction": 1.0, "resets_at": "2099-01-01T00:00:00Z"}]
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.run_screen(pilot)
            await self.tick()
            await self.see(pilot, "waiting on usage window", "at list price", "window 100%", "daemon parked")

    async def test_design_gate_opens_the_browser(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            run_id = await self.run_screen(pilot)
            self.engine(run_id).gates.open("direction-review", "L3", [], "Pick.",
                                           [{"option": "accept", "consequence": "Freezes."}],
                                           context={"design_session": True})
            await self.see(pilot, "o open in browser")
            await pilot.press("o")
            await self.until(pilot, lambda: self.opened and "/design/acme/?code=" in self.opened[0])


class AllScreensTest(TuiCase):
    async def test_a_refused_read_behind_a_key_is_shown_and_the_app_stays_up(self):
        """A worker that raises would close the whole app."""
        async with self.app.run_test(size=self.SIZE) as pilot:
            run_id = await self.run_screen(pilot)
            gate_id = self.merge_gate(run_id)
            await self.see(pilot, "d diff")
            state = self.engine(run_id).units.state("U-0001")
            self.engine(run_id).units.save({**state, "pr": None})
            await pilot.press("d")
            await self.see(pilot, "U-0001 has no PR")
            self.assertTrue(self.app.is_running)
            await self.see(pilot, gate_id)

    async def test_screens_keep_refreshing_under_an_open_dialog(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            run_id = await self.run_screen(pilot)
            gate_id = self.merge_gate(run_id)
            await self.see(pilot, gate_id)
            await pilot.press("n")
            await self.dialog(pilot, FormDialog)
            other = self.merge_gate(run_id, "U-0002")
            pane = self.app.main.query_one("#run-pane")
            await self.until(pilot, lambda: any(g["checkpoint_id"] == other for g in pane.open_gates))

    async def test_losing_the_daemon_under_an_open_dialog_keeps_the_app_up(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            run_id = await self.run_screen(pilot)
            self.merge_gate(run_id)
            await self.see(pilot, "n answer with notes")
            await pilot.press("n")
            await self.dialog(pilot, FormDialog)
            self.server.should_exit = True
            self.server.force_exit = True
            await asyncio.to_thread(self.thread.join, 5)
            await self.until(pilot, lambda: not self.app.connected, timeout=12)
            self.assertTrue(self.app.is_running)
            self.assertTrue(self.app.main.query_one("#banner").has_class("lost"))
            await pilot.press("escape")
            await self.see(pilot, LOST)

    async def test_a_connection_change_after_the_screen_closed_does_not_raise(self):
        """It runs inside except clauses, where a raise would escape and crash the exit."""
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.see(pilot, "Acme")
            for child in list(self.app.main.children):
                await child.remove()
            self.app._set_connected(False)
            self.app._set_connected(True)

    async def test_a_lost_daemon_behind_a_key_shows_the_banner_and_the_app_stays_up(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.run_screen(pilot)
            self.server.should_exit = True
            self.server.force_exit = True
            await asyncio.to_thread(self.thread.join, 5)
            await pilot.press("o")
            await self.see(pilot, "nothing changed", timeout=12)
            self.assertTrue(self.app.is_running)

    async def test_chat_line(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.see(pilot, "Acme")
            await pilot.press("slash")
            self.assertTrue(self.app.query_one("#chat", Input).has_focus)
            await pilot.press(*"pause", "enter")
            await self.see(pilot, "The chat agent is not built yet.")
            self.assertEqual(self.app.query_one("#chat", Input).value, "")

    async def test_typing_in_the_chat_line_does_not_switch_screens(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.see(pilot, "Acme")
            await pilot.press("slash", *"brk")
            await pilot.pause(0.1)
            self.assertEqual(self.app.query_one("#chat", Input).value, "brk")
            self.assertIn("PROJECTS", self.text())

    async def test_audit_of_applied_operations(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            run_id = await self.run_screen(pilot)
            await pilot.press("P")
            await self.see(pilot, "PAUSED")
            audit = await self.client.get("/v1/audit", project="acme")
            self.assertEqual([(a["type"], a["actor"], a["run_id"]) for a in audit["items"]], [("run.pause", "tui", run_id)])

    async def test_a_lost_daemon_shows_a_banner_and_comes_back(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.see(pilot, "Acme")
            self.assertNotIn(LOST, self.text())
            self.server.should_exit = True
            self.server.force_exit = True
            await asyncio.to_thread(self.thread.join, 5)
            await self.see(pilot, LOST, timeout=12)
            self.assertIn("Acme", self.text(), "the last data stays up")
            self._serve()
            await self.until(pilot, lambda: LOST not in self.text(), timeout=12)

    async def test_screen_keys_switch(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.open_acme(pilot)
            await self.see(pilot, "BRIEF acme")
            await pilot.press("escape", "k")
            await self.see(pilot, "BACKLOG")
            await pilot.press("r")
            await self.see(pilot, "RUN")
            await pilot.press("p")
            await self.see(pilot, "PROJECTS")
            await pilot.press("b")
            await self.see(pilot, "BRIEF acme")


class WholeRunTest(TuiCase):
    async def test_a_person_takes_a_whole_run_from_brief_to_complete_on_the_keyboard(self):
        """The product check for this step: only keys and the screen, and the daemon's
        own tick. The mock provider is behind the API, and nothing here reaches past it."""
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.open_acme(pilot)
            await self.see(pilot, "Ready to start.")
            await pilot.press("s")
            await self.dialog(pilot, ConfirmDialog)
            await pilot.press("y")
            await self.see(pilot, "RUN acme-1")
            answered = set()
            for _ in range(160):
                await self.tick()
                await pilot.pause(0.15)
                screen = self.text()
                if "complete" in screen.splitlines()[1]:
                    break
                match = re.search(r"› (G-\d+) L\d (\S+),", screen)
                if match and match.group(1) not in answered and "1 " in screen:
                    answered.add(match.group(1))
                    await pilot.press("1")
                    if "decision D1" in screen:
                        await self.dialog(pilot, FormDialog)
                        await pilot.press(*"Second", "enter")
                    await self.until(pilot, lambda: not isinstance(self.app.screen, FormDialog))
            else:
                self.fail(f"the run never completed on screen:\n{self.text()}")
            self.assertEqual(len(answered), 3, "a direction review and two risky merges: session, then login")
            self.assertCountEqual(self.host.merged, [1, 2, 3, 4])
            await self.see(pilot, "complete", "at list price")


COVERAGE = {
    ("Projects", "List with status"): (ProjectsScreenTest, "test_list_with_status"),
    ("Projects", "New, open, archive"): (ProjectsScreenTest, "test_new_open_archive"),
    ("Brief", "Editor, facts panel, derived profile"): (BriefScreenTest, "test_editor_facts_panel_and_derived_profile"),
    ("Brief", "Critique"): (BriefScreenTest, "test_critique"),
    ("Brief", "Discovery, proposed sections, go or no-go"): (BriefScreenTest, "test_discovery_proposed_sections_and_go_or_no_go"),
    ("Brief", "Interview"): (BriefScreenTest, "test_interview"),
    ("Brief", "Start run"): (BriefScreenTest, "test_start_run"),
    ("Brief", "Provisioning entry"): (BriefScreenTest, "test_provisioning_entry"),
    ("Backlog", "Tree, board, graph, MVP line, risk tags"): (BacklogScreenTest, "test_tree_board_graph_mvp_line_and_risk"),
    ("Backlog", "Move line, defer, restore, reorder, add bug, answer unknown"):
        (BacklogScreenTest, "test_move_line_defer_restore_reorder_add_bug_answer_unknown"),
    ("Backlog", "Open the PR"): (BacklogScreenTest, "test_open_the_pr"),
    ("Run", "Phase, in-flight rows with agent, model, elapsed, context, cost, last tool"):
        (RunScreenTest, "test_phase_and_in_flight_rows"),
    ("Run", "Live session output"): (RunScreenTest, "test_live_session_output"),
    ("Run", "Gate cards, recommended option first, consequences"):
        (RunScreenTest, "test_gate_cards_recommended_first_with_consequences"),
    ("Run", "Risky merge diff"): (RunScreenTest, "test_risky_merge_diff"),
    ("Run", "Feed of routine decisions"): (RunScreenTest, "test_feed_of_routine_decisions"),
    ("Run", "Cancel, re-dispatch, pause"): (RunScreenTest, "test_cancel_redispatch_pause"),
    ("Run", "Waiting on usage window, list-price spend"): (RunScreenTest, "test_waiting_on_usage_window_and_list_price_spend"),
    ("Run", "Design gate opens the browser"): (RunScreenTest, "test_design_gate_opens_the_browser"),
    ("All", "Chat line"): (AllScreensTest, "test_chat_line"),
    ("All", "Audit of applied operations"): (AllScreensTest, "test_audit_of_applied_operations"),
}


class AcceptanceListTest(unittest.TestCase):
    def table_rows(self):
        text = (REPO / "docs" / "harness" / "api-contract.md").read_text()
        body = text.split("## Screen coverage\n", 1)[1].split("\n## ", 1)[0]
        rows = [line for line in body.splitlines() if line.startswith("|")][2:]
        return {tuple(cell.strip() for cell in row.split("|")[1:3]) for row in rows}

    @unittest.skipUnless(HAVE_TUI, "the TUI dependencies are not installed")
    def test_every_row_of_the_coverage_table_has_a_test(self):
        self.assertEqual(self.table_rows(), set(COVERAGE))
        for row, (case, name) in COVERAGE.items():
            self.assertTrue(hasattr(case, name), f"{row} names a missing test {name}")

    def test_the_tui_reaches_the_daemon_only_through_the_api(self):
        """Contract rule 5, and what lets the real provider slot in with no TUI change."""
        allowed = {"client", "dialogs", "panes", "theme"}
        for path in sorted((REPO / "harness" / "springer_harness" / "tui").glob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom) and node.level:
                    self.assertIn(node.module, allowed, f"{path.name} imports {node.module}")
                    self.assertEqual(node.level, 1, f"{path.name} reaches outside tui/")
                module = getattr(node, "module", None) or ""
                self.assertNotIn("springer_harness", module, path.name)
            self.assertNotRegex(path.read_text(), r"events\.jsonl|run-state\.json|backlog\.json|state\.json", path.name)


if __name__ == "__main__":
    unittest.main()
