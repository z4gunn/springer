"""The HTTP and SSE surface. See docs/harness/api-contract.md, which this implements."""

import asyncio
import html
import json
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..build import build_id
from ..check.critique import critique
from ..common import iso, parse_iso, read_json
from ..errors import HarnessError, NotFound
from ..state.backlog import BacklogStore
from ..state.ledger import CursorInvalid
from ..state.projection import rebuild
from ..state.sessions import TERMINAL
from . import models as m
from .operations import Operations, catalog_view

API_VERSION = "v1"
HARNESS_VERSION = "0.0.0"
LOOPBACK = {"127.0.0.1", "localhost", "::1", "[::1]"}
SSE_POLL_SECONDS = 0.2
HEARTBEAT_SECONDS = 15
DESIGN_CODE_SECONDS = 60
DESIGN_COOKIE_SECONDS = 8 * 3600
FAILURE_CLASSES = ("defect", "transient", "environment", "context", "question", "blocked")


def _host(header):
    if header.startswith("["):
        return header.split("]")[0] + "]"
    return header.split(":")[0]


def _error(status, code, message, details=None):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message,
                                                               "details": details or {}}})


def _frame(event, data, event_id=None):
    head = f"id: {event_id}\n" if event_id else ""
    return f"{head}event: {event}\ndata: {json.dumps(data)}\n\n"


def _design_message(status, title, body):
    """The design surface is the one thing a person reads in a browser, so it answers
    in a page and not in the API's JSON."""
    return HTMLResponse(status_code=status, content=(
        "<!doctype html><meta charset=utf-8><title>Springer</title>"
        "<body style='background:#16171A;color:#E4DED2;font:16px/1.5 Menlo,monospace;padding:3rem;max-width:44rem'>"
        f"<h1 style='font-size:1.1rem'>{html.escape(title)}</h1><p style='color:#B7AE9E'>{html.escape(body)}</p>"))


def _page(items, cursor, limit):
    start = int(cursor) if cursor else 0
    end = start + limit
    return {"items": items[start:end], "next_cursor": str(end) if end < len(items) else None}


def create_app(daemon):
    app = FastAPI(title="Springer Harness API", version=API_VERSION)
    app.state.daemon = daemon
    app.state.heartbeat_seconds = HEARTBEAT_SECONDS
    operations = Operations(daemon)
    app.state.operations = operations
    daemon.operations = operations
    token = daemon.home.token()
    build = build_id()
    design_codes = {}
    design_cookies = {}

    @app.middleware("http")
    async def loopback_only(request: Request, call_next):
        """A web page in the local browser must not reach the API by DNS rebinding."""
        host = request.headers.get("host", "")
        if _host(host) not in LOOPBACK:
            return _error(403, "forbidden_host", "The Host header is not a loopback name.")
        origin = request.headers.get("origin")
        if origin and origin.split("://", 1)[-1] != host:
            return _error(403, "forbidden_host", "The Origin header is not this daemon.")
        return await call_next(request)

    @app.exception_handler(HarnessError)
    async def harness_error(_, exc):
        return _error(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_, exc):
        return _error(400, "invalid_args", "The request does not match the contract.",
                      {"errors": json.loads(json.dumps(exc.errors(), default=str))})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_, exc):
        code = {401: "unauthorized", 404: "not_found"}.get(exc.status_code, "internal")
        return _error(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def internal(_, exc):
        return _error(500, "internal", f"The daemon failed: {type(exc).__name__}")

    def auth(authorization: str | None = Header(default=None)):
        if authorization != f"Bearer {token}":
            raise StarletteHTTPException(401, "The token is missing or wrong.")

    secured = [Depends(auth)]

    # --- helpers over the run store ---

    def run_doc(engine):
        head = engine.ledger.head()
        doc = rebuild(engine.run_dir, engine.run_id, engine.ledger, engine.units, engine.gates, engine.cycles,
                      engine.now, engine.sessions, window=engine.window.read(), write=False)
        return head, doc["content"]

    def summary(slug, record):
        run_id = daemon.active_run(slug)
        front = {}
        store = daemon.brief(slug)
        if store.exists():
            front = store.load()[0]
        active = None
        if run_id:
            engine = daemon.engine(slug, run_id)
            _, content = run_doc(engine)
            active = {"run_id": run_id, "phase": content["active_phase"], "open_gates": len(content["open_gates"]),
                      "in_flight": len(content["in_flight"]), "paused": content["paused"],
                      "waiting_on": content["waiting_on"], "externally_held": bool(engine.lock.externally_held())}
        return {"slug": slug, "name": record["name"], "path": record["path"], "profile": front.get("profile"),
                "deploy": front.get("deploy"), "runtime_version": record.get("runtime_version"),
                "archived": record.get("archived", False), "active_run": active,
                "adopted": bool(record.get("adopted")), "lane": front.get("lane"), "settings": daemon.settings(slug),
                "adopted_brief_version": record.get("adopted_brief_version"),
                "has_design": (Path(record["path"]) / "docs" / "design" / "index.html").exists(),
                "hand_merge": [p for p in record.get("hand_merge") or [] if (Path(record["path"]) / p).exists()]}

    def gate_view(engine, gate):
        content = dict(gate["content"])
        context = dict(content.get("context") or {})
        context.pop("previous_brief", None)
        unit_id = context.get("unit_id")
        if unit_id:
            context["diff_path"] = (f"/v1/projects/{engine.project_slug}/runs/{engine.run_id}"
                                    f"/units/{unit_id}/diff")
        context.setdefault("design_session", False)
        context["age_seconds"] = int(engine.now() - parse_iso(content["opened_at"]))
        content["context"] = context
        return content

    # --- reads ---

    @app.get("/v1/health", response_model=m.Health)
    def health():
        return {"status": "ok", "api_version": API_VERSION, "harness_version": HARNESS_VERSION, "build": build}

    @app.get("/v1/daemon", response_model=m.DaemonView, dependencies=secured)
    def daemon_view():
        return {**daemon.state(), "started_at": iso(daemon.started_at), "degradations": list(daemon.degradations)}

    @app.get("/v1/usage", response_model=list[m.Open], dependencies=secured)
    def usage():
        return [daemon.window.read()]

    @app.get("/v1/operations/catalog", response_model=list[m.CatalogEntry], dependencies=secured)
    def catalog():
        return catalog_view()

    @app.get("/v1/audit", response_model=m.Page, dependencies=secured)
    def audit(project: str | None = None, cursor: str | None = None, limit: int = Query(100, ge=1, le=1000)):
        lines = [line for line in daemon.home.audit_lines() if project is None or line.get("project") == project]
        return _page(lines, cursor, limit)

    @app.get("/v1/projects", response_model=list[m.ProjectSummary], dependencies=secured)
    def projects():
        return [summary(slug, record) for slug, record in daemon.home.projects().items()]

    @app.get("/v1/projects/{slug}", response_model=m.ProjectSummary, dependencies=secured)
    def project(slug: str):
        return summary(slug, daemon.home.project(slug))

    @app.get("/v1/projects/{slug}/brief", response_model=m.BriefView, dependencies=secured)
    def brief(slug: str):
        return daemon.brief(slug).view(daemon.started(slug))

    @app.get("/v1/projects/{slug}/brief/critique", response_model=m.Critique, dependencies=secured)
    def brief_critique(slug: str):
        front, sections = daemon.brief(slug).load()
        return critique(front, sections)

    @app.get("/v1/projects/{slug}/provisioning", response_model=list[m.ProvisioningItem], dependencies=secured)
    def provisioning(slug: str):
        for run_id in reversed(daemon.run_ids(slug)):
            items = read_json(daemon.project_path(slug) / "runs" / run_id / "provisioning.json")
            if items:
                return [{**i, "present": daemon.secrets.has(slug, i["secret_name"])} for i in items]
        return []

    @app.get("/v1/adopt/preview", response_model=m.Open, dependencies=secured)
    def adopt_preview(path: str):
        """What adopting the repository at path would read, derive, and write. Writes nothing."""
        from ..adopt import plan, public
        from ..daemon import expand_path
        target = expand_path(path)
        if not target.is_dir():
            raise NotFound(f"no directory at {path}")
        return public(plan(target))

    @app.get("/v1/projects/{slug}/history", response_model=m.Open, dependencies=secured)
    def project_history(slug: str):
        daemon.home.project(slug)
        return daemon.history(slug)

    @app.get("/v1/projects/{slug}/runs", response_model=list[m.RunSummary], dependencies=secured)
    def runs(slug: str):
        out = []
        for run_id in reversed(daemon.run_ids(slug)):
            engine = daemon.engine(slug, run_id)
            _, content = run_doc(engine)
            out.append({"run_id": run_id, "kind": daemon.run_brief(slug, run_id).get("content", {}).get("kind", "build"),
                        "phase": content["active_phase"], "complete": engine.cycles.is_complete(),
                        "paused": content["paused"]})
        return out

    run_path = "/v1/projects/{slug}/runs/{run_id}"

    @app.get(run_path, response_model=m.Open, dependencies=secured)
    def run(slug: str, run_id: str):
        engine = daemon.engine(slug, run_id)
        head, content = run_doc(engine)
        return {**content, "as_of": head, "complete": engine.cycles.is_complete()}

    @app.get(run_path + "/backlog", response_model=m.BacklogView, dependencies=secured)
    def backlog(slug: str, run_id: str):
        engine = daemon.engine(slug, run_id)
        return BacklogStore(engine.run_dir).view(engine.units, engine.ledger.head())

    @app.get(run_path + "/units", response_model=m.Page, dependencies=secured)
    def units(slug: str, run_id: str, state: str | None = None, cursor: str | None = None,
              limit: int = Query(100, ge=1, le=1000)):
        engine = daemon.engine(slug, run_id)
        rows = []
        for unit_id in engine.units.ids():
            record = engine.units.state(unit_id)
            if state is None or record["state"] == state:
                spec = engine.units.spec(unit_id)
                rows.append({"unit_id": unit_id, "state": record["state"], "agent": spec["agent"],
                             "model_tier": spec["model_tier"], "retries_spent": record["retries_spent"],
                             "pr": record["pr"], "entered_at": record["entered_at"]})
        return _page(rows, cursor, limit)

    @app.get(run_path + "/units/{unit_id}", response_model=m.Open, dependencies=secured)
    def unit(slug: str, run_id: str, unit_id: str):
        engine = daemon.engine(slug, run_id)
        spec = engine.units.spec(unit_id)
        unit_dir = engine.units.unit_dir(unit_id)
        return {"spec": spec, "state": engine.units.state(unit_id), "risk": read_json(unit_dir / "risk.json"),
                "sessions": engine.sessions(unit_id).all(), "retrieved": read_json(unit_dir / "retrieved.json")}

    @app.get(run_path + "/units/{unit_id}/diff", response_class=PlainTextResponse, dependencies=secured)
    def diff(slug: str, run_id: str, unit_id: str):
        state = daemon.engine(slug, run_id).units.state(unit_id)
        if not state["pr"]:
            raise NotFound(f"{unit_id} has no PR")
        return PlainTextResponse(daemon.host_for(slug).diff(slug, state["pr"]["number"]), media_type="text/x-diff")

    @app.get(run_path + "/gates", response_model=m.Page, dependencies=secured)
    def gates(slug: str, run_id: str, state: str | None = Query(None, pattern="^(open|answered)$"),
              digest: bool | None = None, cursor: str | None = None, limit: int = Query(100, ge=1, le=1000)):
        engine = daemon.engine(slug, run_id)
        rows = []
        for gate in engine.gates.all():
            content = gate["content"]
            answered = content["response"] is not None
            if (state == "open" and answered) or (state == "answered" and not answered):
                continue
            if digest is not None and content["digest"] != digest:
                continue
            rows.append(gate_view(engine, gate))
        return _page(rows, cursor, limit)

    @app.get(run_path + "/gates/{gate_id}", response_model=m.Open, dependencies=secured)
    def gate(slug: str, run_id: str, gate_id: str):
        engine = daemon.engine(slug, run_id)
        return gate_view(engine, engine.gates.get(gate_id))

    @app.get(run_path + "/metrics", response_model=m.Metrics, dependencies=secured)
    def metrics(slug: str, run_id: str):
        engine = daemon.engine(slug, run_id)
        dispatches, passed, mix = 0, 0, {}
        for entry in engine.ledger.read():
            line = entry.line
            if line.get("event") == "session_started":
                dispatches += 1
            elif line.get("event") == "product_check" and line.get("result") == "pass":
                passed += 1
            elif line.get("event") == "unit_state":
                cause = line.get("reason", "").split(":")[0]
                if cause in FAILURE_CLASSES:
                    mix[cause] = mix.get(cause, 0) + 1
        spend = sum(s["cost_usd_list_price"] for u in engine.units.ids() for s in engine.sessions(u).all())
        cap = (daemon.brief(slug).load()[0].get("budget") or {}).get("daily_cap_usd") if daemon.brief(slug).exists() else None
        return {"product_checks_per_100_dispatches": round(100 * passed / dispatches, 2) if dispatches else 0,
                "failure_class_mix": mix, "dispatches": dispatches, "list_price_spend_usd": round(spend, 4),
                "daily_cap_usd": cap}

    # --- event streams ---

    async def run_frames(request, engine, after):
        cursor = after
        last_beat = asyncio.get_running_loop().time()
        while not await request.is_disconnected():
            try:
                entries = list(engine.ledger.read(after=cursor))
            except CursorInvalid:
                cursor = engine.ledger.head()
                yield _frame("resync", {"cursor": cursor})
                continue
            for entry in entries:
                cursor = entry.cursor
                yield _frame(entry.line.get("event", "unknown"), entry.line, entry.cursor)
            now = asyncio.get_running_loop().time()
            if now - last_beat >= app.state.heartbeat_seconds:
                last_beat = now
                yield _frame("heartbeat", {})
            await asyncio.sleep(SSE_POLL_SECONDS)

    @app.get(run_path + "/events", dependencies=secured)
    def run_events(request: Request, slug: str, run_id: str, after: str | None = None,
                   last_event_id: str | None = Header(default=None)):
        engine = daemon.engine(slug, run_id)
        return StreamingResponse(run_frames(request, engine, last_event_id or after), media_type="text/event-stream")

    async def daemon_frames(request):
        positions, statuses, state, window = {}, {}, None, None
        last_beat = asyncio.get_running_loop().time()
        first = True
        while not await request.is_disconnected():
            current = daemon.state()
            if current != state:
                state = current
                if not first:
                    yield _frame("daemon_state", current)
            record = daemon.window.read()
            sample = (record["used_fraction"], record["resets_at"])
            if sample != window:
                window = sample
                if not first:
                    yield _frame("window_sample", {"provider": record["provider"], "used_fraction": sample[0],
                                                   "resets_at": sample[1]})
            for slug, project_record in daemon.home.projects().items():
                view = summary(slug, project_record)
                if statuses.get(slug) != view:
                    statuses[slug] = view
                    if not first:
                        yield _frame("project_status", view)
                for run_id in daemon.run_ids(slug):
                    engine = daemon.engine(slug, run_id)
                    key = (slug, run_id)
                    if key not in positions:
                        positions[key] = engine.ledger.head()
                        continue
                    for entry in list(engine.ledger.read(after=positions[key])):
                        positions[key] = entry.cursor
                        name = entry.line.get("event")
                        if name == "gate_opened":
                            yield _frame(name, {"project": slug, "run_id": run_id, "gate_id": entry.line["gate_id"],
                                                "level": entry.line["level"]})
                        elif name == "gate_answered":
                            yield _frame(name, {"project": slug, "run_id": run_id, "gate_id": entry.line["gate_id"]})
            first = False
            now = asyncio.get_running_loop().time()
            if now - last_beat >= app.state.heartbeat_seconds:
                last_beat = now
                yield _frame("heartbeat", {})
            await asyncio.sleep(SSE_POLL_SECONDS)

    @app.get("/v1/events", dependencies=secured)
    def events(request: Request):
        return StreamingResponse(daemon_frames(request), media_type="text/event-stream")

    async def session_frames(request, store, session_id, after):
        path = store.dir(session_id) / "stream.jsonl"
        index = after
        while not await request.is_disconnected():
            lines = path.read_text().splitlines() if path.exists() else []
            for raw in lines[index:]:
                index += 1
                yield _frame("stream", json.loads(raw), str(index))
            if store.get(session_id)["state"] in TERMINAL:
                return
            await asyncio.sleep(SSE_POLL_SECONDS)

    @app.get(run_path + "/units/{unit_id}/sessions/{session_id}/stream", dependencies=secured)
    def session_stream(request: Request, slug: str, run_id: str, unit_id: str, session_id: str, after: int = 0):
        store = daemon.engine(slug, run_id).sessions(unit_id)
        if store.get(session_id) is None:
            raise NotFound(f"no session {session_id}")
        return StreamingResponse(session_frames(request, store, session_id, after), media_type="text/event-stream")

    # --- writes ---

    @app.post("/v1/operations", response_model=m.OperationResponse, response_model_exclude_none=True,
              dependencies=secured)
    def apply_operation(body: m.OperationRequest):
        return operations.apply(body.op_id, body.type, body.project, body.run_id, body.args, body.confirm_token, "tui")

    async def chat_frames(session_id):
        yield _frame("text", {"session_id": session_id, "text": "The chat agent is not built yet."})
        yield _frame("done", {"session_id": session_id})

    @app.post("/v1/chat", dependencies=secured)
    def chat(body: m.ChatRequest):
        return StreamingResponse(chat_frames(body.session_id or secrets.token_urlsafe(8)), media_type="text/event-stream")

    # --- design review surface ---

    @app.get("/v1/projects/{slug}/design-session", response_model=m.DesignSession, dependencies=secured)
    def design_session(slug: str, request: Request):
        daemon.home.project(slug)
        code = secrets.token_urlsafe(24)
        expires = daemon.now() + DESIGN_CODE_SECONDS
        design_codes[code] = (slug, expires)
        return {"url": f"{str(request.base_url).rstrip('/')}/design/{slug}/?code={code}", "expires_at": iso(expires)}

    def design_file(slug, rel):
        root = (daemon.project_path(slug) / "docs" / "design").resolve()
        target = (root / rel).resolve()
        if target != root and root not in target.parents:
            return _design_message(404, "Not a design file", "This page only serves the project's docs/design directory.")
        if not root.is_dir():
            return _design_message(404, f"No design files for {slug} yet",
                                   "The design agent writes its mockups to docs/design, and none are there. "
                                   "This page shows them once they exist.")
        if target.is_dir():
            index = target / "index.html"
            if index.exists():
                return FileResponse(index)
            names = sorted(p.name + ("/" if p.is_dir() else "") for p in target.iterdir())
            return PlainTextResponse("\n".join(names))
        if not target.is_file():
            return _design_message(404, "That file is not there", f"{rel} is not in {slug}'s docs/design directory.")
        return FileResponse(target)

    @app.get("/design/{slug}/{rel:path}", include_in_schema=False)
    def design(slug: str, rel: str, request: Request, code: str | None = None):
        if code is not None:
            record = design_codes.pop(code, None)
            if record is None or record[0] != slug or daemon.now() > record[1]:
                return _design_message(401, "This link has expired", "Press o on the gate in the TUI for a fresh one.")
            session = secrets.token_urlsafe(24)
            design_cookies[session] = (slug, daemon.now() + DESIGN_COOKIE_SECONDS)
            response = RedirectResponse(f"/design/{slug}/{rel}", status_code=303)
            response.set_cookie("springer_design", session, max_age=DESIGN_COOKIE_SECONDS, path=f"/design/{slug}/",
                                httponly=True, samesite="strict")
            return response
        record = design_cookies.get(request.cookies.get("springer_design", ""))
        if record is None or record[0] != slug or daemon.now() > record[1]:
            return _design_message(401, "Open this from the TUI", "Press o on the gate in the TUI to sign this browser in.")
        return design_file(slug, rel)

    return app


def export_openapi(app):
    """The committed contract: paths and component schemas, sorted."""
    schema = app.openapi()
    schema.pop("info", None)
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"

