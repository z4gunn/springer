"""The four screens. Each pane fetches through the client and renders. Nothing here
holds state a refetch would not rebuild, so a pane cannot drift from the daemon."""

import os
import time

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, OptionList, Static, TextArea
from textual.widgets.option_list import Option

from .client import ApiError, run_path
from . import items
from .dialogs import (AdoptDialog, ConfirmDialog, EditDialog, FactsDialog, FieldsDialog, FlowDialog, FormDialog,
                      RunsDialog, SettingsDialog, StartDialog, TextDialog, imported_text)
from .theme import COLUMN, RISK, join, keys, lines, paint

# Shown in an empty section, and never saved: the format these sections must take. They
# are the API's to enforce, and these copies only show the shape.
SECTION_TEMPLATES = {
    "Core flows": "### Name of the flow\nWho: A name from Users\nTrigger: What starts it.\n1. First step\n2. Next step\n"
                  "Outcome: How they know it worked.\nCritical: yes",
    "Users": "- Name: who they are and what they want",
}
# The API's message for a rule, said the way this screen fixes it.
SCREEN_MESSAGES = {"flows-not-structured": "Core flows has text but no flow yet. Open Core flows and press a to add each one."}
COLUMNS = ("ready", "in_progress", "in_review", "blocked", "done")
TIERS = ("haiku", "sonnet", "opus")
VIEWS = ("tree", "board", "graph")


def status_of(project):
    """One line a person reads: what, if anything, this project needs from them."""
    run = project["active_run"]
    if project["archived"]:
        return paint("archived", "dim")
    if run is None:
        return paint("no run", "dim")
    if run["externally_held"]:
        return paint("● held by another session", "error")
    if run["paused"]:
        return paint("● paused", "dim")
    if run["open_gates"]:
        return paint(f"● {run['open_gates']} waiting on you", "you", bold=True)
    if run["waiting_on"] == "usage_window":
        return paint("● waiting on usage window", "stone")
    if run["waiting_on"] == "provisioning":
        return paint("● waiting on provisioning", "you")
    return paint("● running", "success")


def _clip(text, width):
    flat = " ".join(text.split())
    return flat if len(flat) <= width else flat[:width - 1] + "…"


def _named(found, name):
    return any(i["name"].strip().lower() == name.strip().lower() for i in found)


def _put(found, original, item, first="name"):
    """Replace the item whose first field is original, or add it when original is None or gone."""
    if original is not None:
        for n, existing in enumerate(found):
            if existing[first] == original:
                return found[:n] + [{**existing, **item}] + found[n + 1:]
    return found + [item]


async def show_runs(app, slug):
    """The runs list: the daemon's runs, then history imported at adoption."""
    runs = await app.client.get(f"/v1/projects/{slug}/runs")
    history = await app.client.get(f"/v1/projects/{slug}/history")
    picked = await app.push_screen_wait(RunsDialog(runs, history))
    if not picked:
        return
    kind, value = picked
    if kind == "run":
        if app.project != slug:
            await app.open_project(slug)
        app.select_run(value)
        app.show("run")
    else:
        await app.push_screen_wait(TextDialog(f"{value['run_id']} (imported)", imported_text(value, history["learnings"])))


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
            table.add_row(*(cell if isinstance(cell, Text) else Text(cell) for cell in cells), key=key)
        keys = [key for key, _ in rows]
        if current in keys:
            table.move_cursor(row=keys.index(current))


class ProjectsPane(Pane):
    focus_id = "#projects"
    BINDINGS = [Binding("n", "new", "new"), Binding("a", "adopt", "adopt"), Binding("x", "archive", "archive"),
                Binding("e", "settings", "settings"),
                Binding("o", "design", "design"), Binding("l", "runs", "runs")]

    def compose(self) -> ComposeResult:
        yield DataTable(id="projects", cursor_type="row", zebra_stripes=False)
        yield Static("", id="project-notes", markup=False)
        yield Static(keys(("n", "new"), ("a", "adopt"), ("enter", "open"), ("e", "settings"),
                          ("o", "design"), ("l", "runs"), ("x", "archive")), classes="hint")

    def on_mount(self):
        self.query_one("#projects", DataTable).add_columns("NAME", "PROFILE", "PHASE", "GATES", "CI", "STATUS")

    async def load(self):
        projects = await self.client.get("/v1/projects")
        self.projects = {p["slug"]: p for p in projects}
        rows = []
        for project in projects:
            run = project["active_run"]
            rows.append((project["slug"], (paint(project["name"], bold=True), paint(project["profile"] or "-", "dim"),
                                           paint(run["phase"] if run else "-", "stone"),
                                           str(run["open_gates"]) if run else "0",
                                           paint(project.get("settings", {}).get("ci_signal", "receipts"), "dim"),
                                           status_of(project))))
        self.fill(self.query_one("#projects", DataTable), rows)
        self._show_notes()

    def _show_notes(self):
        """What the selected project still needs from a person outside a run."""
        slug = self.table_key(self.query_one("#projects", DataTable))
        project = getattr(self, "projects", {}).get(slug) or {}
        notes = [paint(f"Merge by hand: {path}, the new rendering beside your file.", "you")
                 for path in project.get("hand_merge") or []]
        self.query_one("#project-notes", Static).update(lines(notes) if notes else "")

    def on_data_table_row_highlighted(self):
        self._show_notes()

    def action_settings(self):
        slug = self.table_key(self.query_one("#projects", DataTable))
        if slug:
            self.app.spawn(self._settings(slug))

    async def _settings(self, slug):
        args = await self.app.push_screen_wait(SettingsDialog(slug, self.projects[slug].get("settings") or {}))
        if args:
            await self.app.apply("project.configure", args, project=slug)

    def on_data_table_row_selected(self, event):
        self.app.spawn(self.app.open_project(event.row_key.value))

    def action_new(self):
        self.app.spawn(self._create("new"))

    def action_adopt(self):
        self.app.spawn(self._create("adopt"))

    async def _create(self, mode):
        title = "New project" if mode == "new" else "Adopt an existing repository"
        form = await self.app.push_screen_wait(FormDialog(title, {"name": "", "path": ""},
                                                          placeholders={"name": "My App", "path": "~/Repos/my-app"}))
        if not form:
            return
        args = {**form, "path": self._resolve(form["path"]), "mode": mode}
        if mode == "new":
            await self.app.apply("project.create", args)
            return
        # Adopting shows everything it would derive and write before it writes anything,
        # and that review is the confirmation.
        preview = await self.client.get("/v1/adopt/preview", path=args["path"])
        if await self.app.push_screen_wait(AdoptDialog(preview)):
            await self.app.apply("project.create", args, reviewed=True)

    def _selected(self):
        return self.table_key(self.query_one("#projects", DataTable))

    def action_design(self):
        slug = self._selected()
        if slug and self.projects.get(slug, {}).get("has_design"):
            self.app.spawn(self._open_design(slug))
        elif slug:
            self.app.notify(f"{slug} has no docs/design/index.html yet.")

    async def _open_design(self, slug):
        session = await self.client.get(f"/v1/projects/{slug}/design-session")
        self.app.open_url(session["url"])

    def action_runs(self):
        slug = self._selected()
        if slug:
            self.app.spawn(show_runs(self.app, slug))

    def _resolve(self, path):
        """A relative path means relative to where the person ran springer, which only
        this side knows. A ~ path goes as written, and the daemon expands it."""
        path = path.strip()
        return path if path.startswith("~") else os.path.abspath(path)

    def action_archive(self):
        slug = self.table_key(self.query_one("#projects", DataTable))
        if slug:
            self.app.spawn(self.app.apply("project.archive", project=slug))


class BriefPane(Pane):
    focus_id = "#rail"
    BINDINGS = [Binding("c", "check", "check"), Binding("s", "start", "start"), Binding("f", "facts", "facts"),
                Binding("d", "discovery", "discovery"), Binding("y", "confirm_section", "confirm"),
                Binding("v", "provisioning", "provisioning"), Binding("x", "dismiss_recommendation", "dismiss"),
                Binding("a", "add_item", "add"), Binding("delete", "remove_item", "remove"),
                Binding("backspace", "remove_item", "remove", show=False), Binding("t", "text_mode", "text"),
                Binding("ctrl+s", "save", "save", priority=True), Binding("escape", "to_rail", "sections")]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.brief = None
        self.section = None
        self.loaded_body = ""
        self.version = None
        self.as_text = set()  # structured sections the person switched to plain text
        self.parsed = ("", [])  # the preamble and items of the structured section shown

    def compose(self) -> ComposeResult:
        yield Static("", id="brief-title", classes="title")
        yield Static("", id="recommendation", markup=False)
        with Horizontal(id="brief-main"):
            yield OptionList(id="rail")
            with Vertical(id="brief-editor"):
                yield OptionList(id="items")
                yield TextArea(id="editor")
                # The interview's proposals land here beside the human's text, to accept,
                # edit, or drop. The interview itself is built after the TUI.
                yield Static("", id="proposal", markup=False)
            yield Static("", id="facts", markup=False)
        yield Static("", id="critique", markup=False)
        yield Static("", id="brief-keys", classes="hint")

    def _dirty(self):
        return self.section is not None and self.query_one("#editor", TextArea).text != self.loaded_body

    async def load(self):
        slug = self.app.project
        if slug is None:
            self.query_one("#brief-title", Static).update(paint("Open a project first.", "dim"))
            return
        self.brief = await self.client.get(f"/v1/projects/{slug}/brief")
        critique = await self.client.get(f"/v1/projects/{slug}/brief/critique")
        # While the human has unsaved text, base_version stays what that text was based
        # on. Moving it forward here would let a save overwrite someone else's edit.
        if not self._dirty():
            self.version = self.brief["version"]
        self._render_brief(critique)

    def _render_brief(self, critique):
        self.query_one("#brief-title", Static).update(
            join(paint("brief", "dim", bold=True), paint(f"  v{self.brief['version']}", "dim")))
        errored = {e["section"] for e in critique["errors"]}
        warned = {e["section"] for e in critique["warnings"]}

        def mark(section):
            if section["confidence"] == "proposed":
                return paint("?", "you", bold=True)
            if section["name"] in errored:
                return paint("!", "error", bold=True)
            if section["name"] in warned:
                return paint("•", "stone")
            return paint("✓", "success") if section["body"] else paint("○", "dim")

        rail = self.query_one("#rail", OptionList)
        highlighted = rail.highlighted
        rail.clear_options()
        rail.add_options([Option(join(mark(s), f" {s['name']}"), id=s["name"]) for s in self.brief["sections"]])
        if self.brief["sections"]:
            rail.highlighted = highlighted if highlighted is not None else 0
        facts = self.brief["facts"]
        rows = [paint("facts", "dim", bold=True)]
        rows += [join(paint(f"{k} ", "dim"), ", ".join(map(str, v)) if isinstance(v, list) else str(v))
                 for k, v in facts.items() if k not in ("pinned", "budget", "proposed") and v not in (None, [], "")]
        rows += [join(paint(f"pinned {k} ", "dim"), str(v)) for k, v in (facts.get("pinned") or {}).items()]
        rows += [Text(""), paint(self.brief["derived"]["sentence"], "stone")]
        self.query_one("#facts", Static).update(lines(rows))
        recommendation = self.brief["recommendation"]
        self.query_one("#recommendation", Static).update(
            join(paint(f"Discovery says {recommendation['verdict']}: ", "you", bold=True), recommendation["summary"],
                 paint("   x dismiss", "dim"))
            if recommendation and not recommendation.get("dismissed") else "")
        notes = [paint(f"! {SCREEN_MESSAGES.get(e['rule'], e['message'])}", "error") for e in critique["errors"]]
        notes += [paint(f"• {w['message']}", "stone") for w in critique["warnings"]]
        notes += [paint(f"i {i['message']}", "stone") for i in critique["info"]]
        if critique["errors"]:
            notes.append(paint(f"Start blocked: {len(critique['errors'])} error(s)", "error", bold=True))
        elif not self.brief["started"]:
            notes.append(paint("✓ Ready to start.", "success", bold=True))
        else:
            notes.append(paint("The run has started. An edit opens a scope-change gate.", "dim"))
        self.query_one("#critique", Static).update(lines(notes))
        self._show_section()

    def _show_section(self):
        """Refill the section from the brief, never over text the human is typing."""
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
            editor.placeholder = SECTION_TEMPLATES.get(section["name"], "")
            editor.load_text(section["body"])
        fields = self._fields()
        editor.display = not fields
        self.query_one("#items", OptionList).display = fields
        if fields:
            self._fill_items(section["body"])
        self._show_keys(fields)

    def _fields(self):
        """True when the section shown is edited through fields, not as plain text."""
        return self.section not in self.as_text and items.codec(self.section) is not None

    def _is_form(self):
        return self.section in items.FORMS

    def _show_keys(self, fields):
        common = (("c", "check"), ("s", "start"), ("f", "facts"), ("d", "discover"), ("y", "confirm"), ("v", "provide"))
        if fields and self._is_form():
            pairs = (("enter", "edit"), ("t", "as text"), ("esc", "sections"))
        elif fields:
            pairs = (("enter", "edit"), ("a", f"add {items.NOUNS[self.section]}"), ("del", "remove"), ("t", "as text"),
                     ("esc", "sections"))
        else:
            pairs = (("enter", "edit"), ("ctrl+s", "save"), ("t", "as fields"), ("esc", "sections"))
        self.query_one("#brief-keys", Static).update(keys(*pairs, *common))

    def _fill_items(self, body):
        parse, _ = items.codec(self.section)
        self.parsed = parse(body)
        preamble, content = self.parsed
        options = []
        if self._is_form():
            for key, label, _ in items.FORMS[self.section]:
                value = content.get(key, "")
                options.append(Option(lines([paint(label, "dim"), Text(_clip(value, 200)) if value
                                             else paint("not written yet", "dim"), Text("")]), id=f"field-{key}"))
        else:
            if preamble:
                label = "text that is not a flow yet" if self.section == "Core flows" else "notes"
                options.append(Option(join(paint("¶ ", "dim"), paint(f"{label}: ", "dim"), _clip(preamble, 60)),
                                      id="preamble"))
            options += [Option(self._item_label(item), id=f"item-{n}") for n, item in enumerate(content)]
            options.append(Option(paint(f"+ add a {items.NOUNS[self.section]}", "dim"), id="add"))
        listing = self.query_one("#items", OptionList)
        highlighted = listing.highlighted
        listing.clear_options()
        listing.add_options(options)
        listing.highlighted = min(highlighted or 0, len(options) - 1)

    def _item_label(self, item):
        if self.section == "Users":
            return join(paint("✓ ", "success"), paint(item["name"], bold=True),
                        paint(f"  {item['about']}" if item["about"] else "  no description yet", "dim"))
        if self.section != "Core flows":
            specs = items.LISTS[self.section]
            rest = [f"{label.lower()} {item[key]}" for key, label, _ in specs[1:] if item.get(key)]
            return join(paint("• ", "dim"), paint(item[specs[0][0]], bold=True),
                        paint(("  " + " · ".join(rest)) if rest else "", "dim"))
        gaps = items.missing(item)
        steps = len([s for s in item["steps"] if s.strip()])
        detail = [item["who"] or "nobody yet", f"{steps} step{'s' if steps != 1 else ''}"]
        if item["critical"]:
            detail.append("critical")
        first = join(paint("! " if gaps else "✓ ", "error" if gaps else "success", bold=bool(gaps)),
                     paint(item["name"], bold=True))
        second = paint("    " + " · ".join(detail), "dim")
        if gaps:
            second = join(second, paint(f" · needs {', '.join(gaps)}", "error"))
        return lines([first, second])

    def on_option_list_option_highlighted(self, event):
        if event.option_list.id != "rail" or self.brief is None or event.option.id == self.section:
            return
        if self._dirty():
            self.app.spawn(self._save_then_show())
        else:
            self._show_section()

    async def _save_then_show(self):
        await self._save()
        self._show_section()

    def on_option_list_option_selected(self, event):
        if event.option_list.id == "items":
            self.app.spawn(self._edit_item(event.option.id))
        else:
            self._body().focus()

    def _body(self):
        return self.query_one("#items" if self._fields() else "#editor")

    # --- sections as fields ---

    async def _edit_item(self, option_id):
        preamble, content = self.parsed
        if self._is_form():
            await self._edit_form()
        elif option_id == "add":
            await self._open_item(None)
        elif option_id == "preamble":
            text = await self.app.push_screen_wait(EditDialog(f"{self.section}: text kept as written", preamble))
            if text is not None:
                await self._write(lambda pre, found: (text.strip(), found))
        else:
            await self._open_item(content[int(option_id.removeprefix("item-"))])

    async def _edit_form(self):
        section = self.section
        specs = items.FORMS[section]
        values = await self.app.push_screen_wait(FieldsDialog(section, specs, self.parsed[1]))
        if values is not None:
            await self._write(lambda pre, old: (pre, values), section=section)

    async def _open_item(self, item):
        """Add when item is None, else edit it. Items are matched by name when written,
        so an edit lands on the right one even if the brief moved underneath."""
        section = self.section
        if section == "Core flows":
            await self._open_flow(item)
            return
        specs = (("name", "Name", "line"), ("about", "Who they are and what they want", "line")) \
            if section == "Users" else items.LISTS[section]
        first = specs[0][0]
        original = item[first] if item else None
        values = dict(item) if item else {key: "" for key, _, _ in specs}
        noun = items.NOUNS[section]
        values = await self.app.push_screen_wait(
            FieldsDialog(f"Edit {noun}" if item else f"New {noun}", specs, values, required=first))
        if values is not None:
            await self._write(lambda pre, found: (pre, _put(found, original, values, first)), section=section)

    async def _open_flow(self, item):
        original = item["name"] if item else None
        users = items.parse_users(self._body_of("Users"))[1]
        answer = await self.app.push_screen_wait(
            FlowDialog(item or items.blank_flow(), users, title="Edit flow" if item else "New flow"))
        if answer is None:
            return
        new_users = answer["new_users"]
        if new_users and not await self._write(
                lambda pre, found: (pre, found + [u for u in new_users if not _named(found, u["name"])]),
                section="Users"):
            return
        await self._write(lambda pre, found: (pre, _put(found, original, answer["flow"])), section="Core flows")

    def _body_of(self, name):
        return next((s["body"] for s in self.brief["sections"] if s["name"] == name), "")

    async def _write(self, change, section=None):
        """Apply change(preamble, content) to the section as the daemon holds it now and
        save. A save that lost a race is applied again to the newer brief, once."""
        section = section or self.section
        parse, write = items.codec(section)
        for attempt in (1, 2):
            body = write(*change(*parse(self._body_of(section))))
            try:
                outcome = await self.app.apply("brief.update_section",
                                               {"section": section, "body": body, "base_version": self.version},
                                               project=self.app.project, reraise=True)
            except ApiError as exc:
                if exc.code == "stale_version" and attempt == 1:
                    self.brief = await self.client.get(f"/v1/projects/{self.app.project}/brief")
                    self.version = self.brief["version"]
                    continue
                self.app.notify(exc.message, severity="error")
                return False
            if not outcome:
                return False
            self.version = outcome["result"]["version"]
            await self.load()
            return True

    def action_add_item(self):
        if self._fields() and not self._is_form():
            self.app.spawn(self._open_item(None))

    def action_remove_item(self):
        listing = self.query_one("#items", OptionList)
        if not self._fields() or self._is_form() or not listing.has_focus or listing.highlighted is None:
            return
        option_id = listing.get_option_at_index(listing.highlighted).id
        if option_id.startswith("item-"):
            self.app.spawn(self._remove(int(option_id.removeprefix("item-"))))

    async def _remove(self, index):
        section = self.section
        item = self.parsed[1][index]
        first = "name" if section in ("Core flows", "Users") else items.LISTS[section][0][0]
        name = item[first]
        preview = {"summary": f"Remove {_clip(name, 50)} from {section}?", "consequences": ["Nothing else changes."]}
        if await self.app.push_screen_wait(ConfirmDialog(preview)):
            await self._write(lambda pre, found: (pre, [i for i in found if i[first] != name]), section=section)

    def action_text_mode(self):
        """Switch a section to plain text and back. Unsaved text is saved first."""
        if items.codec(self.section) is None:
            return
        self.app.spawn(self._toggle_text())

    async def _toggle_text(self):
        if not await self._save():
            return
        self.as_text ^= {self.section}
        self._show_section()
        self._body().focus()

    async def _save(self):
        """Write plain text typed in the editor. False when the text stays unsaved, so a
        caller does not move on from it."""
        if not self._dirty():
            return True
        text = self.query_one("#editor", TextArea).text
        args = {"section": self.section, "body": text, "base_version": self.version}
        try:
            outcome = await self.app.apply("brief.update_section", args, project=self.app.project, reraise=True)
        except ApiError as exc:
            if exc.code == "stale_version":
                self.version = exc.details["current_version"]
                self.app.notify(f"The brief changed elsewhere, now v{self.version}. Your text is kept. "
                                "Save again to write over it.", severity="warning")
                return False
            self.app.notify(exc.message, severity="error")
            return False
        if outcome:
            self.loaded_body = text
            await self.load()
            return True
        return False

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
        if not await self._save():
            return
        args = {"base_version": self.version}
        project = await self.client.get(f"/v1/projects/{self.app.project}")
        if project.get("adopted"):
            choice = await self.app.push_screen_wait(StartDialog())
            if choice is None:
                return
            if choice["lane"] == "build" and self.version == project.get("adopted_brief_version"):
                self.app.notify("Describe the change in the brief first: edit the sections it touches, then "
                                "press s and choose build.", severity="warning")
                self.query_one("#rail", OptionList).focus()
                return
            args.update({k: v for k, v in choice.items() if v})
        outcome = await self.app.apply("run.start", args, project=self.app.project)
        if outcome and outcome.get("result", {}).get("run_id"):
            self.app.select_run(outcome["result"]["run_id"])
            self.app.show("run")

    def action_facts(self):
        self.app.spawn(self._facts())

    async def _facts(self):
        facts = await self.app.push_screen_wait(FactsDialog(self.brief["facts"]))
        if facts is not None:
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
        yield Static("", id="backlog-title", classes="title")
        yield DataTable(id="backlog", cursor_type="row", show_header=False)
        yield Static("", id="board", markup=False)
        yield Static(keys(("v", "view"), ("space", "fold"), ("m", "move line here"), ("d", "defer/restore"),
                          ("J/K", "reorder"), ("+", "add bug"), ("u", "unknowns"), ("o", "open PR")), classes="hint")

    def on_mount(self):
        self.query_one("#backlog", DataTable).add_columns("ITEM", "COLUMN", "RISK", "WAVE", "NOTE")

    async def load(self):
        if not self.app.run_id:
            self.query_one("#backlog-title", Static).update(paint("No backlog until a run starts.", "dim"))
            return
        self.data = await self.client.get(run_path(self.app.project, self.app.run_id) + "/backlog")
        unanswered = sum(1 for u in self.data["unknowns"] if u["answer"] is None)
        self.query_one("#backlog-title", Static).update(join(
            paint("backlog", "dim", bold=True), paint(f"   view: {self.view_name}", "dim"),
            paint(f"   unknowns: {unanswered}", "you" if unanswered else "dim")))
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
            rows.append((f"epic:{epic['epic_id']}", (paint(f"{epic['epic_id']} {epic['title']}{critical}", "text", bold=True),
                                                     "", "", "", "")))
            for feature in epic["features"]:
                if not feature["mvp"] and not line_drawn:
                    rows.append(("line", (paint("──────────── MVP LINE ────────────", "stone", bold=True), "", "", "", "")))
                    line_drawn = True
                fold = "▸" if feature["feature_id"] in self.folded else "▾"
                rows.append((f"feature:{feature['feature_id']}",
                             (paint(f"  {fold} {feature['feature_id']} {feature['title']}", bold=True), "", "", "",
                              paint("deferred" if feature["deferred"] else "", "dim"))))
                if feature["feature_id"] in self.folded:
                    continue
                for story in feature["stories"]:
                    pr = story.get("pr") or {}
                    deps = ", ".join(story.get("depends_on", []))
                    note = " ".join(x for x in (f"PR #{pr['number']}" if pr else "", f"needs {deps}" if deps else "") if x)
                    column, risk = story.get("column") or "", story.get("risk") or ""
                    rows.append((f"story:{story['story_id']}",
                                 (join(paint(f"      {story['story_id']} ", "dim"), story["title"]),
                                  paint(column, COLUMN.get(column)), paint(risk, RISK.get(risk)),
                                  paint("" if story.get("wave") is None else f"wave {story['wave']}", "dim"),
                                  paint(note, "dim"))))
        return rows

    def _board_text(self):
        rows = []
        for column in COLUMNS:
            stories = [s for s in self._stories() if s.get("column") == column]
            rows.append(paint(f"{column.upper()} ({len(stories)})", COLUMN[column], bold=True))
            rows += [join(paint(f"  {s['story_id']} ", "dim"), s["title"],
                          paint(f"  {s.get('risk') or ''}".rstrip(), RISK.get(s.get("risk")))) for s in stories]
            rows.append(Text(""))
        return lines(rows)

    def _graph_text(self):
        rows = [paint("dependencies", "dim", bold=True)]
        edges = [join(s["story_id"], paint(" <- ", "dim"), ", ".join(s["depends_on"]))
                 for s in self._stories() if s.get("depends_on")]
        return lines(rows + (edges or [paint("None.", "dim")]))

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
                Binding("R", "redispatch", "re-dispatch"), Binding("X", "cancel_run", "cancel run"),
                Binding("v", "viewed", "clear routine"), Binding("l", "runs", "runs")]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.run = None
        self.open_gates = []
        self.digest = []
        self.selected_gate = 0

    def compose(self) -> ComposeResult:
        yield VerticalScroll(Static("", id="gates", markup=False), id="gates-box")
        yield Static("", id="run-title", classes="section", markup=False)
        yield DataTable(id="units", cursor_type="row")
        yield Static(keys(("c", "cancel"), ("R", "one tier up"), ("enter", "live output"), ("P", "pause run"), ("X", "cancel run")),
                     classes="hint")
        yield Static("", id="routine", markup=False)

    def on_mount(self):
        self.query_one("#units", DataTable).add_columns("UNIT", "AGENT", "MODEL", "TIME", "CTX", "COST", "LAST")

    def _path(self):
        return run_path(self.app.project, self.app.run_id)

    async def load(self):
        if not self.app.run_id:
            self.query_one("#run-title", Static).update(paint("No run yet. Start one from the brief.", "dim"))
            return
        path = self._path()
        self.run = await self.client.get(path)
        self.open_gates = (await self.client.get(path + "/gates", state="open", digest="false"))["items"]
        self.digest = (await self.client.get(path + "/gates", state="open", digest="true"))["items"]
        self.selected_gate = min(self.selected_gate, max(0, len(self.open_gates) - 1))
        self._render_run()

    def _render_run(self):
        run = self.run
        counts = ", ".join(f"{count} {state}" for state, count in sorted(run["units"].items()))
        self.query_one("#run-title", Static).update(join(paint("in flight", "dim", bold=True), paint(f"   {counts}", "dim")))
        self.query_one("#gates-box").display = bool(self.open_gates)
        self.query_one("#gates", Static).update(self._gates_text())
        rows = []
        for row in run["in_flight"]:
            context = "" if row.get("context_percent") is None else f"{row['context_percent']:.0f}%"
            rows.append((f"{row['unit_id']}/{row['session_id']}",
                         (row["unit_id"], row["agent"].removeprefix("spgr-agent-"), row["model"], age(row["started_at"]),
                          context, f"${row.get('cost') or 0:.2f}", row.get("last_tool_call") or "")))
        self.fill(self.query_one("#units", DataTable), rows)
        rows = [join(paint("routine, since you looked", "dim", bold=True), "   ", keys(("v", "clear")))]
        rows += [join(paint("· ", "success"), paint(g["decision_prompt"], "dim")) for g in self.digest] or [paint("Nothing new.", "dim")]
        self.query_one("#routine", Static).update(lines(rows))

    def _gate_label(self, gate):
        kind = {"pr-merge": "merge"}.get(gate["checkpoint_type"], gate["checkpoint_type"].replace("-", " "))
        return f"{gate['checkpoint_id']} · {gate['level']} {kind} · {gate['context']['age_seconds'] // 60}m"

    def _gates_text(self):
        """One gate reads as one block. With several, each gets a line and tab moves
        between them. Terracotta is on what you act on and nothing else."""
        if not self.open_gates:
            return ""
        single = len(self.open_gates) == 1
        rows = [join(paint("needs you", "you", bold=True),
                     paint(f"   {self._gate_label(self.open_gates[0])}" if single else f" ({len(self.open_gates)})   tab next", "dim"))]
        for index, gate in enumerate(self.open_gates):
            selected = index == self.selected_gate
            if not single:
                rows.append(join(paint("› " if selected else "  ", "you", bold=True), paint(self._gate_label(gate), "text" if selected else "dim")))
            if not selected:
                continue
            context = gate["context"]
            rows.append(paint(gate["decision_prompt"], "text", bold=True))
            rows += [paint(f"{f.get('vertical', '').removeprefix('spgr-agent-')}  {f.get('detail', '')} ({f.get('rule', '')})",
                           "error") for f in context.get("findings", [])]
            width = max(len(o["option"]) for o in gate["options"]) + 2
            for number, option in enumerate(gate["options"], 1):
                rows.append(join(paint(f"{number} ", "you", bold=True),
                                 paint(option["option"].replace("_", " ").ljust(width), "text", bold=True),
                                 paint(option["consequence"], "dim"),
                                 paint("   recommended" if option.get("recommended_because") else "", "success")))
            rows += [join(paint(f"decision {decision['decision_id']}  ", "dim"), decision["prompt"])
                     for decision in gate.get("decisions", [])]
            hints = [("n", "answer with notes")]
            if context.get("diff_path"):
                hints.append(("d", "diff"))
            if context.get("design_session"):
                hints.append(("o", "open in browser"))
            rows.append(keys(*hints))
        return lines(rows)

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

    def action_cancel_run(self):
        self._op("run.cancel")

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

    def action_runs(self):
        if self.app.project:
            self.app.spawn(show_runs(self.app, self.app.project))

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
