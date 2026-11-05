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
    from springer_harness.check.critique import critique, parse_flows, parse_users
    from springer_harness.tui import items
    from springer_harness.tui.dialogs import (NEW_USER, AdoptDialog, ConfirmDialog, FactsDialog, FieldsDialog, FlowDialog,
                                              FormDialog, RunsDialog, SettingsDialog, StartDialog, TextDialog)
    from test_harness_adopt import build_instance
    from textual.widgets import Select

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
                             self.secrets, time.time, local_host=self.host)
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
        await self.see(pilot, f"acme · {run_id}", "in flight")
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

    async def test_a_slow_change_says_it_is_working(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.see(pilot, "Acme")
            real = self.app.client.op

            async def slow(*args, **kwargs):
                await asyncio.sleep(1.5)
                return await real(*args, **kwargs)
            self.app.client.op = slow
            task = asyncio.ensure_future(self.app.apply("project.configure", {"ci_signal": "receipts"}, project="acme",
                                                        busy="Saving the settings.", reviewed=True))
            await self.see(pilot, "Saving the settings.")
            await task
            self.assertEqual(task.result()["status"], "applied")

    async def test_settings_set_the_ci_signal(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.see(pilot, "Acme", "local")
            await pilot.press("e")
            await self.dialog(pilot, SettingsDialog)
            self.app.screen.query_one("#set-ci", Select).value = "both"
            await pilot.press("ctrl+s")
            await self.see(pilot, "needs the github source host")
            self.app.screen.query_one("#set-host", Select).value = "github"
            await pilot.press("ctrl+s")
            await self.dialog(pilot, ConfirmDialog)
            await pilot.press("y")
            await self.see(pilot, "github+both")

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
            await self.see(pilot, "brief  v")


class AdoptedProjectTest(TuiCase):
    async def adopt(self, pilot):
        await self.see(pilot, "Acme")
        await pilot.press("a")
        await self.dialog(pilot, FormDialog)
        self.app.screen.query_one("#field-name", Input).value = "Shop"
        self.app.screen.query_one("#field-path", Input).value = str(self.shop)
        await pilot.press("enter")
        await self.dialog(pilot, AdoptDialog)

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.shop = build_instance(self.root / "instances")
        (self.shop / "docs/design").mkdir(parents=True, exist_ok=True)
        (self.shop / "docs/design/index.html").write_text("<title>Existing directions</title>")

    async def adopted(self, pilot):
        await self.adopt(pilot)
        await pilot.press("y")
        await self.see(pilot, "Shop")
        await self.until(pilot, lambda: "shop" in self.daemon.home.projects())

    async def test_the_adopt_screen_shows_what_it_derives_then_adopts(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.adopt(pilot)
            await self.see(pilot, "kept, edited here: .claude/references/pdca-harness.md",
                           "CLAUDE.md: new rendering in .claude/springer-update/", "Derived facts, which run as small",
                           "pinned rulings: 3", "Problem from the latest confirmed PRD", "Never written: Claude outputs")
            self.assertEqual(self.daemon.home.projects().get("shop"), None, "the review writes nothing")
            await pilot.press("y")
            await self.until(pilot, lambda: "shop" in self.daemon.home.projects())
            self.assertNotIsInstance(self.app.screen, ConfirmDialog, "the review was the confirmation")
            await self.see(pilot, "Shop")
            rows = [r.value for r in self.app.query_one("#projects", DataTable).rows]
            self.app.query_one("#projects", DataTable).move_cursor(row=rows.index("shop"))
            await self.see(pilot, "Merge by hand: .claude/springer-update/CLAUDE.md")

    async def test_start_offers_polish_with_an_issue_and_build_waits_for_a_delta(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.adopted(pilot)
            await pilot.press("down")
            await pilot.press("enter")
            await self.see(pilot, "brief  v")
            await pilot.press("s")
            await self.dialog(pilot, StartDialog)
            await pilot.press("ctrl+b")
            await self.see(pilot, "Describe the change in the brief first")
            self.assertEqual(self.daemon.run_ids("shop"), [])
            await pilot.press("s")
            await self.dialog(pilot, StartDialog)
            self.app.screen.query_one("#start-issue", TextArea).load_text("The footer link opens the wrong address.")
            await pilot.press("ctrl+s")
            await self.dialog(pilot, ConfirmDialog)
            await self.see(pilot, "lane: polish")
            await pilot.press("y")
            await self.until(pilot, lambda: self.daemon.run_ids("shop"))
            run_id = self.daemon.run_ids("shop")[0]
            brief = json.loads((self.shop / "runs" / run_id / "run-brief.json").read_text())["content"]
            self.assertEqual((brief["lane"], brief["issue"]), ("polish", "The footer link opens the wrong address."))
            self.assertEqual(len(brief["pinned_rulings"]), 3)

    async def test_the_design_page_serves_the_existing_mockups(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.adopted(pilot)
            rows = [r.value for r in self.app.query_one("#projects", DataTable).rows]
            self.app.query_one("#projects", DataTable).move_cursor(row=rows.index("shop"))
            await pilot.press("o")
            await self.until(pilot, lambda: self.opened)
            import httpx
            page = await asyncio.to_thread(httpx.get, self.opened[-1], follow_redirects=True)
            self.assertIn("Existing directions", page.text)

    async def test_the_runs_list_shows_imported_history(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.adopted(pilot)
            rows = [r.value for r in self.app.query_one("#projects", DataTable).rows]
            self.app.query_one("#projects", DataTable).move_cursor(row=rows.index("shop"))
            await pilot.press("l")
            await self.dialog(pilot, RunsDialog)
            await self.see(pilot, "second  imported, 1 cycles  complete", "first  imported, 0 cycles")
            await pilot.press("enter")
            await self.dialog(pilot, TextDialog)
            await self.see(pilot, "CYCLE-0001  development  pass -> complete  frontend-developer",
                           "DEF-1 | the heading | accepted", "L-1 (process): Frozen lists help.")


class BriefScreenTest(TuiCase):
    async def test_editor_facts_panel_and_derived_profile(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.open_acme(pilot)
            screen = await self.see(pilot, "brief  v", "✓ Problem", "facts", "runs as brochure",
                                    "What is hard today", GOOD["Problem"], "Why it matters now")
            self.assertNotIn("sentence", screen, "the derived sentence is not a fact")
            await pilot.press("enter", "enter")
            await self.dialog(pilot, FieldsDialog)
            self.app.screen.query_one("#f-why", Input).value = "Tax season is close."
            await pilot.press("ctrl+s")
            await self.until(pilot, lambda: "Why it matters now: Tax season is close." in BriefStore(self.project).load()[1]["Problem"])
            self.assertIn(f"What is hard today: {GOOD['Problem']}", BriefStore(self.project).load()[1]["Problem"])
            await self.see(pilot, f"v{self.version + 1}", "Tax season is close.")
            await pilot.press("t")
            await self.until(pilot, lambda: self.app.query_one("#editor", TextArea).display)
            editor = self.app.query_one("#editor", TextArea)
            editor.move_cursor(editor.document.end)
            await pilot.press(*" More")
            await pilot.press("ctrl+s")
            await self.until(pilot, lambda: BriefStore(self.project).load()[1]["Problem"].endswith("More"))

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
            await self.until(pilot, lambda: self.app.query_one("#brief-pane").section == "Users")
            await self.see(pilot, "Fran  a freelancer", "+ add a user")

    async def test_facts_edit_recomputes_the_profile(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.open_acme(pilot)
            await self.see(pilot, "runs as brochure")
            await pilot.press("f")
            await self.dialog(pilot, FactsDialog)
            await self.see(pilot, "Surfaces", "Payments", "Pinned decisions")
            self.app.screen.query_one("#fact-payments", Select).value = "subscription"
            self.app.screen.query_one("#fact-pinned", TextArea).load_text("db: postgres")
            await pilot.press("ctrl+s")
            await self.see(pilot, "runs as saas", "pinned db postgres")
            front = BriefStore(self.project).load()[0]
            self.assertEqual((front["payments"], front["pinned"], front["surfaces"]), ("subscription", {"db": "postgres"}, ["web"]))

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

    async def test_prose_flows_are_refused_and_kept_beside_the_flows(self):
        store = BriefStore(self.project)
        store.update_section("Core flows", "The user picks a diet, then we search.", self.version)
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.open_acme(pilot)
            await self.see(pilot, "! Core flows", "Start blocked", "press a to add each one")
            self.assertNotIn("Ready to start", self.text())
            self.assertNotIn("### heading", self.text(), "the screen never asks for typed format")
            await self.core_flows(pilot)
            await self.see(pilot, "text that is not a flow yet: The user picks a diet", "+ add a flow")
            store.update_section("Core flows", "", store.load()[0]["brief_version"])
            self.app.mark_dirty()
            await self.see(pilot, "Core flows is required")
            self.assertNotIn("text that is not a flow", self.text())

    async def core_flows(self, pilot):
        await self.see(pilot, "✓ Problem")
        await pilot.press("down", "down")
        await self.until(pilot, lambda: self.app.query_one("#brief-pane").section == "Core flows")
        await self.see(pilot, "+ add a flow")

    async def test_core_flows_and_users_as_fields(self):
        """A flow is added, edited, and removed through a form, and the text it writes is
        what the API parses, so the person never types the format."""
        store = BriefStore(self.project)
        async with self.app.run_test(size=(80, 28)) as pilot:
            await self.open_acme(pilot)
            await self.core_flows(pilot)
            await self.see(pilot, "✓ Send an invoice", "Fran · 1 step · critical")
            await pilot.press("enter")  # from the rail into the list
            await pilot.press("a")
            await self.dialog(pilot, FlowDialog)
            await self.see(pilot, "New flow", "name", "trigger", "outcome", "critical")
            await pilot.press(*"Chase a late invoice", "enter")
            self.assertEqual(self.app.focused.id, "flow-who", "enter moves to the next field")
            self.app.screen.query_one("#flow-who", Select).value = NEW_USER
            await self.dialog(pilot, FormDialog)
            await pilot.press(*"Ada", "enter", *"an accountant", "enter")
            await self.dialog(pilot, FlowDialog)
            self.assertEqual(self.app.screen.query_one("#flow-who", Select).value, "Ada")
            self.app.screen.query_one("#flow-trigger", Input).value = "A due date passes."
            self.app.screen.query_one("#flow-steps", TextArea).load_text("Find the invoice\n\nSend a reminder\n")
            await pilot.press("ctrl+s")
            await self.see(pilot, "! Chase a late invoice", "needs an outcome")
            _, sections = store.load()
            flows = parse_flows(sections["Core flows"])
            self.assertEqual([f["name"] for f in flows], ["Send an invoice", "Chase a late invoice"])
            self.assertEqual(flows[1], {"name": "Chase a late invoice", "steps": 2, "who": "Ada",
                                        "trigger": "A due date passes.", "critical": "no"})
            self.assertEqual(parse_users(sections["Users"]), {"fran", "ada"}, "someone new joins Users")
            await self.see(pilot, "Chase a late invoice has no outcome.")

            await self.until(pilot, lambda: self.app.focused and self.app.focused.id == "items")
            await pilot.press("down")
            await pilot.press("enter")
            await self.dialog(pilot, FlowDialog)
            self.assertEqual(self.app.screen.query_one("#flow-trigger", Input).value, "A due date passes.")
            self.app.screen.query_one("#flow-outcome", Input).value = "The client pays."
            await pilot.press("ctrl+s")
            await self.see(pilot, "✓ Chase a late invoice", "Ready to start.")
            self.assertEqual(critique(*store.load())["errors"], [])

            await pilot.press("delete")
            await self.dialog(pilot, ConfirmDialog)
            await pilot.press("y")
            await self.until(pilot, lambda: "Chase" not in store.load()[1]["Core flows"])
            self.assertIn("### Send an invoice", store.load()[1]["Core flows"], "the other flow stays")

            await pilot.press("t")
            await self.until(pilot, lambda: self.app.query_one("#editor", TextArea).display)
            self.assertIn("Who: Fran", self.app.query_one("#editor", TextArea).text)
            await pilot.press("escape", "t")
            await self.see(pilot, "✓ Send an invoice")

    async def test_a_flow_needs_a_name_and_keys_do_not_leak_behind_the_form(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.open_acme(pilot)
            await self.core_flows(pilot)
            await pilot.press("a")
            await self.dialog(pilot, FlowDialog)
            toggle = self.app.screen.query_one("#flow-critical")
            toggle.focus()
            await pilot.press("p", "q")
            await pilot.pause(0.1)
            self.assertIsInstance(self.app.screen, FlowDialog)
            await pilot.press("space")
            await self.see(pilot, "[x] yes, the product fails without this flow")
            self.assertTrue(toggle.value)
            self.assertEqual(self.app.query_one("#brief-pane").section, "Core flows")
            await pilot.press("ctrl+s")
            await self.see(pilot, "Name the flow first.")
            await pilot.press("escape")
            await self.until(pilot, lambda: not isinstance(self.app.screen, FlowDialog))
            self.assertEqual(BriefStore(self.project).load()[1]["Core flows"].strip(), GOOD["Core flows"].strip())

    async def test_every_section_has_its_fields(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.open_acme(pilot)
            await self.see(pilot, "✓ Problem")
            for section, shown in (("Non-goals", "None yet."), ("Success criteria", "+ add a measure"),
                                   ("Constraints", "+ add a constraint"), ("Design preferences", "Sites or apps you like"),
                                   ("Inputs and references", "+ add a input"), ("Glossary", "+ add a term"),
                                   ("Open questions", "+ add a question")):
                rail = self.app.query_one("#rail", OptionList)
                rail.highlighted = [s["name"] for s in self.app.query_one("#brief-pane").brief["sections"]].index(section)
                await self.until(pilot, lambda: self.app.query_one("#brief-pane").section == section)
                await self.see(pilot, shown)
                self.assertFalse(self.app.query_one("#editor", TextArea).display, section)
            rail.focus()
            await pilot.press("enter", "a")
            await self.dialog(pilot, FieldsDialog)
            await pilot.press(*"Which currency", "enter", *"Fran")
            await pilot.press("ctrl+s")
            await self.until(pilot, lambda: BriefStore(self.project).load()[1]["Open questions"]
                             == "- Which currency\n  Who can answer: Fran")
            await self.see(pilot, "Which currency  who can answer Fran")

    async def test_users_as_fields_and_prose_kept_as_notes(self):
        store = BriefStore(self.project)
        store.update_section("Users", "Anyone who sends invoices.\n- Fran: a freelancer", self.version)
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.open_acme(pilot)
            await self.see(pilot, "✓ Problem")
            await pilot.press("down", "enter")
            await self.see(pilot, "notes: Anyone who sends invoices.", "Fran  a freelancer")
            await pilot.press("a")
            await self.dialog(pilot, FieldsDialog)
            await pilot.press(*"Bo", "enter", *"a bookkeeper")
            await pilot.press("ctrl+s")
            await self.until(pilot, lambda: "- Bo: a bookkeeper" in store.load()[1]["Users"])
            self.assertTrue(store.load()[1]["Users"].startswith("Anyone who sends invoices."))

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
            await self.see(pilot, "acme · acme-1", "in flight")

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
            await self.see(pilot, f"acme · {run_id}", "in flight")
            await pilot.press("b")
            await self.see(pilot, "brief  v")
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
            screen = await self.see(pilot, "E-1 Invoice  critical", "S-1 Draft [wip]", "change #7", "needs S-1", "unknowns: 1")
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
            await self.see(pilot, "requirements", run_id, "U-0001", "product-manager", "mock-sonnet", "TIME", "LAST")
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
            screen = await self.see(pilot, "needs you", f"{gate_id} · L2 merge", "Merge PR 9?",
                                    "auth  Sessions expire. (R1)", "1 approve    It merges.   recommended",
                                    "2 send back  A fresh session fixes it.")
            self.assertLess(screen.index("needs you"), screen.index("in flight"), "gates come first")

    async def test_a_long_question_keeps_its_options_on_a_small_terminal(self):
        async with self.app.run_test(size=(80, 28)) as pilot:
            run_id = await self.run_screen(pilot)
            long = "Why it blocked. " * 120 + "The last sentence."
            self.engine(run_id).gates.open("scope-change", "L3", [], long, [
                {"option": "retry", "consequence": "A fresh session tries again."},
                {"option": "cancel", "consequence": "The unit is cancelled."}])
            self.app.mark_dirty()
            screen = await self.see(pilot, "1 retry", "2 cancel", "full question")
            self.assertNotIn("The last sentence.", screen)
            await pilot.press("f")
            await self.dialog(pilot, TextDialog)
            self.assertTrue(self.app.screen.text.endswith("The last sentence."))

    async def test_no_open_gate_collapses_the_card_area(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.run_screen(pilot)
            screen = await self.see(pilot, "in flight")
            self.assertNotIn("needs you", screen)
            self.assertFalse(self.app.query_one("#gates-box").display)

    async def test_a_number_key_answers_the_gate(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            run_id = await self.run_screen(pilot)
            gate_id = self.merge_gate(run_id)
            await self.see(pilot, "1 approve")
            await pilot.press("1")
            await self.until(pilot, lambda: "needs you" not in self.text())
            self.assertEqual(self.engine(run_id).gates.get(gate_id)["content"]["response"]["option"], "approve")

    async def test_tab_moves_between_gates_and_the_number_answers_the_chosen_one(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            run_id = await self.run_screen(pilot)
            first = self.merge_gate(run_id)
            second = self.merge_gate(run_id, "U-0002")
            await self.see(pilot, "needs you (2)", f"› {first}")
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
            await self.see(pilot, "decision D1  Which direction?")
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
            self.assertNotIn("needs you", self.text(), "a digest entry is not a pause")
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

    async def test_cancelling_the_run_ends_it_and_says_so(self):
        self.daemon.provider.default.ticks = 50
        async with self.app.run_test(size=self.SIZE) as pilot:
            run_id = await self.run_screen(pilot)
            await self.tick(3)
            await self.see(pilot, "U-0001", "X cancel run")
            await pilot.press("X")
            await self.dialog(pilot, ConfirmDialog)
            await self.see(pilot, "Cancels every unfinished unit")
            await pilot.press("y")
            await self.see(pilot, "cancelled", timeout=8)
            self.assertTrue(self.engine(run_id).cycles.is_complete())
            await pilot.press("p")
            await self.see(pilot, "no run")

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

    async def test_quit_is_shown_and_works_from_the_key_and_the_prompt(self):
        for how in ("key", "quit", "exit", "/quit", "EXIT"):
            with self.subTest(how):
                self.app = SpringerApp(self.client, open_url=self.opened.append)
                async with self.app.run_test(size=self.SIZE) as pilot:
                    await self.see(pilot, "q quit")
                    if how == "key":
                        await pilot.press("q")
                    else:
                        await pilot.press("slash", *how, "enter")
                    await self.until(pilot, lambda: self.app._exit)

    async def test_an_80_column_terminal_keeps_the_whole_header(self):
        run_id = self.start_run()
        self.app = SpringerApp(self.client, open_url=self.opened.append)
        async with self.app.run_test(size=(80, 28)) as pilot:
            await self.open_acme(pilot)
            await self.see(pilot, f"acme · {run_id}", "q quit", "X cancel run")

    async def test_typing_a_sentence_with_quit_in_it_does_not_quit(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.see(pilot, "Acme")
            await pilot.press("slash", *"why did it quit", "enter")
            await self.see(pilot, "The chat agent is not built yet.")
            self.assertFalse(self.app._exit)

    async def test_typing_in_the_chat_line_does_not_switch_screens(self):
        async with self.app.run_test(size=self.SIZE) as pilot:
            await self.see(pilot, "Acme")
            await pilot.press("slash", *"brk")
            await pilot.pause(0.1)
            self.assertEqual(self.app.query_one("#chat", Input).value, "brk")
            self.assertIn("NAME", self.text())

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
            await self.see(pilot, "brief  v")
            await pilot.press("escape", "k")
            await self.see(pilot, "No backlog until a run starts.")
            await pilot.press("r")
            await self.see(pilot, "No run yet.")
            await pilot.press("p")
            await self.see(pilot, "NAME")
            await pilot.press("b")
            await self.see(pilot, "brief  v")


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
            await self.see(pilot, "acme · acme-1", "in flight")
            answered = set()
            for _ in range(160):
                await self.tick()
                await pilot.pause(0.15)
                screen = self.text()
                if "complete" in "\n".join(screen.splitlines()[:4]):
                    break
                match = re.search(r"(?:› |needs you   )(G-\d+) ·", screen)
                if match and match.group(1) not in answered and "1 " in screen:
                    answered.add(match.group(1))
                    await pilot.press("1")
                    if "decision D1" in screen:
                        await self.dialog(pilot, FormDialog)
                        await pilot.press(*"Second", "enter")
                    await self.until(pilot, lambda: not isinstance(self.app.screen, FormDialog))
            else:
                self.fail(f"the run never completed on screen:\n{self.text()}")
            self.assertEqual(len(answered), 5, "a standard run: a direction review and a merge gate for each of four PRs")
            self.assertCountEqual(self.host.merged, [1, 2, 3, 4])
            await self.see(pilot, "complete", "at list price")


COVERAGE = {
    ("Projects", "List with status"): (ProjectsScreenTest, "test_list_with_status"),
    ("Projects", "New, open, archive"): (ProjectsScreenTest, "test_new_open_archive"),
    ("Projects", "Adopt an existing instance: derived facts, proposed sections, edited files, the CLAUDE.md merge"):
        (AdoptedProjectTest, "test_the_adopt_screen_shows_what_it_derives_then_adopts"),
    ("Projects", "Start on an adopted project: polish with an issue, or build a delta"):
        (AdoptedProjectTest, "test_start_offers_polish_with_an_issue_and_build_waits_for_a_delta"),
    ("Projects", "Design page serves an existing docs/design/index.html"):
        (AdoptedProjectTest, "test_the_design_page_serves_the_existing_mockups"),
    ("Projects", "Runs list with imported history"): (AdoptedProjectTest, "test_the_runs_list_shows_imported_history"),
    ("Projects", "Source host and CI signal per project"):
        (ProjectsScreenTest, "test_settings_set_the_ci_signal"),
    ("Brief", "Editor, facts panel, derived profile"): (BriefScreenTest, "test_editor_facts_panel_and_derived_profile"),
    ("Brief", "Critique"): (BriefScreenTest, "test_critique"),
    ("Brief", "Every section as fields"): (BriefScreenTest, "test_core_flows_and_users_as_fields"),
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


class ItemsFormatTest(unittest.TestCase):
    """The TUI writes the brief's text, and the API parses it. These hold the two to one format."""

    @unittest.skipUnless(HAVE_TUI, "the TUI dependencies are not installed")
    def test_what_the_form_writes_the_critique_reads(self):
        flow = {**items.blank_flow(), "name": "Pick a diet", "who": "Home cook", "trigger": "First launch.",
                "steps": ["See the diets", " ", "Pick one"], "outcome": "Searches use it.", "critical": True,
                "surface": "web"}
        text = items.write_flows("Kept prose.", [flow])
        self.assertEqual(parse_flows(text), [{"name": "Pick a diet", "steps": 2, "who": "Home cook",
                                              "trigger": "First launch.", "outcome": "Searches use it.",
                                              "critical": "yes", "surface": "web"}])
        self.assertEqual(items.parse_flows(text), ("Kept prose.", [{**flow, "steps": ["See the diets", "Pick one"]}]))
        users = items.write_users("Notes.", [{"name": "Home cook", "about": "cooks on a diet"}, {"name": "Bo", "about": ""}])
        self.assertEqual(parse_users(users), {"home cook", "bo"})
        self.assertEqual(items.parse_users(users)[0], "Notes.")

    def test_a_flow_typed_by_hand_is_read_leniently(self):
        preamble, flows = items.parse_flows("### Diet interview\nwho: end user\nTrigger : new launch\n"
                                            "1) Presents diets\n- Picks one\nCritical: Yes\nsee the mockup\n")
        self.assertEqual(preamble, "")
        self.assertEqual(flows[0]["who"], "end user")
        self.assertEqual(flows[0]["steps"], ["Presents diets", "Picks one"])
        self.assertTrue(flows[0]["critical"])
        self.assertEqual(flows[0]["extra"], ["see the mockup"])
        self.assertEqual(items.missing(flows[0]), ["an outcome"])


class LookTest(unittest.TestCase):
    """Terracotta means this needs you, so it stays a rule and not a preference."""

    @unittest.skipUnless(HAVE_TUI, "the TUI dependencies are not installed")
    def test_terracotta_is_only_painted_on_what_needs_a_person(self):
        allowed = ("waiting on you", "needs you", "› ", "number", "waiting on provisioning", '"?"', "Discovery says",
                   "unknowns", '"L2"', "Merge by hand")
        for name in ("panes.py", "app.py", "theme.py"):
            source = (REPO / "harness" / "springer_harness" / "tui" / name).read_text()
            for line in source.splitlines():
                if re.search(r'"you"', line) and not re.search(r'^(RISK|DARK|LIGHT)|warning=C', line.strip()):
                    self.assertTrue(any(word in line for word in allowed), f"{name}: {line.strip()}")

    @unittest.skipUnless(HAVE_TUI, "the TUI dependencies are not installed")
    def test_the_256_color_palette_is_exact_xterm_colors(self):
        """Anything else gets rounded by the terminal, which is how terracotta became pink."""
        from rich.color import EIGHT_BIT_PALETTE
        from springer_harness.tui import theme
        exact = {"#%02x%02x%02x" % tuple(c) for c in EIGHT_BIT_PALETTE}
        for palette in (theme.DARK_256, theme.LIGHT_256):
            for name, value in palette.items():
                self.assertIn(value, exact, name)
        self.assertEqual(theme.DARK_256.keys(), theme.DARK.keys())
        self.assertEqual(theme.LIGHT_256.keys(), theme.LIGHT.keys())

    @unittest.skipUnless(HAVE_TUI, "the TUI dependencies are not installed")
    def test_every_phase_the_stones_know_is_within_the_arch(self):
        from springer_harness.tui.theme import STONES, STONES_LAID, stones_laid
        self.assertTrue(all(0 <= laid <= STONES for laid in STONES_LAID.values()))
        self.assertEqual(stones_laid("anything", complete=True), STONES)
        self.assertIsNone(stones_laid("a phase nobody named"))

    @unittest.skipUnless(HAVE_TUI, "the TUI dependencies are not installed")
    def test_the_mark_curves_and_the_springers_start_the_curve(self):
        from springer_harness.tui.theme import MARK, MARK_COLORS, mark
        rendered = mark()
        self.assertEqual(len(rendered.plain.splitlines()), 4)
        self.assertIn(MARK_COLORS["T"].lower(), " ".join(str(s.style) for s in rendered.spans).lower())
        first = [next(i for i, ch in enumerate(row) if ch != ".") for row in MARK]
        self.assertEqual(first[:4], sorted(first[:4], reverse=True), "the crown steps out to the springers")
        self.assertEqual(len(set(first[:3])), 3, "a curve, not a flat top")
        rows = [i for i, row in enumerate(MARK) if "T" in row]
        self.assertGreater(min(i for i, row in enumerate(MARK) if "P" in row), max(rows), "springers sit on the piers")
        self.assertTrue(all(row == row[::-1] for row in MARK), "the arch is symmetric")


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
        allowed = {"client", "dialogs", "items", "panes", "theme"}
        for path in sorted((REPO / "harness" / "springer_harness" / "tui").glob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom) and node.level:
                    for name in ([a.name for a in node.names] if node.module is None else [node.module]):
                        self.assertIn(name, allowed, f"{path.name} imports {name}")
                    self.assertIn(node.module or node.names[0].name, allowed, f"{path.name} imports {node.module}")
                    self.assertEqual(node.level, 1, f"{path.name} reaches outside tui/")
                module = getattr(node, "module", None) or ""
                self.assertNotIn("springer_harness", module, path.name)
            self.assertNotRegex(path.read_text(), r"events\.jsonl|run-state\.json|backlog\.json|state\.json", path.name)


if __name__ == "__main__":
    unittest.main()
