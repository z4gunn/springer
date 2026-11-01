"""The four screens. Each pane fetches through the client and renders. Nothing here
holds state a refetch would not rebuild, so a pane cannot drift from the daemon."""

import time

import yaml
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, OptionList, Static, TextArea
from textual.widgets.option_list import Option

from .client import ApiError, run_path
from .dialogs import EditDialog, FormDialog, TextDialog

COLUMNS = ("ready", "in_progress", "in_review", "blocked", "done")
TIERS = ("haiku", "sonnet", "opus")
VIEWS = ("tree", "board", "graph")


def status_of(project):
    """One line a person reads: what, if anything, this project needs from them."""
    run = project["active_run"]
    if project["archived"]:
        return "archived"
    if run is None:
        return "no run"
    if run["externally_held"]:
        return "held by another session"
    if run["paused"]:
        return "paused"
    if run["open_gates"]:
        return f"{run['open_gates']} waiting on you"
    if run["waiting_on"] == "usage_window":
        return "waiting on usage window"
    if run["waiting_on"] == "provisioning":
        return "waiting on provisioning"
    return "running"


def age(iso_text):
    seconds = max(0, int(time.time() - time.mktime(time.strptime(iso_text, "%Y-%m-%dT%H:%M:%SZ")) + time.timezone))
    return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m" if seconds >= 3600 else f"{seconds // 60}m"


class Pane(Vertical):
    """A screen of the app. load() fetches and renders, and is safe to call any time."""

    focus_id = None

    @property
    def client(self):
        return self.app.client

    async def load(self):
        raise NotImplementedError

    def focus_main(self):
        if self.focus_id:
            self.query_one(self.focus_id).focus()

    def table_key(self, table):
        if not table.row_count:
            return None
        return table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value

    def fill(self, table, rows):
        """Replace the rows and keep the cursor on the same key if it is still there.
        Cells go in as Text, so a title with a bracket is not read as markup and a
        tree's indent survives."""
        current = self.table_key(table)
        table.clear()
        for key, cells in rows:
            table.add_row(*(Text(cell) for cell in cells), key=key)
        keys = [key for key, _ in rows]
        if current in keys:
            table.move_cursor(row=keys.index(current))


class ProjectsPane(Pane):
    focus_id = "#projects"
    BINDINGS = [Binding("n", "new", "new"), Binding("a", "adopt", "adopt"), Binding("x", "archive", "archive")]

    def compose(self) -> ComposeResult:
        yield Static("PROJECTS", classes="title")
        yield DataTable(id="projects", cursor_type="row", zebra_stripes=False)
        yield Static("n new   a adopt   enter open   x archive", classes="hint")

    def on_mount(self):
        self.query_one("#projects", DataTable).add_columns("NAME", "PROFILE", "PHASE", "GATES", "IN FLIGHT", "STATUS")

    async def load(self):
        projects = await self.client.get("/v1/projects")
        rows = []
        for project in projects:
            run = project["active_run"]
            rows.append((project["slug"], (project["name"], project["profile"] or "-", run["phase"] if run else "-",
                                           str(run["open_gates"]) if run else "0",
                                           str(run["in_flight"]) if run else "0", status_of(project))))
        self.fill(self.query_one("#projects", DataTable), rows)

    def on_data_table_row_selected(self, event):
        self.app.spawn(self.app.open_project(event.row_key.value))

    def action_new(self):
        self.app.spawn(self._create("new"))

    def action_adopt(self):
        self.app.spawn(self._create("adopt"))

    async def _create(self, mode):
        title = "New project" if mode == "new" else "Adopt an existing repository"
        form = await self.app.push_screen_wait(FormDialog(title, {"name": "", "path": ""}))
        if form:
            await self.app.apply("project.create", {**form, "mode": mode})

    def action_archive(self):
        slug = self.table_key(self.query_one("#projects", DataTable))
        if slug:
            self.app.spawn(self.app.apply("project.archive", project=slug))


class BriefPane(Pane):
    focus_id = "#rail"
    BINDINGS = [Binding("c", "check", "check"), Binding("s", "start", "start"), Binding("f", "facts", "facts"),
                Binding("d", "discovery", "discovery"), Binding("y", "confirm_section", "confirm"),
                Binding("v", "provisioning", "provisioning"), Binding("x", "dismiss_recommendation", "dismiss"),
                Binding("ctrl+s", "save", "save", priority=True), Binding("escape", "to_rail", "sections")]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.brief = None
        self.section = None
        self.loaded_body = ""
        self.version = None

    def compose(self) -> ComposeResult:
        yield Static("BRIEF", id="brief-title", classes="title")
        yield Static("", id="recommendation", markup=False)
        with Horizontal(id="brief-main"):
            yield OptionList(id="rail")
            with Vertical(id="brief-editor"):
                yield TextArea(id="editor")
                # The interview's proposals land here beside the human's text, to accept,
                # edit, or drop. The interview itself is built after the TUI.
                yield Static("", id="proposal", markup=False)
            yield Static("", id="facts", markup=False)
        yield Static("", id="critique", markup=False)
        yield Static("enter edit   esc sections   ctrl+s save   c check   s start   f facts   d discover   "
                     "y confirm   v provide", classes="hint")

    def _dirty(self):
        return self.section is not None and self.query_one("#editor", TextArea).text != self.loaded_body

    async def load(self):
        slug = self.app.project
        if slug is None:
            self.query_one("#brief-title", Static).update("BRIEF  open a project first")
            return
        self.brief = await self.client.get(f"/v1/projects/{slug}/brief")
        critique = await self.client.get(f"/v1/projects/{slug}/brief/critique")
        # While the human has unsaved text, base_version stays what that text was based
        # on. Moving it forward here would let a save overwrite someone else's edit.
        if not self._dirty():
            self.version = self.brief["version"]
        self._render_brief(critique)

    def _render_brief(self, critique):
        name = self.app.project
        self.query_one("#brief-title", Static).update(f"BRIEF {name}  v{self.brief['version']}")
        errored = {e["section"] for e in critique["errors"]}
        warned = {e["section"] for e in critique["warnings"]}

        def mark(section):
            if section["confidence"] == "proposed":
                return "??"
            if section["name"] in errored:
                return "!!"
            if section["name"] in warned:
                return ".."
            return "ok" if section["body"] else "--"

        rail = self.query_one("#rail", OptionList)
        highlighted = rail.highlighted
        rail.clear_options()
        rail.add_options([Option(f"{mark(s)} {s['name']}", id=s["name"]) for s in self.brief["sections"]])
        if self.brief["sections"]:
            rail.highlighted = highlighted if highlighted is not None else 0
        facts = self.brief["facts"]
        lines = [f"{k} {', '.join(map(str, v)) if isinstance(v, list) else v}" for k, v in facts.items()
                 if k not in ("pinned", "budget")]
        lines += [f"pinned {k}: {v}" for k, v in (facts.get("pinned") or {}).items()]
        self.query_one("#facts", Static).update("FACTS\n" + "\n".join(lines) + "\n\n" + self.brief["derived"]["sentence"])
        recommendation = self.brief["recommendation"]
        self.query_one("#recommendation", Static).update(
            f"Discovery says {recommendation['verdict']}: {recommendation['summary']}   x dismiss"
            if recommendation and not recommendation.get("dismissed") else "")
        notes = [f"!! {e['message']}" for e in critique["errors"]] + [f".. {w['message']}" for w in critique["warnings"]]
        notes += [f"i  {i['message']}" for i in critique["info"]]
        if critique["errors"]:
            notes.append(f"Start blocked: {len(critique['errors'])} error(s)")
        elif not self.brief["started"]:
            notes.append("Ready to start.")
        else:
            notes.append("The run has started. An edit opens a scope-change gate.")
        self.query_one("#critique", Static).update("\n".join(notes))
        self._show_section()

    def _show_section(self):
        """Refill the editor from the section, never over text the human is typing."""
        if not self.brief or self._dirty():
            return
        rail = self.query_one("#rail", OptionList)
        if rail.highlighted is None or not self.brief["sections"]:
            return
        section = self.brief["sections"][rail.highlighted]
        editor = self.query_one("#editor", TextArea)
        if self.section != section["name"] or editor.text != section["body"]:
            self.section = section["name"]
            self.loaded_body = section["body"]
            editor.load_text(section["body"])

    def on_option_list_option_highlighted(self, event):
        if self.brief is None or event.option.id == self.section:
            return
        if self._dirty():
            self.app.spawn(self._save_then_show())
        else:
            self._show_section()

    async def _save_then_show(self):
        await self._save()
        self._show_section()

    def on_option_list_option_selected(self):
        self.query_one("#editor", TextArea).focus()

    async def _save(self):
        if not self._dirty():
            return
        text = self.query_one("#editor", TextArea).text
        args = {"section": self.section, "body": text, "base_version": self.version}
        try:
            outcome = await self.app.apply("brief.update_section", args, project=self.app.project, reraise=True)
        except ApiError as exc:
            if exc.code == "stale_version":
                self.version = exc.details["current_version"]
                self.app.notify(f"The brief changed elsewhere, now v{self.version}. Your text is kept. "
                                "Save again to write over it.", severity="warning")
                return
            self.app.notify(exc.message, severity="error")
            return
        if outcome:
            self.loaded_body = text
            await self.load()

    def action_save(self):
        self.app.spawn(self._save())

    def action_to_rail(self):
        self.query_one("#rail", OptionList).focus()

    def action_check(self):
        self.app.mark_dirty()
        self.app.notify("Checked.")

    def action_start(self):
        self.app.spawn(self._start())

    async def _start(self):
        await self._save()
        outcome = await self.app.apply("run.start", {"base_version": self.version}, project=self.app.project)
        if outcome and outcome.get("result", {}).get("run_id"):
            self.app.select_run(outcome["result"]["run_id"])
            self.app.show("run")

    def action_facts(self):
        self.app.spawn(self._facts())

    async def _facts(self):
        text = await self.app.push_screen_wait(EditDialog("Facts", yaml.safe_dump(self.brief["facts"], sort_keys=False)))
        if text is None:
            return
        try:
            facts = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            self.app.notify(f"That is not valid YAML: {exc}", severity="error")
            return
        await self.app.apply("brief.update_facts", {"facts": facts, "base_version": self.version},
                             project=self.app.project)

    def action_discovery(self):
        self.app.spawn(self.app.apply("brief.run_discovery", {"sections": [self.section] if self.section else "all"},
                                           project=self.app.project))

    def action_confirm_section(self):
        if self.section:
            self.app.spawn(self.app.apply("brief.confirm_section",
                                               {"section": self.section, "base_version": self.version},
                                               project=self.app.project))

    def action_dismiss_recommendation(self):
        self.app.spawn(self.app.apply("brief.dismiss_recommendation", project=self.app.project))

    def action_provisioning(self):
        self.app.spawn(self._provisioning())

    async def _provisioning(self):
        items = await self.client.get(f"/v1/projects/{self.app.project}/provisioning")
        missing = [i for i in items if not i["present"]]
        if not missing:
            self.app.notify("Nothing is waiting to be provided.")
            return
        item = missing[0]
        form = await self.app.push_screen_wait(FormDialog(f"Provide {item['secret_name']}", {"value": ""},
                                                          masked=("value",)))
        if form and form["value"]:
            await self.app.apply("provisioning.set_secret", {"item_id": item["item_id"], "value": form["value"]},
                                 project=self.app.project)

    def on_resize(self, event):
        self.query_one("#facts", Static).display = event.size.width >= 100


class BacklogPane(Pane):
    focus_id = "#backlog"
    can_focus = True  # holds the keys while the table is hidden in board and graph view
    BINDINGS = [Binding("v", "view", "view"), Binding("m", "move_line", "move line"), Binding("d", "defer", "defer"),
                Binding("J", "down", "later"), Binding("K", "up", "earlier"), Binding("plus", "add_bug", "add bug"),
                Binding("u", "unknown", "unknowns"), Binding("o", "open_pr", "open PR"),
                Binding("space", "toggle", "fold")]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.view_name = "tree"
        self.data = None
        self.folded = set()

    def compose(self) -> ComposeResult:
        yield Static("BACKLOG", id="backlog-title", classes="title")
        yield DataTable(id="backlog", cursor_type="row", show_header=False)
        yield Static("", id="board", markup=False)
        yield Static("v view   space fold   m move line here   d defer/restore   J/K reorder   + add bug   "
                     "u unknowns   o open PR", classes="hint")

    def on_mount(self):
        self.query_one("#backlog", DataTable).add_columns("ITEM", "COLUMN", "RISK", "WAVE", "NOTE")

    async def load(self):
        if not self.app.run_id:
            self.query_one("#backlog-title", Static).update("BACKLOG  no run yet")
            return
        self.data = await self.client.get(run_path(self.app.project, self.app.run_id) + "/backlog")
        unanswered = sum(1 for u in self.data["unknowns"] if u["answer"] is None)
        self.query_one("#backlog-title", Static).update(
            f"BACKLOG {self.app.run_id}   view: {self.view_name}   unknowns: {unanswered}")
        table = self.query_one("#backlog", DataTable)
        board = self.query_one("#board", Static)
        table.display = self.view_name == "tree"
        board.display = self.view_name != "tree"
        if self.data["state"] == "not_generated":
            self.fill(table, [("empty", ("The backlog is not generated yet.", "", "", "", ""))])
            board.update("The backlog is not generated yet.")
        elif self.view_name == "tree":
            self.fill(table, self._tree_rows())
        elif self.view_name == "board":
            board.update(self._board_text())
        else:
            board.update(self._graph_text())

    def _features(self):
        return [f for epic in self.data["epics"] for f in epic["features"]]

    def _stories(self):
        return [s for f in self._features() for s in f["stories"]]

    def _tree_rows(self):
        rows, line_drawn = [], False
        for epic in self.data["epics"]:
            critical = "  critical" if epic.get("critical") else ""
            rows.append((f"epic:{epic['epic_id']}", (f"{epic['epic_id']} {epic['title']}{critical}", "", "", "", "")))
            for feature in epic["features"]:
                if not feature["mvp"] and not line_drawn:
                    rows.append(("line", ("=" * 12 + " MVP LINE " + "=" * 12, "", "", "", "")))
                    line_drawn = True
                fold = ">" if feature["feature_id"] in self.folded else "v"
                rows.append((f"feature:{feature['feature_id']}",
                             (f"  {fold} {feature['feature_id']} {feature['title']}", "", "", "",
                              "deferred" if feature["deferred"] else "")))
                if feature["feature_id"] in self.folded:
                    continue
                for story in feature["stories"]:
                    pr = story.get("pr") or {}
                    deps = ", ".join(story.get("depends_on", []))
                    note = " ".join(x for x in (f"PR #{pr['number']}" if pr else "", f"needs {deps}" if deps else "") if x)
                    rows.append((f"story:{story['story_id']}",
                                 (f"      {story['story_id']} {story['title']}", story.get("column") or "",
                                  story.get("risk") or "", "" if story.get("wave") is None else f"wave {story['wave']}",
                                  note)))
        return rows

    def _board_text(self):
        lines = []
        for column in COLUMNS:
            stories = [s for s in self._stories() if s.get("column") == column]
            lines.append(f"{column.upper()} ({len(stories)})")
            lines += [f"  {s['story_id']} {s['title']}  {s.get('risk') or ''}".rstrip() for s in stories]
            lines.append("")
        return "\n".join(lines)

    def _graph_text(self):
        lines = [f"{s['story_id']} <- {', '.join(s['depends_on'])}" for s in self._stories() if s.get("depends_on")]
        return "DEPENDENCIES\n" + ("\n".join(lines) if lines else "None.")

    def _selected(self, kind):
        key = self.table_key(self.query_one("#backlog", DataTable))
        if key and key.startswith(f"{kind}:"):
            return key.split(":", 1)[1]
        return None

    def _op(self, kind, args=None):
        self.app.spawn(self.app.apply(kind, args, project=self.app.project, run_id=self.app.run_id))

    def action_view(self):
        self.view_name = VIEWS[(VIEWS.index(self.view_name) + 1) % len(VIEWS)]
        self.query_one("#backlog", DataTable).display = self.view_name == "tree"
        self.query_one("#board", Static).display = self.view_name != "tree"
        self.focus_main()
        self.app.mark_dirty()

    def focus_main(self):
        if self.view_name == "tree":
            super().focus_main()
        else:
            self.focus()

    def action_toggle(self):
        feature = self._selected("feature")
        if feature:
            self.folded ^= {feature}
            self.app.mark_dirty()

    def _story_feature(self):
        """The feature a selected story sits in, so a key works from any row beneath it."""
        story = self._selected("story")
        for feature in self._features():
            if any(s["story_id"] == story for s in feature["stories"]):
                return feature["feature_id"]
        return self._selected("feature")

    def action_move_line(self):
        feature = self._story_feature()
        if feature:
            self._op("backlog.move_mvp_line", {"after_feature_id": feature})

    def action_defer(self):
        feature_id = self._story_feature()
        if feature_id:
            feature = next(f for f in self._features() if f["feature_id"] == feature_id)
            self._op("backlog.restore_feature" if feature["deferred"] else "backlog.defer_feature",
                     {"feature_id": feature_id})

    def _move(self, delta):
        story_id = self._selected("story")
        if not story_id:
            return
        for feature in self._features():
            story = next((s for s in feature["stories"] if s["story_id"] == story_id), None)
            if story:
                wave = [s["story_id"] for s in feature["stories"] if s.get("wave") == story.get("wave")]
                self._op("backlog.reorder", {"story_id": story_id, "position": max(0, wave.index(story_id) + delta)})

    def action_down(self):
        self._move(1)

    def action_up(self):
        self._move(-1)

    def action_add_bug(self):
        self.app.spawn(self._add_bug())

    async def _add_bug(self):
        form = await self.app.push_screen_wait(FormDialog("Add a bug", {"title": "", "description": ""}))
        if form and form["title"]:
            await self.app.apply("backlog.add_bug", form, project=self.app.project, run_id=self.app.run_id)

    def action_unknown(self):
        self.app.spawn(self._unknown())

    async def _unknown(self):
        waiting = [u for u in (self.data or {}).get("unknowns", []) if u["answer"] is None]
        if not waiting:
            self.app.notify("No unknowns are waiting.")
            return
        form = await self.app.push_screen_wait(FormDialog(waiting[0]["question"], {"answer": ""}))
        if form and form["answer"]:
            await self.app.apply("backlog.answer_unknown", {"unknown_id": waiting[0]["unknown_id"], "answer": form["answer"]},
                                 project=self.app.project, run_id=self.app.run_id)

    def action_open_pr(self):
        story_id = self._selected("story")
        story = next((s for s in self._stories() if s["story_id"] == story_id), None)
        pr = (story or {}).get("pr") or {}
        if pr.get("url"):
            self.app.open_url(pr["url"])
        else:
            self.app.notify("This item has no PR link.")


class RunPane(Pane):
    focus_id = "#units"
    BINDINGS = [*(Binding(str(n), f"answer({n})", show=False) for n in range(1, 10)),
                Binding("tab", "next_gate", "next gate", priority=False), Binding("d", "diff", "diff"),
                Binding("o", "design", "design"), Binding("n", "notes", "answer with notes"),
                Binding("P", "pause", "pause"), Binding("c", "cancel_unit", "cancel"),
                Binding("R", "redispatch", "re-dispatch"), Binding("v", "viewed", "clear routine")]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.run = None
        self.open_gates = []
        self.digest = []
        self.selected_gate = 0

    def compose(self) -> ComposeResult:
        yield Static("RUN", id="run-title", classes="title")
        yield VerticalScroll(Static("", id="gates", markup=False), id="gates-box")
        yield Static("IN FLIGHT                                                           P pause", classes="section")
        yield DataTable(id="units", cursor_type="row")
        yield Static("c cancel   R re-dispatch one tier up   enter live output", classes="hint")
        yield Static("", id="routine", markup=False)

    def on_mount(self):
        self.query_one("#units", DataTable).add_columns("UNIT", "AGENT", "MODEL", "ELAPSED", "CONTEXT", "COST", "LAST TOOL")

    def _path(self):
        return run_path(self.app.project, self.app.run_id)

    async def load(self):
        if not self.app.run_id:
            self.query_one("#run-title", Static).update("RUN  no run yet. Start one from the brief.")
            return
        path = self._path()
        self.run = await self.client.get(path)
        self.open_gates = (await self.client.get(path + "/gates", state="open", digest="false"))["items"]
        self.digest = (await self.client.get(path + "/gates", state="open", digest="true"))["items"]
        metrics = await self.client.get(path + "/metrics")
        self.selected_gate = min(self.selected_gate, max(0, len(self.open_gates) - 1))
        self._render_run(metrics)

    def _render_run(self, metrics):
        run = self.run
        flags = []
        if run.get("complete"):
            flags.append("complete")
        if run["paused"]:
            flags.append("PAUSED")
        if run["waiting_on"] == "usage_window":
            flags.append("waiting on usage window")
        elif run["waiting_on"] == "provisioning":
            flags.append("waiting on provisioning")
        counts = ", ".join(f"{count} {state}" for state, count in sorted(run["units"].items()))
        self.query_one("#run-title", Static).update(
            f"RUN {self.app.run_id}  {run['active_phase']}  {'  '.join(flags)}   {counts}   "
            f"${metrics['list_price_spend_usd']:.2f} at list price")
        self.query_one("#gates-box").display = bool(self.open_gates)
        self.query_one("#gates", Static).update(self._gates_text())
        rows = []
        for row in run["in_flight"]:
            context = "" if row.get("context_percent") is None else f"{row['context_percent']:.0f}%"
            rows.append((f"{row['unit_id']}/{row['session_id']}",
                         (row["unit_id"], row["agent"].removeprefix("spgr-agent-"), row["model"], age(row["started_at"]),
                          context, f"${row.get('cost') or 0:.2f}", row.get("last_tool_call") or "")))
        self.fill(self.query_one("#units", DataTable), rows)
        lines = [f"  {g['decision_prompt']}" for g in self.digest]
        self.query_one("#routine", Static).update(
            "ROUTINE (since you looked)   v clear\n" + ("\n".join(lines) if lines else "  Nothing new."))

    def _gates_text(self):
        if not self.open_gates:
            return ""
        lines = [f"WAITING ON YOU ({len(self.open_gates)})" + ("   tab next" if len(self.open_gates) > 1 else "")]
        for index, gate in enumerate(self.open_gates):
            mark = ">" if index == self.selected_gate else " "
            context = gate["context"]
            lines.append(f"{mark} {gate['checkpoint_id']} {gate['level']} {gate['checkpoint_type']}, "
                         f"age {context['age_seconds'] // 60}m")
            lines.append(f"  {gate['decision_prompt']}")
            lines += [f"  {f.get('vertical', '').removeprefix('spgr-agent-')}: {f.get('detail', '')} ({f.get('rule', '')})"
                      for f in context.get("findings", [])]
            if index == self.selected_gate:
                for number, option in enumerate(gate["options"], 1):
                    recommended = " (recommended)" if option.get("recommended_because") else ""
                    lines.append(f"  {number} {option['option']}  {option['consequence']}{recommended}")
                for decision in gate.get("decisions", []):
                    lines.append(f"  decision {decision['decision_id']}: {decision['prompt']}")
                keys = ["n answer with notes"]
                if context.get("diff_path"):
                    keys.append("d diff")
                if context.get("design_session"):
                    keys.append("o open in browser")
                lines.append("  " + "   ".join(keys))
        return "\n".join(lines)

    def _gate(self):
        return self.open_gates[self.selected_gate] if self.open_gates else None

    def action_next_gate(self):
        if self.open_gates:
            self.selected_gate = (self.selected_gate + 1) % len(self.open_gates)
            self.query_one("#gates", Static).update(self._gates_text())

    def action_answer(self, number):
        gate = self._gate()
        if gate and number <= len(gate["options"]):
            option = gate["options"][number - 1]["option"]
            self.app.spawn(self._answer(gate, option))

    async def _answer(self, gate, option, free_text=None, rule_change=None):
        decisions = []
        for decision in gate.get("decisions", []):
            form = await self.app.push_screen_wait(FormDialog(decision["prompt"], {"answer": ""}))
            if form is None:
                return
            decisions.append({"decision_id": decision["decision_id"], "response": form["answer"]})
        args = {"gate_id": gate["checkpoint_id"], "option": option, "decisions": decisions}
        if free_text:
            args["free_text"] = free_text
        if rule_change:
            args["rule_change"] = rule_change
        await self.app.apply("gate.answer", args, project=self.app.project, run_id=self.app.run_id)

    def action_notes(self):
        self.app.spawn(self._notes())

    async def _notes(self):
        gate = self._gate()
        if not gate:
            return
        names = ", ".join(o["option"] for o in gate["options"])
        form = await self.app.push_screen_wait(FormDialog(
            f"Answer {gate['checkpoint_id']}", {"option": gate["options"][0]["option"], "notes": "", "rule_change": ""}))
        if form is None:
            return
        if form["option"] not in names.split(", "):
            self.app.notify(f"Choose one of: {names}", severity="error")
            return
        await self._answer(gate, form["option"], form["notes"] or None, form["rule_change"] or None)

    def action_diff(self):
        gate = self._gate()
        path = gate and gate["context"].get("diff_path")
        if path:
            self.app.spawn(self._diff(gate["checkpoint_id"], path))

    async def _diff(self, title, path):
        await self.app.push_screen_wait(TextDialog(f"Diff for {title}", await self.client.get_text(path)))

    def action_design(self):
        if self.app.project:
            self.app.spawn(self.app.open_design())

    def action_pause(self):
        kind = "run.resume" if self.run and self.run["paused"] else "run.pause"
        self._op(kind)

    def _op(self, kind, args=None):
        if self.app.run_id:
            self.app.spawn(self.app.apply(kind, args, project=self.app.project, run_id=self.app.run_id))

    def _unit_row(self):
        key = self.table_key(self.query_one("#units", DataTable))
        return key.split("/") if key else (None, None)

    def action_cancel_unit(self):
        unit_id, _ = self._unit_row()
        if unit_id:
            self._op("unit.cancel", {"unit_id": unit_id})

    def action_redispatch(self):
        unit_id, _ = self._unit_row()
        if unit_id:
            self.app.spawn(self._redispatch(unit_id))

    async def _redispatch(self, unit_id):
        unit = await self.client.get(f"{self._path()}/units/{unit_id}")
        tier = unit["sessions"][-1]["tier"] if unit["sessions"] else unit["spec"]["model_tier"]
        higher = TIERS[min(TIERS.index(tier) + 1, len(TIERS) - 1)]
        await self.app.apply("unit.redispatch", {"unit_id": unit_id, "model_tier": higher}, project=self.app.project,
                             run_id=self.app.run_id)

    def action_viewed(self):
        if self.digest:
            self._op("digest.mark_viewed", {"gate_ids": [g["checkpoint_id"] for g in self.digest]})

    def on_data_table_row_selected(self, event):
        unit_id, session_id = event.row_key.value.split("/")
        self.app.spawn(self._live(unit_id, session_id))

    async def _live(self, unit_id, session_id):
        dialog = TextDialog(f"Live output of {unit_id} {session_id}")
        self.app.push_screen(dialog)
        path = f"{self._path()}/units/{unit_id}/sessions/{session_id}/stream"
        async for _, data, _ in self.client.stream(path):
            if not dialog.is_attached:
                return
            dialog.append(f"{data.get('type')}: {data.get('name', '')}")
