"""Modal dialogs. Each returns its answer through dismiss, and None means cancel."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static, TextArea

from .theme import keys


class Dialog(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def action_cancel(self):
        self.dismiss(None)


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

    def __init__(self, title, fields, masked=(), placeholders=None):
        super().__init__()
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
            yield Static(keys(("enter", "submit"), ("esc", "cancel")), classes="hint")

    def on_input_submitted(self):
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
