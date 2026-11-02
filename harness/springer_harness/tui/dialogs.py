"""Modal dialogs. Each returns its answer through dismiss, and None means cancel."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Select, Static, TextArea

from .theme import join, keys, paint

NEW_USER = "\0new-user"


class Dialog(ModalScreen):
    # The app's screen keys would act on the panes behind an open dialog, so a key
    # no field takes does nothing here.
    BINDINGS = [Binding("escape", "cancel", "Cancel")] + [
        Binding(key, "ignore", show=False) for key in ("p", "b", "k", "r", "q", "slash")]

    def action_cancel(self):
        self.dismiss(None)

    def action_ignore(self):
        pass


class ConfirmDialog(Dialog):
    """Shows the API's preview as it came, so every scope or config change reads the same."""

    BINDINGS = [Binding("y", "yes", "Yes"), Binding("n", "cancel", "No"), Binding("escape", "cancel", "Cancel")]

    def __init__(self, preview):
        super().__init__()
        self.preview = preview

    def compose(self) -> ComposeResult:
        lines = "\n".join(f"  {c}" for c in self.preview.get("consequences", []))
        with Vertical(classes="dialog"):
            yield Static(self.preview["summary"], classes="dialog-title", markup=False)
            yield Static(lines, markup=False)
            yield Static(keys(("y", "confirm"), ("n", "cancel")), classes="hint")

    def action_yes(self):
        self.dismiss(True)


class FormDialog(Dialog):
    """A title and named inputs. A field named in masked hides what is typed."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title, fields, masked=(), placeholders=None, advance=False):
        super().__init__()
        self.advance = advance  # enter moves to the next field, and submits from the last
        self.form_title = title
        self.fields = fields
        self.masked = masked
        self.placeholders = placeholders or {}

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static(self.form_title, classes="dialog-title", markup=False)
            for name, value in self.fields.items():
                yield Label(name)
                yield Input(value=value, id=f"field-{name}", password=name in self.masked,
                            placeholder=self.placeholders.get(name, ""))
            yield Static(keys(("enter", "next, then save" if self.advance else "submit"), ("esc", "cancel")),
                         classes="hint")

    def on_input_submitted(self, event):
        event.stop()
        names = list(self.fields)
        if self.advance and event.input.id != f"field-{names[-1]}":
            self.focus_next()
            return
        self.dismiss({name: self.query_one(f"#field-{name}", Input).value for name in self.fields})


class TextDialog(Dialog):
    """Read-only text that scrolls (e.g. a PR diff, a session's live output)."""

    def __init__(self, title, text=""):
        super().__init__()
        self.dialog_title = title
        self.text = text

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Static(self.dialog_title, classes="dialog-title", markup=False)
            with VerticalScroll():
                yield Static(self.text, id="dialog-text", markup=False)
            yield Static(keys(("esc", "close")), classes="hint")

    def append(self, line):
        self.text += line + "\n"
        self.query_one("#dialog-text", Static).update(self.text)


class EditDialog(Dialog):
    """Multi-line text, saved with ctrl+s (e.g. the facts as YAML, structure notes)."""

    BINDINGS = [Binding("ctrl+s", "save", "Save", priority=True), Binding("escape", "cancel", "Cancel")]

    def __init__(self, title, text=""):
        super().__init__()
        self.dialog_title = title
        self.text = text

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Static(self.dialog_title, classes="dialog-title", markup=False)
            yield TextArea(self.text, id="dialog-editor")
            yield Static(keys(("ctrl+s", "save"), ("esc", "cancel")), classes="hint")

    def action_save(self):
        self.dismiss(self.query_one("#dialog-editor", TextArea).text)


class Fields(VerticalScroll, can_focus=False):
    """The scrolling body of a form. It never takes focus itself, so the first key a
    person types lands in the first field."""


class Toggle(Static, can_focus=True):
    """A yes or no answer that says which it is, toggled with space or enter."""

    BINDINGS = [Binding("space", "toggle", show=False), Binding("enter", "toggle", show=False)]

    def __init__(self, value, yes, no, **kwargs):
        super().__init__("", markup=False, **kwargs)
        self.value, self.yes, self.no = value, yes, no

    def on_mount(self):
        self._paint()

    def action_toggle(self):
        self.value = not self.value
        self._paint()

    def _paint(self):
        self.update(join(paint("[x] " if self.value else "[ ] ", "text", bold=True),
                         paint(self.yes if self.value else self.no, "text" if self.value else "dim")))


class FlowDialog(Dialog):
    """One core flow as fields. Who picks from Users, and a person new to Users can be
    added from here without leaving the flow. Returns {"flow", "new_users"}."""

    BINDINGS = [Binding("ctrl+s", "save", "Save", priority=True)]

    def __init__(self, flow, users, title="New flow"):
        super().__init__()
        self.flow = flow
        self.users = list(users)
        self.new_users = []
        self.dialog_title = title

    def _who_options(self):
        names = [u["name"] for u in self.users + self.new_users]
        who = self.flow["who"].strip()
        options = [(n, n) for n in names]
        if who and who.lower() not in {n.lower() for n in names}:
            options.append((f"{who}  (joins Users on save)", who))
        return options + [("+ someone new", NEW_USER)]

    def compose(self) -> ComposeResult:
        flow = self.flow
        with Vertical(classes="dialog form"):
            yield Static(self.dialog_title, classes="dialog-title", markup=False)
            with Horizontal(classes="form-row"):
                yield Label("name")
                yield Input(flow["name"], id="flow-name", placeholder="Pick a diet", compact=True)
            with Horizontal(classes="form-row"):
                yield Label("who")
                yield Select(self._who_options(), id="flow-who", prompt="pick from Users",
                             value=flow["who"].strip() or Select.NULL, compact=True)
            with Horizontal(classes="form-row"):
                yield Label("trigger")
                yield Input(flow["trigger"], id="flow-trigger", placeholder="what starts it", compact=True)
            with Horizontal(classes="form-row steps"):
                yield Label("steps")
                yield TextArea("\n".join(flow["steps"]), id="flow-steps", compact=True, show_line_numbers=True,
                               placeholder="one step per line, in order")
            with Horizontal(classes="form-row"):
                yield Label("outcome")
                yield Input(flow["outcome"], id="flow-outcome", placeholder="how they know it worked", compact=True)
            with Horizontal(classes="form-row"):
                yield Label("critical")
                yield Toggle(flow["critical"], "yes, the product fails without this flow", "no", id="flow-critical")
            yield Static("", id="flow-error", markup=False)
            yield Static(keys(("tab", "next field"), ("ctrl+s", "save"), ("esc", "cancel")), classes="hint")

    def on_input_submitted(self, event):
        event.stop()
        self.focus_next()

    def on_select_changed(self, event):
        if event.value == NEW_USER:
            placeholders = {"name": "Home cook", "about": "who they are and what they want"}
            self.app.push_screen(FormDialog("Someone new in Users", {"name": "", "about": ""}, placeholders=placeholders,
                                            advance=True), self._added_user)

    def _added_user(self, form):
        select = self.query_one("#flow-who", Select)
        if not form or not form["name"].strip():
            select.value = Select.NULL
            return
        user = {"name": form["name"].strip(), "about": form["about"].strip()}
        if user["name"].lower() not in {u["name"].lower() for u in self.users + self.new_users}:
            self.new_users.append(user)
        select.set_options(self._who_options())
        select.value = next(v for _, v in self._who_options() if v.lower() == user["name"].lower())

    def action_save(self):
        name = self.query_one("#flow-name", Input).value.strip()
        if not name:
            self.query_one("#flow-error", Static).update("Name the flow first.")
            self.query_one("#flow-name", Input).focus()
            return
        who = self.query_one("#flow-who", Select).value
        who = "" if who in (Select.NULL, NEW_USER) else str(who)
        if who and who.lower() not in {u["name"].lower() for u in self.users + self.new_users}:
            self.new_users.append({"name": who, "about": ""})
        steps = [line.strip() for line in self.query_one("#flow-steps", TextArea).text.splitlines() if line.strip()]
        flow = {**self.flow, "name": name, "who": who, "steps": steps,
                "trigger": self.query_one("#flow-trigger", Input).value.strip(),
                "outcome": self.query_one("#flow-outcome", Input).value.strip(),
                "critical": self.query_one("#flow-critical", Toggle).value}
        self.dismiss({"flow": flow, "new_users": self.new_users})


class FieldsDialog(Dialog):
    """A form from specs of (key, label, kind), kind being line or text. Returns the
    values by key, or None on cancel."""

    BINDINGS = [Binding("ctrl+s", "save", "Save", priority=True)]

    def __init__(self, title, specs, values, required=None):
        super().__init__()
        self.dialog_title, self.specs, self.values, self.required = title, specs, values, required

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog form"):
            yield Static(self.dialog_title, classes="dialog-title", markup=False)
            with Fields(classes="form-fields"):
                for key, label, kind in self.specs:
                    if kind == "text":
                        yield Label(label, classes="form-label")
                        yield TextArea(self.values.get(key, ""), id=f"f-{key}", compact=True, classes="form-text")
                    else:
                        yield Label(label, classes="form-label")
                        yield Input(self.values.get(key, ""), id=f"f-{key}", compact=True, classes="form-line")
            yield Static("", id="form-error", markup=False)
            yield Static(keys(("tab", "next field"), ("ctrl+s", "save"), ("esc", "cancel")), classes="hint")

    def on_input_submitted(self, event):
        event.stop()
        self.focus_next()

    def action_save(self):
        values = {}
        for key, _, kind in self.specs:
            widget = self.query_one(f"#f-{key}")
            values[key] = (widget.text if kind == "text" else widget.value).strip()
        if self.required and not values[self.required]:
            label = next(label for key, label, _ in self.specs if key == self.required)
            self.query_one("#form-error", Static).update(f"{label} is needed.")
            self.query_one(f"#f-{self.required}").focus()
            return
        self.dismiss(values)


# The facts a person states about the product, each with the values the brief allows.
# See Frontmatter in docs/harness/design-notes.md.
FACT_CHOICES = (
    ("backend", "Backend", ("none", "yes")),
    ("accounts", "Accounts", ("none", "single-org", "multi-org")),
    ("payments", "Payments", ("none", "one-time", "subscription")),
    ("scale", "Scale", ("personal", "team", "public")),
    ("autonomy", "Autonomy", ("supervised", "standard", "autopilot")),
    ("deploy", "Deploy", ("cloud", "self-hosted")),
    ("reach", "Reach", ("regional", "global")),
    ("variants", "Variants", (0, 2, 3)),
)
SURFACES = ("web", "mobile", "api", "cli")


class FactsDialog(Dialog):
    """The product facts as choices. Returns only the facts this form shows, typed the
    way the frontmatter stores them. The profile is derived from them, never picked."""

    BINDINGS = [Binding("ctrl+s", "save", "Save", priority=True)]

    def __init__(self, facts):
        super().__init__()
        self.facts = facts

    def compose(self) -> ComposeResult:
        facts = self.facts
        with Vertical(classes="dialog form"):
            yield Static("Facts", classes="dialog-title", markup=False)
            with Fields(classes="form-fields"):
                with Horizontal(classes="form-row"):
                    yield Label("Surfaces")
                    for surface in SURFACES:
                        yield Toggle(surface in (facts.get("surfaces") or []), surface, surface,
                                     id=f"surface-{surface}", classes="surface")
                for key, label, values in FACT_CHOICES:
                    current = facts.get(key)
                    current = "yes" if current is True else "none" if current is False else current
                    with Horizontal(classes="form-row"):
                        yield Label(label)
                        yield Select([(str(v), v) for v in values], id=f"fact-{key}", compact=True,
                                     value=current if current in values else Select.NULL, prompt="default")
                with Horizontal(classes="form-row"):
                    yield Label("Live")
                    yield Toggle(bool(facts.get("live")), "yes, people already use it", "no, not yet", id="fact-live")
                for key, label, hint in (("staging", "Staging host", "a host registered in the harness"),
                                         ("frameworks", "Compliance", "e.g. gdpr, hipaa"),
                                         ("reference", "Reference", "a POC or earlier version to match")):
                    value = facts.get(key)
                    value = ", ".join(value) if isinstance(value, list) else (value or "")
                    with Horizontal(classes="form-row"):
                        yield Label(label)
                        yield Input(str(value), id=f"fact-{key}", placeholder=hint, compact=True)
                with Horizontal(classes="form-row"):
                    yield Label("Daily cap $")
                    cap = (facts.get("budget") or {}).get("daily_cap_usd")
                    yield Input("" if cap is None else str(cap), id="fact-cap", placeholder="no cap", compact=True,
                                restrict=r"[0-9.]*")
                yield Label("Pinned decisions, one per line (e.g. db: postgres)", classes="form-label")
                pinned = "\n".join(f"{k}: {v}" for k, v in (facts.get("pinned") or {}).items())
                yield TextArea(pinned, id="fact-pinned", compact=True, classes="form-text")
            yield Static("", id="form-error", markup=False)
            yield Static(keys(("tab", "next"), ("space", "toggle"), ("ctrl+s", "save"), ("esc", "cancel")),
                         classes="hint")

    def on_input_submitted(self, event):
        event.stop()
        self.focus_next()

    def action_save(self):
        facts = {"surfaces": [s for s in SURFACES if self.query_one(f"#surface-{s}", Toggle).value]}
        if not facts["surfaces"]:
            self.query_one("#form-error", Static).update("Pick at least one surface.")
            return
        for key, _, _ in FACT_CHOICES:
            value = self.query_one(f"#fact-{key}", Select).value
            if value is not Select.NULL:
                facts[key] = value
        facts["live"] = self.query_one("#fact-live", Toggle).value
        staging = self.query_one("#fact-staging", Input).value.strip()
        facts["staging"] = staging or None
        facts["frameworks"] = [f.strip() for f in self.query_one("#fact-frameworks", Input).value.split(",") if f.strip()]
        facts["reference"] = self.query_one("#fact-reference", Input).value.strip() or None
        cap = self.query_one("#fact-cap", Input).value.strip()
        try:
            facts["budget"] = {"daily_cap_usd": float(cap) if "." in cap else int(cap)} if cap else None
        except ValueError:
            self.query_one("#form-error", Static).update("The daily cap is a number of dollars.")
            return
        pinned = {}
        for line in self.query_one("#fact-pinned", TextArea).text.splitlines():
            key, colon, value = line.partition(":")
            if not line.strip():
                continue
            if not colon or not key.strip() or not value.strip():
                self.query_one("#form-error", Static).update(f"Write a pinned decision as id: choice, not {line.strip()}")
                return
            pinned[key.strip()] = value.strip()
        facts["pinned"] = pinned
        self.dismiss(facts)

