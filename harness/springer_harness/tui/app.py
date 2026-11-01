"""The Springer TUI: four screens and a chat line over the daemon API."""

import asyncio
import calendar
import time
import uuid
import webbrowser

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.containers import Horizontal
from textual.widgets import ContentSwitcher, Input, Static

from .client import ApiError, ConnectionLost, run_path
from .dialogs import ConfirmDialog
from .panes import BacklogPane, BriefPane, ProjectsPane, RunPane
from .theme import C, THEME, join, keys, paint

REFRESH_SECONDS = 0.25
IDLE_REFRESH_SECONDS = 5
RETRY_SECONDS = 1
LOST = "Lost the daemon. What you see may be stale. Retrying."
QUIET_EVENTS = {"heartbeat"}


class SpringerApp(App):
    TITLE = "Springer"
    CSS = """
    Screen { background: $background; }
    #topbar { height: 1; padding: 0 1; }
    #banner { height: auto; background: $error 20%%; color: $error; padding: 0 1; display: none; }
    #banner.lost { display: block; }
    #panes { height: 1fr; }
    .title { height: auto; padding: 0 1; }
    .section { height: 1; padding: 0 1; margin-top: 1; }
    .hint { height: auto; padding: 0 1; }
    #statusline { height: 1; padding: 0 1; }
    #chat-log { height: auto; max-height: 4; padding: 0 1; display: none; }
    #chat-log.shown { display: block; }
    #prompt { dock: bottom; height: 2; border-top: solid %(border)s; padding: 0 1; }
    #prompt-mark { width: 2; height: 1; }
    #chat { height: 1; width: 1fr; border: none; padding: 0; background: $background; }
    #chat:focus { border: none; background: $background; }
    DataTable { height: auto; max-height: 1fr; background: $background; margin: 0 1; }
    DataTable:focus { background-tint: transparent; }
    DataTable > .datatable--header { background: $background; color: %(dim)s; text-style: bold; }
    DataTable > .datatable--cursor { background: %(selected)s; color: %(text)s; }
    DataTable:focus > .datatable--cursor { background: %(selected)s; color: %(text)s; text-style: none; }
    DataTable > .datatable--hover { background: $background; }
    #projects, #backlog { height: 1fr; }
    #board { height: 1fr; padding: 0 1; }
    #gates-box { height: auto; max-height: 50%%; background: %(pending)s; border-left: thick $primary; padding: 0 1; margin: 1 1 0 1; }
    #gates { height: auto; }
    #routine { height: auto; padding: 0 1; margin-top: 1; }
    #brief-main { height: 1fr; margin-top: 1; }
    #rail { width: 30; height: 100%%; border: none; padding: 0; background: $background; }
    #rail:focus { border: none; }
    #rail > .option-list--option-highlighted { background: %(selected)s; color: %(text)s; text-style: none; }
    #rail:focus > .option-list--option-highlighted { background: %(selected)s; color: %(text)s; text-style: none; }
    #brief-editor { width: 1fr; height: 100%%; border-left: solid %(border)s; padding: 0 1; }
    #editor { height: 1fr; border: none; padding: 0; background: $background; }
    #editor:focus { border: none; }
    #proposal { height: auto; display: none; }
    #facts { width: 32; height: 100%%; padding: 0 1; border-left: solid %(border)s; }
    #recommendation { height: auto; padding: 0 1; }
    #critique { height: auto; max-height: 8; padding: 0 1; margin-top: 1; }
    ConfirmDialog, FormDialog, TextDialog, EditDialog { align: center middle; background: $background 60%%; }
    .dialog { width: 70; height: auto; max-height: 80%%; background: $surface; border-left: thick $primary; padding: 1 2; }
    .dialog.wide { width: 90%%; height: 80%%; }
    .dialog-title { text-style: bold; color: $primary; margin-bottom: 1; }
    .dialog Label { color: %(dim)s; }
    .dialog Input { border: none; border-bottom: solid %(border)s; height: 2; padding: 0; background: $surface; margin-bottom: 1; }
    .dialog Input:focus { border: none; border-bottom: solid $primary; background: $surface; }
    #dialog-editor { height: 1fr; border: none; background: $surface; }
    """ % C
    BINDINGS = [Binding("p", "show('projects')", "projects"), Binding("b", "show('brief')", "brief"),
                Binding("k", "show('backlog')", "backlog"), Binding("r", "show('run')", "run"),
                Binding("slash", "chat", "chat"), Binding("q", "quit", "quit")]

    def __init__(self, client, open_url=webbrowser.open):
        super().__init__()
        self.client = client
        self.open_url = open_url
        self.project = None
        self.run_id = None
        self.dirty = True
        self.connected = True
        self._refreshing = False
        self._run_watch = None
        self._idle = 0.0

    def compose(self) -> ComposeResult:
        yield Static("Springer", id="topbar", markup=False)
        yield Static(LOST, id="banner", markup=False)
        with ContentSwitcher(initial="projects", id="panes"):
            yield ProjectsPane(id="projects-pane")
            yield BriefPane(id="brief-pane")
            yield BacklogPane(id="backlog-pane")
            yield RunPane(id="run-pane")
        yield Static("", id="chat-log", markup=False)
        yield Static("", id="statusline", markup=False)
        with Horizontal(id="prompt"):
            yield Static(paint("› ", "accent", bold=True), id="prompt-mark")
            yield Input(placeholder="ask anything  (press / to focus)", id="chat")

    def on_mount(self):
        self.register_theme(THEME)
        self.theme = THEME.name
        self._main_screen = self.screen
        self.main.query_one("#panes", ContentSwitcher).current = "projects-pane"
        self.set_interval(REFRESH_SECONDS, self._tick)
        self.run_worker(self._watch("/v1/events"), name="daemon-stream")
        self.main.query_one("#projects").focus()

    @property
    def main(self):
        """The screen the panes live on. App.query_one searches the screen on top, which
        is a dialog whenever one is open, and the panes must keep working under it."""
        return self._main_screen

    def spawn(self, coroutine):
        """Run a key's work in the background. A worker that raises would close the whole
        app, so a refusal or a lost daemon is shown on the screen here instead."""

        async def guarded():
            try:
                await coroutine
            except ApiError as exc:
                self.notify(self._explain(exc), severity="error")
            except ConnectionLost:
                self._set_connected(False)
                self.notify("The daemon did not answer, so nothing changed.", severity="error")
            except NoMatches:
                pass  # the screen is closing under this work

        return self.run_worker(guarded())

    # --- navigation ---

    def _pane(self, name=None):
        switcher = self.main.query_one("#panes", ContentSwitcher)
        return self.main.query_one(f"#{name}-pane") if name else self.main.query_one(f"#{switcher.current}")

    def show(self, name):
        self.main.query_one("#panes", ContentSwitcher).current = f"{name}-pane"
        self._pane(name).focus_main()
        self.mark_dirty()

    def action_show(self, name):
        self.show(name)

    def action_chat(self):
        self.main.query_one("#chat", Input).focus()

    def select_run(self, run_id):
        self.run_id = run_id
        if self._run_watch:
            self._run_watch.cancel()
            self._run_watch = None
        if run_id:
            path = run_path(self.project, run_id) + "/events"
            self._run_watch = self.run_worker(self._watch(path, resume=True), name="run-stream")

    async def open_project(self, slug):
        self.project = slug
        project = await self.client.get(f"/v1/projects/{slug}")
        run = project["active_run"]
        runs = await self.client.get(f"/v1/projects/{slug}/runs")
        run_id = run["run_id"] if run else (runs[0]["run_id"] if runs else None)
        self.select_run(run_id)
        self.show("run" if run_id else "brief")

    async def open_design(self):
        session = await self.client.get(f"/v1/projects/{self.project}/design-session")
        self.open_url(session["url"])

    # --- writes: one path, with the confirmation flow ---

    async def apply(self, kind, args=None, project=None, run_id=None, reraise=False):
        """Send an operation. A change that needs confirming shows the API's preview,
        and on yes is sent again with its token. Returns the outcome, or None."""
        op_id = str(uuid.uuid4())
        try:
            outcome = await self.client.op(kind, args, project, run_id, op_id=op_id)
            if outcome["status"] == "needs_confirmation":
                if not await self.push_screen_wait(ConfirmDialog(outcome["preview"])):
                    return None
                outcome = await self.client.op(kind, args, project, run_id, confirm_token=outcome["confirm_token"],
                                               op_id=op_id)
        except ApiError as exc:
            if reraise:
                raise
            self.notify(self._explain(exc), severity="error")
            return None
        except ConnectionLost:
            self._set_connected(False)
            self.notify("The daemon did not answer, so nothing changed.", severity="error")
            return None
        self.mark_dirty()
        return outcome

    def _explain(self, exc):
        if exc.code == "critique_errors":
            return "Start is blocked: " + "; ".join(e["message"] for e in exc.details["critique"]["errors"])
        return exc.message

    # --- refresh ---

    def mark_dirty(self):
        self.dirty = True

    async def _tick(self):
        self._idle += REFRESH_SECONDS
        if self._idle >= IDLE_REFRESH_SECONDS:
            self.dirty = True  # elapsed times move with no event
        if self.dirty and not self._refreshing:
            self.dirty = False
            self._idle = 0.0
            self._refreshing = True
            self.run_worker(self._refresh(), exclusive=False, name="refresh")

    async def _refresh(self):
        try:
            await self._refresh_topbar()
            await self._pane().load()
            self._set_connected(True)
        except ConnectionLost:
            self._set_connected(False)
        except ApiError as exc:
            self.notify(exc.message, severity="error")
        except NoMatches:
            pass  # the screen is closing under this refresh
        finally:
            self._refreshing = False

    async def _refresh_topbar(self):
        state = await self.client.get("/v1/daemon")
        usage = await self.client.get("/v1/usage")
        window = ""
        if usage:
            used = usage[0]["used_fraction"]
            resets = calendar.timegm(time.strptime(usage[0]["resets_at"], "%Y-%m-%dT%H:%M:%SZ"))
            window = f"window {'unknown' if used is None else f'{used:.0%}'}, resets {time.strftime('%H:%M', time.localtime(resets))}"
        where = " ".join(x for x in (self.project, self.run_id) if x)
        parked = state["state"] == "parked"
        current = self.main.query_one("#panes", ContentSwitcher).current.removesuffix("-pane")
        tabs = []
        for key, name in (("p", "projects"), ("b", "brief"), ("k", "backlog"), ("r", "run")):
            tabs += [paint(key, "accent"), paint(f" {name}   ", "text" if name == current else "dim", bold=name == current)]
        self.main.query_one("#topbar", Static).update(join(
            paint("springer", "accent", bold=True), paint(f"  {where}" if where else "", "system"), "     ", *tabs))
        self.main.query_one("#statusline", Static).update(join(
            paint("● ", "soft" if parked else "success"), paint(f"daemon {state['state']}", "dim"),
            paint(f"   {window}", "dim")))

    def _set_connected(self, connected):
        if connected != self.connected:
            self.connected = connected
            # A query and not query_one: this runs inside except clauses, and a screen
            # closing under it must not raise from there.
            self.main.query("#banner").set_class(not connected, "lost")
            if connected:
                self.mark_dirty()

    async def _watch(self, path, resume=False):
        """Follow a stream for the life of the app. Any frame means something changed,
        and a drop reconnects at the last cursor, so nothing is missed."""
        cursor = None
        while True:
            try:
                kwargs = {"params": {"after": cursor}} if resume and cursor else {}
                async for event, _, frame_id in self.client.stream(path, **kwargs):
                    self._set_connected(True)
                    if frame_id:
                        cursor = frame_id
                    if event not in QUIET_EVENTS:
                        self.mark_dirty()
                await asyncio.sleep(RETRY_SECONDS)
            except ConnectionLost:
                self._set_connected(False)
                await asyncio.sleep(RETRY_SECONDS)
            except ApiError:
                await asyncio.sleep(RETRY_SECONDS)
            except NoMatches:
                return  # the screen is closing under this stream

    # --- chat line ---

    def on_input_submitted(self, event):
        if event.input.id != "chat" or not event.value.strip():
            return
        message = event.value
        event.input.value = ""
        self.run_worker(self._chat(message))

    async def _chat(self, message):
        log = self.main.query_one("#chat-log", Static)
        log.add_class("shown")
        try:
            async for name, data, _ in self.client.stream("/v1/chat", method="POST",
                                                          json={"message": message, "project": self.project}):
                if name == "text":
                    log.update(data["text"])
        except ConnectionLost:
            self._set_connected(False)
