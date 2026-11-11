"""The API contract against the real daemon with the mock provider behind it. A
meta-test fails when a catalog operation or a GET path has no test, so the contract
cannot grow past its coverage. See Conformance in docs/harness/api-contract.md."""

import contextlib
import io
import json
import sys
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path

from harness_support import HAVE_JSONSCHEMA, Clock, git_project, schema_errors

try:
    import httpx
    import uvicorn
    from fastapi.testclient import TestClient
    HAVE_API = True
except ImportError:
    HAVE_API = False

if HAVE_API:
    from springer_harness.api.app import create_app
    from springer_harness.api.export import OPENAPI_PATH, current
    from springer_harness.api.operations import CATALOG
    from springer_harness.daemon import Daemon
    from springer_harness.providers.mock import MockProvider, MockSourceHost
    from springer_harness.providers.mock_scenario import demo_planner_factory, demo_script
    from springer_harness.providers.secrets import MemorySecrets
    from springer_harness.state.brief import BriefStore

GOOD_SECTIONS = {
    "Problem": "Freelancers lose track of invoices.",
    "Users": "- Fran: a freelancer",
    "Core flows": "### Send an invoice\nWho: Fran\nTrigger: The work is done.\n1. Write it\n2. Send it\nOutcome: The client has it.\nCritical: yes\n",
    "Non-goals": "None yet.",
    "Success criteria": "Fran sends one invoice.",
}
BACKLOG = {"epics": [{"epic_id": "E-1", "title": "Invoice", "critical": True, "features": [
    {"feature_id": "F-1", "title": "Editor", "mvp": True, "deferred": False, "stories": [
        {"story_id": "S-1", "title": "Draft", "wave": 1, "unit_ids": [], "pr": None, "depends_on": []},
        {"story_id": "S-2", "title": "Send", "wave": 1, "unit_ids": [], "pr": None, "depends_on": ["S-1"]}]},
    {"feature_id": "F-2", "title": "Reports", "mvp": False, "deferred": False, "stories": []}]}],
    "unknowns": [{"unknown_id": "UK-1", "question": "Which currency?", "answer": None}]}


def op_id():
    return str(uuid.uuid4())


@unittest.skipUnless(HAVE_API, "the harness API dependencies are not installed")
class ApiCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clock = Clock(time.time())
        self.host = MockSourceHost()
        self.secrets = MemorySecrets()
        self.daemon = Daemon(self.root / "home", MockProvider(demo_script()), self.host, demo_planner_factory(),
                             self.secrets, self.clock, local_host=self.host)
        self.app = create_app(self.daemon)
        self.token = self.daemon.home.token()
        self.client = TestClient(self.app, base_url="http://127.0.0.1", raise_server_exceptions=False,
                                 headers={"Authorization": f"Bearer {self.token}"})
        self.project_path = git_project(self.root / "acme")
        self.daemon.home.save_project("acme", {"slug": "acme", "name": "Acme", "path": str(self.project_path),
                                               "archived": False, "runtime_version": "abc1234"})
        store = BriefStore(self.project_path)
        store.create("Acme")
        version = 1
        for name, body in GOOD_SECTIONS.items():
            version = store.update_section(name, body, version)
        self.version = version

    def op(self, kind, args=None, project="acme", run_id=None, token=None, identifier=None, expect=200):
        response = self.client.post("/v1/operations", json={
            "op_id": identifier or op_id(), "type": kind, "project": project, "run_id": run_id,
            "args": args or {}, "confirm_token": token})
        self.assertEqual(response.status_code, expect, response.text)
        return response.json()

    def confirmed(self, kind, args=None, project="acme", run_id=None):
        """Walk the confirmation flow the way a client does."""
        first = self.op(kind, args, project, run_id)
        self.assertEqual(first["status"], "needs_confirmation", first)
        self.assertTrue(first["preview"]["summary"])
        return self.op(kind, args, project, run_id, token=first["confirm_token"])

    def start(self):
        return self.confirmed("run.start", {"base_version": self.version})["result"]["run_id"]

    def run_path(self, run_id):
        return f"/v1/projects/acme/runs/{run_id}"

    def get(self, path, **params):
        response = self.client.get(path, params=params)
        self.assertEqual(response.status_code, 200, f"{path}: {response.text}")
        return response.json()

    def tick(self, count=1):
        for _ in range(count):
            self.daemon.tick_all()

    def tick_to_unit(self, run_id):
        for _ in range(10):
            self.tick()
            units = self.get(self.run_path(run_id) + "/units")["items"]
            if units:
                return units[0]
        self.fail("no unit appeared")

    def backlog_file(self):
        return self.daemon.project_path("acme") / "runs" / "_backlog.json"

    def with_backlog(self, run_id):
        self.backlog_file().write_text(json.dumps(BACKLOG))

    def error(self, response, status, code):
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(response.json()["error"]["code"], code)


class SecurityTest(ApiCase):
    def test_no_token_and_a_wrong_token_are_refused(self):
        bare = TestClient(self.app, base_url="http://127.0.0.1")
        self.error(bare.get("/v1/projects"), 401, "unauthorized")
        self.error(bare.get("/v1/projects", headers={"Authorization": "Bearer nope"}), 401, "unauthorized")
        self.error(bare.post("/v1/operations", json={"op_id": "1", "type": "run.pause"}), 401, "unauthorized")

    def test_health_alone_needs_no_token(self):
        bare = TestClient(self.app, base_url="http://127.0.0.1")
        body = bare.get("/v1/health").json()
        self.assertEqual((body["status"], body["api_version"]), ("ok", "v1"))

    def test_a_foreign_host_is_refused_even_with_the_token(self):
        response = self.client.get("/v1/projects", headers={"Host": "evil.example"})
        self.error(response, 403, "forbidden_host")

    def test_a_foreign_origin_is_refused_even_with_the_token(self):
        response = self.client.get("/v1/projects", headers={"Origin": "http://evil.example"})
        self.error(response, 403, "forbidden_host")
        response = self.client.get("/v1/projects", headers={"Host": "127.0.0.1:7337", "Origin": "http://127.0.0.1:7337"})
        self.assertEqual(response.status_code, 200)

    def test_the_token_file_is_owner_only(self):
        self.assertEqual(self.daemon.home.token_path.stat().st_mode & 0o777, 0o600)


class ReadsTest(ApiCase):
    def setUp(self):
        super().setUp()
        self.run_id = self.start()
        self.unit = self.tick_to_unit(self.run_id)
        self.with_backlog(self.run_id)
        design = self.project_path / "docs" / "design"
        design.mkdir(parents=True)
        (design / "index.html").write_text("<h1>mockup</h1>")
        (self.daemon.engine("acme", self.run_id).run_dir / "provisioning.json").write_text(json.dumps(
            [{"item_id": "stripe", "secret_name": "STRIPE_KEY", "needed_by": "skeleton"}]))
        self.gate = self.daemon.engine("acme", self.run_id).gates.open(
            "scope-review", "L3", [], "Move the line?", [{"option": "submit", "consequence": "Locks."}])["content"]

    def test_every_get_in_the_contract_answers(self):
        run = self.run_path(self.run_id)
        unit = self.unit["unit_id"]
        engine = self.daemon.engine("acme", self.run_id)
        state = engine.units.state(unit)
        engine.units.save({**state, "pr": {"number": 7, "branch": "b", "base": "main"}})
        self.tick()
        session = engine.units.state(unit)["sessions"][0]
        reads = {
            "/v1/health": "/v1/health", "/v1/daemon": "/v1/daemon", "/v1/usage": "/v1/usage",
            "/v1/operations/catalog": "/v1/operations/catalog", "/v1/audit": "/v1/audit",
            "/v1/projects": "/v1/projects", "/v1/projects/{slug}": "/v1/projects/acme",
            "/v1/projects/{slug}/brief": "/v1/projects/acme/brief",
            "/v1/projects/{slug}/brief/critique": "/v1/projects/acme/brief/critique",
            "/v1/projects/{slug}/provisioning": "/v1/projects/acme/provisioning",
            "/v1/projects/{slug}/design-session": "/v1/projects/acme/design-session",
            "/v1/projects/{slug}/runs": "/v1/projects/acme/runs",
            "/v1/projects/{slug}/history": "/v1/projects/acme/history",
            "/v1/adopt/preview": f"/v1/adopt/preview?path={self.project_path}",
            "/v1/projects/{slug}/runs/{run_id}": run, "/v1/projects/{slug}/runs/{run_id}/backlog": run + "/backlog",
            "/v1/projects/{slug}/runs/{run_id}/units": run + "/units",
            "/v1/projects/{slug}/runs/{run_id}/units/{unit_id}": f"{run}/units/{unit}",
            "/v1/projects/{slug}/runs/{run_id}/units/{unit_id}/diff": f"{run}/units/{unit}/diff",
            "/v1/projects/{slug}/runs/{run_id}/gates": run + "/gates",
            "/v1/projects/{slug}/runs/{run_id}/gates/{gate_id}": f"{run}/gates/{self.gate['checkpoint_id']}",
            "/v1/projects/{slug}/runs/{run_id}/metrics": run + "/metrics",
            "/v1/projects/{slug}/runs/{run_id}/feed": run + "/feed",
        }
        streams = {"/v1/events", "/v1/projects/{slug}/runs/{run_id}/events",
                   "/v1/projects/{slug}/runs/{run_id}/units/{unit_id}/sessions/{session_id}/stream"}
        schema = json.loads(OPENAPI_PATH.read_text())
        gets = {path for path, methods in schema["paths"].items() if "get" in methods}
        self.assertEqual(gets, set(reads) | streams, "a GET path has no test")
        for template, path in reads.items():
            with self.subTest(template):
                self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertTrue(session)

    def test_project_summary_shows_the_active_run(self):
        body = self.get("/v1/projects")[0]
        self.assertEqual(body["active_run"]["run_id"], self.run_id)
        self.assertEqual(body["profile"], "brochure")
        self.assertEqual(self.get("/v1/projects/acme")["slug"], "acme")

    def test_brief_view_splits_facts_and_sections(self):
        body = self.get("/v1/projects/acme/brief")
        self.assertTrue(body["started"])
        self.assertEqual(body["derived"]["profile"], "brochure")
        problem = next(s for s in body["sections"] if s["name"] == "Problem")
        self.assertEqual((problem["required"], problem["confidence"]), (True, "confirmed"))
        self.assertIn("A web product with no backend runs as brochure", body["derived"]["sentence"])

    def test_run_view_validates_as_run_state_plus_its_additions(self):
        body = self.get(self.run_path(self.run_id))
        self.assertTrue(body["as_of"].startswith("c-"))
        self.assertIn("paused", body)
        self.assertEqual(body["in_flight"][0]["last_tool_call"] in ("Read", "Bash", None), True)

    @unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed in this interpreter")
    def test_records_served_keep_their_schema(self):
        run = self.run_path(self.run_id)
        unit = self.get(f"{run}/units/{self.unit['unit_id']}")
        self.assertEqual(schema_errors("unit-spec-v1", unit["spec"]), [])
        self.assertEqual(schema_errors("unit-state-v1", unit["state"]), [])
        for session in unit["sessions"]:
            self.assertEqual(schema_errors("session-v1", session), [])
        for record in self.get("/v1/usage"):
            self.assertEqual(schema_errors("usage-window-v1", record), [])

    def test_a_read_writes_nothing(self):
        engine = self.daemon.engine("acme", self.run_id)
        state_file = engine.run_dir / "run-state.json"
        before = (state_file.stat().st_mtime_ns, engine.ledger.head())
        self.get(self.run_path(self.run_id))
        self.get("/v1/projects")
        self.assertEqual((state_file.stat().st_mtime_ns, engine.ledger.head()), before)

    def test_backlog_view_takes_its_column_from_the_units(self):
        run = self.run_path(self.run_id)
        backlog = json.loads(json.dumps(BACKLOG))
        backlog["epics"][0]["features"][0]["stories"][0]["unit_ids"] = [self.unit["unit_id"]]
        self.backlog_file().write_text(json.dumps(backlog))
        story = self.get(run + "/backlog")["epics"][0]["features"][0]["stories"][0]
        self.assertIn(story["column"], ("in_progress", "done", "ready", "in_review"))

    def test_backlog_before_it_exists_is_not_generated(self):
        self.backlog_file().unlink()
        body = self.get(self.run_path(self.run_id) + "/backlog")
        self.assertEqual((body["state"], body["epics"]), ("not_generated", []))

    def test_gate_filters_and_context(self):
        run = self.run_path(self.run_id)
        items = self.get(run + "/gates", state="open")["items"]
        self.assertEqual(items[0]["checkpoint_id"], self.gate["checkpoint_id"])
        self.assertIn("age_seconds", items[0]["context"])
        self.assertEqual(self.get(run + "/gates", state="answered")["items"], [])
        self.assertEqual(self.get(run + "/gates", digest=True)["items"], [])

    def test_pagination_walks_every_item(self):
        run = self.run_path(self.run_id)
        engine = self.daemon.engine("acme", self.run_id)
        for _ in range(4):
            engine.gates.open("scope-review", "L3", [], "x", [{"option": "a", "consequence": "b"}])
        seen, cursor = [], None
        while True:
            page = self.get(run + "/gates", limit=2, **({"cursor": cursor} if cursor else {}))
            seen += page["items"]
            cursor = page["next_cursor"]
            if cursor is None:
                break
        self.assertEqual(len(seen), 5)

    def test_not_found_uses_the_error_shape(self):
        self.error(self.client.get("/v1/projects/nope"), 404, "not_found")
        self.error(self.client.get("/v1/projects/acme/runs/nope"), 404, "not_found")
        self.error(self.client.get(self.run_path(self.run_id) + "/units/U-9999"), 404, "not_found")
        self.error(self.client.get(self.run_path(self.run_id) + "/gates/G-9999"), 404, "not_found")

    def test_provisioning_never_shows_a_value(self):
        items = self.get("/v1/projects/acme/provisioning")
        self.assertEqual((items[0]["secret_name"], items[0]["present"]), ("STRIPE_KEY", False))

    def test_design_page_needs_its_code_and_stays_inside_the_directory(self):
        (self.project_path / "docs" / "secret.txt").write_text("nope")
        bare = TestClient(self.app, base_url="http://127.0.0.1", follow_redirects=False)
        self.assertEqual(bare.get("/design/acme/").status_code, 401)
        url = self.get("/v1/projects/acme/design-session")["url"]
        path = url.split("127.0.0.1", 1)[-1]
        self.assertEqual(bare.get(path).status_code, 303)
        self.assertEqual(bare.get(path).status_code, 401, "a code is single use")
        self.assertIn("mockup", bare.get("/design/acme/").text)
        self.assertEqual(bare.get("/design/acme/..%2Fsecret.txt").status_code, 404)
        self.assertEqual(bare.get("/design/other/").status_code, 401, "the cookie is scoped to one project")

    def test_a_project_with_no_design_files_gets_a_page_that_says_so(self):
        shutil.rmtree(self.project_path / "docs" / "design")
        browser = TestClient(self.app, base_url="http://127.0.0.1")
        url = self.get("/v1/projects/acme/design-session")["url"]
        response = browser.get(url.split("127.0.0.1", 1)[-1])
        self.assertEqual(response.status_code, 404)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("No design files for acme yet", response.text)
        self.assertNotIn('"error"', response.text)

    def test_design_refusals_are_pages_a_person_can_read(self):
        bare = TestClient(self.app, base_url="http://127.0.0.1")
        for path, words in (("/design/acme/", "Open this from the TUI"), ("/design/acme/?code=nope", "expired")):
            response = bare.get(path)
            self.assertEqual(response.status_code, 401)
            self.assertIn("text/html", response.headers["content-type"])
            self.assertIn(words, response.text)

    def test_a_missing_file_name_cannot_inject_into_the_page(self):
        browser = TestClient(self.app, base_url="http://127.0.0.1")
        browser.get(self.get("/v1/projects/acme/design-session")["url"].split("127.0.0.1", 1)[-1])
        response = browser.get("/design/acme/<script>alert(1)</script>")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("<script>", response.text)

    def test_the_design_page_refuses_writes(self):
        bare = TestClient(self.app, base_url="http://127.0.0.1")
        self.assertEqual(bare.post("/design/acme/index.html").status_code, 405)




class OperationCatalogTest(ApiCase):
    """One test per catalog entry, named in COVERED. See the meta-test below."""

    def test_project_configure_sets_the_ci_signal(self):
        out = self.confirmed("project.configure", {"source_host": "github", "ci_signal": "self-hosted-actions"})
        self.assertEqual(out["result"]["settings"], {"ci_signal": "self-hosted-actions", "source_host": "github"})
        self.assertEqual(self.get("/v1/projects/acme")["settings"]["ci_signal"], "self-hosted-actions")
        bad = self.op("project.configure", {"ci_signal": "jenkins"}, expect=400)
        self.assertIn("ci_signal", json.dumps(bad))

    def configure_refused(self, args, status, code):
        first = self.op("project.configure", args)
        response = self.client.post("/v1/operations", json={
            "op_id": op_id(), "type": "project.configure", "project": "acme", "run_id": None, "args": args,
            "confirm_token": first.get("confirm_token")})
        self.error(response, status, code)

    def test_a_project_is_local_until_it_opts_into_github(self):
        self.assertEqual(self.daemon.settings("acme"), {"ci_signal": "receipts", "source_host": "local"})
        self.assertIs(self.daemon.host_for("acme"), self.daemon.local_host)
        self.configure_refused({"ci_signal": "both"}, 400, "invalid_args")
        self.confirmed("project.configure", {"source_host": "github"})
        self.assertIs(self.daemon.host_for("acme"), self.daemon.source_host)

    def test_the_source_host_does_not_change_under_a_run(self):
        self.start()
        self.configure_refused({"source_host": "github"}, 409, "illegal_transition")
        self.confirmed("project.configure", {"ci_signal": "receipts"})

    def run_started(self):
        run_id = self.start()
        self.unit = self.tick_to_unit(run_id)
        self.with_backlog(run_id)
        return run_id

    def test_run_archive_restore_and_prune(self):
        old = self.project_path / "runs" / "old"
        old.mkdir(parents=True)
        (old / "notes.json").write_text("{}\n")
        env = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
        subprocess.run(["git", "-C", str(self.project_path), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.project_path), *env, "commit", "-q", "-m", "old"], check=True)
        self.op("project.archive_run", {"run_id": "old"})
        self.op("project.restore_run", {"run_id": "old"})
        self.assertEqual(self.daemon.archived_runs("acme"), [])
        self.op("project.archive_run", {"run_id": "old"})
        self.assertEqual(self.confirmed("project.prune_run", {"run_id": "old"})["result"]["removed"], 1)
        self.assertFalse(old.exists())

    def test_project_create_and_archive(self):
        target = self.root / "fresh"
        body = self.confirmed("project.create", {"name": "Fresh App", "path": str(target), "mode": "new"}, project=None)
        self.assertEqual(body["result"]["project"], "fresh-app")
        self.assertTrue((target / ".claude" / "skills").is_dir())
        self.assertTrue((target / "docs" / "brief.md").exists())
        self.assertEqual(self.get("/v1/projects/fresh-app")["name"], "Fresh App")
        self.confirmed("project.archive", project="fresh-app")
        self.assertTrue(self.get("/v1/projects/fresh-app")["archived"])

    def test_project_create_adopts_an_existing_repository(self):
        target = git_project(self.root / "existing")
        self.confirmed("project.create", {"name": "Existing", "path": str(target), "mode": "adopt"}, project=None)
        self.assertTrue((target / ".claude" / "springer-manifest.json").exists())

    def test_expand_path(self):
        from springer_harness.daemon import expand_path
        home = Path.home()
        self.assertEqual(expand_path("~/Repos/app"), home / "Repos/app")
        self.assertEqual(expand_path("  ~Repos/app "), home / "Repos/app", "no user is named Repos")
        self.assertEqual(expand_path("~"), home)
        self.assertEqual(expand_path("/srv/app"), Path("/srv/app"))
        self.assertFalse(expand_path("rel/app").is_absolute())

    def test_project_create_refuses_a_relative_path_and_a_duplicate(self):
        first = self.op("project.create", {"name": "Acme", "path": "/tmp/x", "mode": "new"}, project=None)
        self.op("project.create", {"name": "Acme", "path": "/tmp/x", "mode": "new"}, project=None,
                token=first["confirm_token"], expect=400)
        first = self.op("project.create", {"name": "New", "path": "rel/x", "mode": "new"}, project=None)
        self.op("project.create", {"name": "New", "path": "rel/x", "mode": "new"}, project=None,
                token=first["confirm_token"], expect=400)

    def test_archive_refuses_a_project_with_a_run_in_progress(self):
        self.start()
        first = self.op("project.archive")
        self.op("project.archive", token=first["confirm_token"], expect=409)

    def test_brief_update_section_before_start_needs_no_confirmation(self):
        body = self.op("brief.update_section", {"section": "Glossary", "body": "Invoice: a bill.",
                                                "base_version": self.version})
        self.assertEqual(body["status"], "applied")
        self.assertEqual(body["result"]["version"], self.version + 1)

    def test_a_stale_base_version_is_refused(self):
        body = self.op("brief.update_section", {"section": "Problem", "body": "x", "base_version": 1}, expect=409)
        self.assertEqual(body["error"]["code"], "stale_version")
        self.assertEqual(body["error"]["details"]["current_version"], self.version)

    def test_brief_update_facts_recomputes_the_derived_profile(self):
        self.op("brief.update_facts", {"facts": {"payments": "subscription"}, "base_version": self.version})
        self.assertEqual(self.get("/v1/projects/acme/brief")["derived"]["profile"], "saas")

    def test_brief_update_facts_refuses_an_unknown_fact(self):
        self.op("brief.update_facts", {"facts": {"nonsense": 1}, "base_version": self.version}, expect=400)

    def test_an_edit_after_start_confirms_and_opens_a_scope_change_gate_that_can_discard(self):
        run_id = self.start()
        before = self.get("/v1/projects/acme/brief")
        args = {"section": "Problem", "body": "Changed.", "base_version": before["version"]}
        body = self.confirmed("brief.update_section", args)
        gate_id = body["result"]["gate_id"]
        changed = next(s for s in self.get("/v1/projects/acme/brief")["sections"] if s["name"] == "Problem")
        self.assertEqual(changed["body"], "Changed.")
        self.op("gate.answer", {"gate_id": gate_id, "option": "discard"}, run_id=run_id)
        restored = next(s for s in self.get("/v1/projects/acme/brief")["sections"] if s["name"] == "Problem")
        self.assertEqual(restored["body"], GOOD_SECTIONS["Problem"])

    def test_an_applied_brief_change_is_committed(self):
        """Left in the working tree, it reached no unit worktree and refused every local merge."""
        run_id = self.start()
        version = self.get("/v1/projects/acme/brief")["version"]
        body = self.confirmed("brief.update_section", {"section": "Problem", "body": "Changed.", "base_version": version})
        self.op("gate.answer", {"gate_id": body["result"]["gate_id"], "option": "apply"}, run_id=run_id)
        git = lambda *a: subprocess.run(["git", "-C", str(self.project_path), *a], capture_output=True, text=True).stdout
        self.assertEqual(git("status", "--porcelain", "--", "docs/brief.md"), "")
        self.assertIn("Changed.", git("show", "HEAD:docs/brief.md"))
        self.assertIn("applied at G-", git("log", "-1", "--format=%s"))

    def test_brief_confirm_section_clears_proposed(self):
        store = BriefStore(self.project_path)
        front, sections = store.load()
        front["proposed"] = ["Users"]
        store._write(front, sections)
        version = self.get("/v1/projects/acme/brief")["version"]
        section = next(s for s in self.get("/v1/projects/acme/brief")["sections"] if s["name"] == "Users")
        self.assertEqual(section["confidence"], "proposed")
        self.op("brief.confirm_section", {"section": "Users", "base_version": version})
        section = next(s for s in self.get("/v1/projects/acme/brief")["sections"] if s["name"] == "Users")
        self.assertEqual(section["confidence"], "confirmed")

    def test_brief_run_discovery_returns_accepted_and_runs(self):
        body = self.confirmed("brief.run_discovery", {"sections": ["Users"]})
        self.assertEqual(body["status"], "accepted")
        run_id = body["result"]["run_id"]
        self.assertFalse(self.get("/v1/projects/acme/brief")["started"], "Discovery is not the build")
        self.assertEqual(self.tick_to_unit(run_id)["agent"], "spgr-agent-discovery")

    def test_brief_dismiss_recommendation(self):
        store = BriefStore(self.project_path)
        front, sections = store.load()
        front["recommendation"] = {"verdict": "go", "summary": "Do it.", "dismissed": False}
        store._write(front, sections)
        self.op("brief.dismiss_recommendation")
        self.assertTrue(self.get("/v1/projects/acme/brief")["recommendation"]["dismissed"])

    def test_run_start_refuses_critique_errors(self):
        version = self.op("brief.update_section", {"section": "Core flows", "body": "### Bad\nWho: Nobody\n",
                                                   "base_version": self.version})["result"]["version"]
        first = self.op("run.start", {"base_version": version})
        body = self.op("run.start", {"base_version": version}, token=first["confirm_token"], expect=422)
        self.assertEqual(body["error"]["code"], "critique_errors")
        rules = {e["rule"] for e in body["error"]["details"]["critique"]["errors"]}
        self.assertEqual(rules, {"flow-without-outcome", "unknown-user", "no-critical-flow"})
        self.assertEqual(self.get("/v1/projects/acme/runs"), [])

    def test_prose_flows_block_the_start_and_say_what_to_write(self):
        version = self.op("brief.update_section", {"section": "Core flows", "body": "The user picks a diet, then we search.",
                                                   "base_version": self.version})["result"]["version"]
        critique = self.get("/v1/projects/acme/brief/critique")
        self.assertEqual([e["rule"] for e in critique["errors"]], ["flows-not-structured"])
        self.assertIn("### heading", critique["errors"][0]["message"])
        first = self.op("run.start", {"base_version": version})
        self.op("run.start", {"base_version": version}, token=first["confirm_token"], expect=422)
        self.assertEqual(self.get("/v1/projects/acme/runs"), [])

    def test_a_user_missing_from_prose_users_is_named(self):
        self.op("brief.update_section", {"section": "Users", "body": "Anyone who cooks.", "base_version": self.version})
        errors = self.get("/v1/projects/acme/brief/critique")["errors"]
        self.assertEqual(errors[0]["rule"], "unknown-user")
        self.assertIn("who is not in Users. Add them to Users.", errors[0]["message"])

    def test_run_start_commits_the_brief_so_a_worktree_can_read_it(self):
        self.start()
        shown = subprocess.run(["git", "-C", str(self.project_path), "show", "HEAD:docs/brief.md"],
                               capture_output=True, text=True)
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn("Freelancers", shown.stdout)

    def test_run_cancel_ends_the_run_and_a_new_one_can_start(self):
        self.daemon.provider.default.ticks = 50
        run_id = self.start()
        unit_id = self.tick_to_unit(run_id)["unit_id"]
        engine = self.daemon.engine("acme", run_id)
        gate_id = self._open_gate(run_id)
        self.confirmed("run.cancel", run_id=run_id)
        self.assertEqual(engine.units.state(unit_id)["state"], "cancelled")
        self.assertEqual(engine.sessions(unit_id).all()[-1]["outcome"], "killed")
        self.assertEqual(engine.gates.open_gates(), [])
        self.assertEqual(engine.gates.get(gate_id)["content"]["response"]["option"], "run cancelled")
        view = self.get(self.run_path(run_id))
        self.assertTrue(view["complete"])
        self.assertEqual(view["active_phase"], "cancelled")
        self.assertIsNone(self.get("/v1/projects/acme")["active_run"])
        version = self.get("/v1/projects/acme/brief")["version"]
        second = self.confirmed("run.start", {"base_version": version})["result"]["run_id"]
        self.assertNotEqual(second, run_id)
        spawned = len(self.daemon.provider.spawned)
        self.tick(3)
        self.assertEqual(engine.units.state(unit_id)["state"], "cancelled", "a cancelled run stays down")
        self.assertGreaterEqual(len(self.daemon.provider.spawned), spawned)

    @unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed in this interpreter")
    def test_a_cancelled_runs_records_keep_their_schema(self):
        run_id = self.start()
        self.tick_to_unit(run_id)
        self._open_gate(run_id)
        self.confirmed("run.cancel", run_id=run_id)
        engine = self.daemon.engine("acme", run_id)
        for gate in engine.gates.all():
            self.assertEqual(schema_errors("hil-checkpoint-v2", gate), [])
        for cycle in engine.cycles.all():
            self.assertEqual(schema_errors("pdca-cycle-v1", cycle), [])
        for line in (e.line for e in engine.ledger.read()):
            self.assertEqual(schema_errors("events-v1", line), [], line)

    def test_run_start_writes_the_derived_profile_where_a_worktree_will_see_it(self):
        target = self.root / "fresh"
        self.confirmed("project.create", {"name": "Fresh", "path": str(target), "mode": "new"}, project=None)
        self.assertIn("`small`", (target / "CLAUDE.md").read_text(), "scaffolded before the brief exists")
        store = BriefStore(target)
        version = store.load()[0]["brief_version"]
        for name, body in GOOD_SECTIONS.items():
            version = store.update_section(name, body, version)
        version = store.update_facts({"payments": "subscription"}, version)
        self.confirmed("run.start", {"base_version": version}, project="fresh")
        self.assertIn("Default profile for this project: `saas`.", (target / "CLAUDE.md").read_text())
        committed = subprocess.run(["git", "-C", str(target), "show", "HEAD:CLAUDE.md"], capture_output=True, text=True).stdout
        self.assertIn("`saas`", committed, "a worktree is cut from a commit")

    def test_run_start_opens_a_run(self):
        body = self.confirmed("run.start", {"base_version": self.version})
        self.assertEqual(body["status"], "accepted")
        self.assertTrue(self.get(self.run_path(body["result"]["run_id"])))
        self.assertTrue(body["cursor"].startswith("c-"))

    def test_run_pause_and_resume(self):
        run_id = self.start()
        self.op("run.pause", {"reason": "lunch"}, run_id=run_id)
        self.assertTrue(self.get(self.run_path(run_id))["paused"])
        self.tick(3)
        self.assertEqual(self.get(self.run_path(run_id) + "/units")["items"], [], "a paused run plans nothing")
        self.op("run.resume", run_id=run_id)
        self.assertFalse(self.get(self.run_path(run_id))["paused"])
        self.assertTrue(self.tick_to_unit(run_id))

    def test_unit_cancel(self):
        run_id = self.run_started()
        self.confirmed("unit.cancel", {"unit_id": self.unit["unit_id"]}, run_id=run_id)
        self.assertEqual(self.get(f"{self.run_path(run_id)}/units/{self.unit['unit_id']}")["state"]["state"], "cancelled")

    def test_unit_cancel_on_a_finished_unit_is_an_illegal_transition(self):
        run_id = self.run_started()
        self.tick(3)
        unit_id = self.unit["unit_id"]
        self.assertEqual(self.get(f"{self.run_path(run_id)}/units/{unit_id}")["state"]["state"], "done")
        first = self.op("unit.cancel", {"unit_id": unit_id}, run_id=run_id)
        body = self.op("unit.cancel", {"unit_id": unit_id}, run_id=run_id, token=first["confirm_token"], expect=409)
        self.assertEqual(body["error"]["code"], "illegal_transition")

    def test_unit_redispatch(self):
        run_id = self.run_started()
        unit_id = self.unit["unit_id"]
        engine = self.daemon.engine("acme", run_id)
        self.assertEqual(engine.units.state(unit_id)["state"], "running")
        self.confirmed("unit.redispatch", {"unit_id": unit_id, "model_tier": "opus"}, run_id=run_id)
        state = engine.units.state(unit_id)
        self.assertEqual((state["state"], state["retries_spent"]), ("redispatch", 0))
        self.assertEqual(engine.sessions(unit_id).all()[-1]["outcome"], "killed")
        self.tick()
        self.assertEqual(engine.units.state(unit_id)["sessions"][-1], "S-0002")
        self.assertEqual(engine.sessions(unit_id).all()[-1]["tier"], "opus")

    def test_run_note_reaches_the_next_session_of_each_open_unit(self):
        run_id = self.run_started()
        unit_id = self.unit["unit_id"]
        body = self.op("run.note", {"text": "Keep the hero copy."}, run_id=run_id)
        self.assertEqual(body["result"]["units"], [unit_id])
        engine = self.daemon.engine("acme", run_id)
        notes = (engine.units.unit_dir(unit_id) / "redispatch-notes.txt").read_text()
        self.assertIn("A note from the human (tui): Keep the hero copy.", notes)
        with self.assertRaises(Exception):
            self.app.state.operations.apply(op_id(), "run.note", "acme", run_id, {"text": "x"}, None, "chat")

    def test_project_unlock_config_records_a_ruling_the_hook_reads(self):
        self.confirmed("project.unlock_config", {"path": "./tsconfig.json", "reason": "ADR-004 adds an alias."})
        self.confirmed("project.unlock_config", {"path": "tsconfig.json", "reason": "Ruled again."})
        record = json.loads((self.project_path / "runs" / "_config-unlock.json").read_text())
        self.assertEqual([e["path"] for e in record["paths"]], ["tsconfig.json"], "one entry per path")
        self.assertIn("Ruled again.", record["paths"][0]["reason"])
        first = self.op("project.unlock_config", {"path": "../x", "reason": "r"})
        self.op("project.unlock_config", {"path": "../x", "reason": "r"}, token=first["confirm_token"], expect=400)

    def test_project_release_needs_a_command_a_run_and_a_clean_checkout(self):
        self.op("project.set_release", {"command": "deploy", "confirm": "go now"}, expect=400)
        first = self.op("project.release", {})
        self.op("project.release", {}, token=first["confirm_token"], expect=409)
        self.confirmed("project.set_release", {"command": f"{sys.executable} -c \"print('shipped')\""})
        self.assertIsNone(self.daemon.settings("acme")["release_confirm"])
        first = self.op("project.release", {})
        self.op("project.release", {}, token=first["confirm_token"], expect=409)  # no run to log it under
        run_id = self.run_started()
        engine = self.daemon.engine("acme", run_id)
        self.confirmed("project.release", {})
        for _ in range(200):
            if [e for e in engine.ledger.read() if e.line.get("event") == "release_finished"]:
                break
            time.sleep(0.05)
        started = [e.line for e in engine.ledger.read() if e.line.get("event") == "release_started"]
        self.assertEqual((len(started), started[0]["by"]), (1, "tui"))
        self.assertTrue([e for e in engine.ledger.read() if e.line.get("event") == "release_finished"])
        tracked = next(p for p in self.project_path.iterdir() if p.is_file() and p.name != ".gitignore")
        tracked.write_text(tracked.read_text() + "\nedited\n")
        first = self.op("project.release", {})
        refused = self.op("project.release", {}, token=first["confirm_token"], expect=409)
        self.assertIn("uncommitted", json.dumps(refused))
        with self.assertRaises(Exception):
            self.app.state.operations.apply(op_id(), "project.release", "acme", None, {}, None, "chat")

    def test_a_finished_run_commits_its_records_and_ignores_its_working_state(self):
        def git(*args):
            return subprocess.run(["git", "-C", str(self.project_path), *args], capture_output=True,
                                  text=True).stdout.strip()

        run_id = self.run_started()
        self.assertIn("runs/*/units/", git("show", "HEAD:.gitignore"), "the rules ride on the brief commit")
        self.daemon.tick_all()
        self.confirmed("run.cancel", run_id=run_id)
        self.daemon.tick_all()
        self.assertEqual(git("log", "-1", "--format=%s"), f"chore(runs): record {run_id}")
        committed = git("show", "--name-only", "--format=", "HEAD").splitlines()
        self.assertIn(f"runs/{run_id}/run-brief.json", committed)
        self.assertTrue(any(p.startswith(f"runs/{run_id}/artifacts/CYCLE-") for p in committed), committed)
        self.assertFalse([p for p in committed if "/units/" in p or p.endswith("events.jsonl")], committed)
        self.assertEqual(git("status", "--porcelain", "--", "runs"), "", "nothing in the run store is left loose")
        self.daemon.tick_all()
        self.assertEqual(git("log", "-1", "--format=%s"), f"chore(runs): record {run_id}", "recorded once")

    def test_project_set_checks_sets_and_clears_the_project_checks(self):
        self.confirmed("project.set_checks", {"commands": ["npm run check", "  "]})
        self.assertEqual(self.daemon.settings("acme")["project_checks"], ["npm run check"])
        self.confirmed("project.set_checks", {"commands": []})
        self.assertEqual(self.daemon.settings("acme")["project_checks"], [])
        self.op("project.set_checks", {"commands": ["a"] * 6}, expect=400)
        with self.assertRaises(Exception):
            self.app.state.operations.apply(op_id(), "project.set_checks", "acme", None, {"commands": []}, None,
                                            "chat")

    def test_daemon_restart_pauses_the_runs_and_drains_before_it_restarts(self):
        run_id = self.run_started()
        engine = self.daemon.engine("acme", run_id)
        restarted = []
        self.daemon.restart_process = lambda: restarted.append(self.daemon.sessions_running())
        engine.units.by_state = lambda *states: []
        self.confirmed("daemon.restart", {}, project=None)
        for _ in range(100):
            if restarted:
                break
            time.sleep(0.05)
        self.assertEqual(restarted, [0], "it restarts only once no session is running")
        self.assertTrue(engine.paused())
        first = self.op("daemon.restart", {}, project=None)
        self.op("daemon.restart", {}, project=None, token=first["confirm_token"], expect=409)

    def _open_gate(self, run_id, kind="scope-review"):
        return self.daemon.engine("acme", run_id).gates.open(
            kind, "L3", [], "Decide.", [{"option": "yes", "consequence": "It happens."}],
            decisions=[{"decision_id": "D1", "kind": "question", "prompt": "Why?"}])["content"]["checkpoint_id"]

    def test_gate_answer_records_the_response_and_each_decision(self):
        run_id = self.start()
        gate_id = self._open_gate(run_id)
        self.op("gate.answer", {"gate_id": gate_id, "option": "yes", "free_text": "Notes.",
                                "decisions": [{"decision_id": "D1", "response": "Because."}]}, run_id=run_id)
        gate = self.get(f"{self.run_path(run_id)}/gates/{gate_id}")
        self.assertEqual((gate["response"]["option"], gate["response"]["by"], gate["response"]["free_text"]),
                         ("yes", "tui", "Notes."))
        self.assertEqual(gate["decisions"][0]["response"], "Because.")

    def test_a_second_answer_gets_gate_already_answered_with_the_first(self):
        run_id = self.start()
        gate_id = self._open_gate(run_id)
        self.op("gate.answer", {"gate_id": gate_id, "option": "yes"}, run_id=run_id)
        body = self.op("gate.answer", {"gate_id": gate_id, "option": "yes"}, run_id=run_id, expect=409)
        self.assertEqual(body["error"]["code"], "gate_already_answered")
        self.assertEqual(body["error"]["details"]["response"]["option"], "yes")

    def test_gate_answer_with_a_rule_change_needs_confirmation(self):
        run_id = self.start()
        gate_id = self._open_gate(run_id)
        args = {"gate_id": gate_id, "option": "yes", "rule_change": "low ^docs/"}
        self.confirmed("gate.answer", args, run_id=run_id)

    def test_a_rule_change_updates_the_risk_rules_and_commits_them(self):
        run_id = self.start()
        gate_id = self._open_gate(run_id)
        self.confirmed("gate.answer", {"gate_id": gate_id, "option": "yes",
                                       "rule_change": "high auth ^src/server/session/"}, run_id=run_id)
        project = self.daemon.project_path("acme")
        rules = json.loads((project / "runs" / "_risk.json").read_text())
        self.assertEqual(rules, {"high": {"auth": ["^src/server/session/"]}})
        git = lambda *a: subprocess.run(["git", "-C", str(project), *a], capture_output=True, text=True).stdout.strip()
        self.assertEqual(git("log", "-1", "--format=%s"), f"chore(runs): risk rule from {gate_id}")
        self.assertEqual(git("status", "--porcelain", "--", "runs/_risk.json"), "")

    def test_a_rule_change_that_is_not_a_rule_is_refused_before_the_answer(self):
        run_id = self.start()
        gate_id = self._open_gate(run_id)
        for text in ("Auth tests are enough for L1.", "low ([", "high Auth ^x"):
            body = self.op("gate.answer", {"gate_id": gate_id, "option": "yes", "rule_change": text},
                           run_id=run_id, expect=400)
            self.assertIn("rule", json.dumps(body))
        self.assertIsNone(self.daemon.engine("acme", run_id).gates.get(gate_id)["content"].get("response"))

    def test_gate_answer_refuses_an_option_not_offered(self):
        run_id = self.start()
        gate_id = self._open_gate(run_id)
        self.op("gate.answer", {"gate_id": gate_id, "option": "maybe"}, run_id=run_id, expect=400)

    def test_digest_mark_viewed(self):
        run_id = self.start()
        engine = self.daemon.engine("acme", run_id)
        gate_id = engine.gates.open("routine-decision", "L1", [], "Merged.",
                                    [{"option": "viewed", "consequence": "Closes."}], digest=True)["content"]["checkpoint_id"]
        self.assertEqual(len(self.get(self.run_path(run_id) + "/gates", digest=True, state="open")["items"]), 1)
        self.op("digest.mark_viewed", {"gate_ids": [gate_id]}, run_id=run_id)
        self.assertEqual(self.get(self.run_path(run_id) + "/gates", digest=True, state="open")["items"], [])

    def features(self, run_id):
        return self.get(self.run_path(run_id) + "/backlog")["epics"][0]["features"]

    def test_backlog_move_mvp_line_confirms_outside_scope_review_only(self):
        run_id = self.run_started()
        self.confirmed("backlog.move_mvp_line", {"after_feature_id": "F-2"}, run_id=run_id)
        self.assertTrue(self.features(run_id)[1]["mvp"])
        self._open_gate(run_id)
        body = self.op("backlog.move_mvp_line", {"after_feature_id": "F-1"}, run_id=run_id)
        self.assertEqual(body["status"], "applied", "the scope review's answer is the commit")
        self.assertFalse(self.features(run_id)[1]["mvp"])

    def test_backlog_defer_and_restore_keep_the_feature_in_the_graph(self):
        run_id = self.run_started()
        self.confirmed("backlog.defer_feature", {"feature_id": "F-1"}, run_id=run_id)
        self.assertTrue(self.features(run_id)[0]["deferred"])
        self.assertEqual(len(self.features(run_id)[0]["stories"]), 2)
        self.assertEqual(self.get(self.run_path(run_id))["deferred"], ["F-1"])
        self.confirmed("backlog.restore_feature", {"feature_id": "F-1"}, run_id=run_id)
        self.assertFalse(self.features(run_id)[0]["deferred"])

    def test_backlog_reorder_refuses_to_break_a_dependency(self):
        run_id = self.run_started()
        body = self.op("backlog.reorder", {"story_id": "S-2", "position": 0}, run_id=run_id, expect=409)
        self.assertEqual(body["error"]["code"], "illegal_transition")
        self.backlog_file().write_text(json.dumps(
            {**BACKLOG, "epics": [{**BACKLOG["epics"][0], "features": [{**BACKLOG["epics"][0]["features"][0], "stories": [
                {"story_id": "S-1", "title": "a", "wave": 1, "unit_ids": [], "pr": None, "depends_on": []},
                {"story_id": "S-2", "title": "b", "wave": 1, "unit_ids": [], "pr": None, "depends_on": []}]}]}]}))
        self.op("backlog.reorder", {"story_id": "S-2", "position": 0}, run_id=run_id)
        self.assertEqual([s["story_id"] for s in self.features(run_id)[0]["stories"]], ["S-2", "S-1"])

    def test_backlog_add_bug(self):
        run_id = self.run_started()
        body = self.op("backlog.add_bug", {"title": "It broke", "severity": "high"}, run_id=run_id)
        self.assertEqual(body["result"]["story_id"], f"BUG-{time.strftime('%Y', time.gmtime())}-1")
        epics = self.get(self.run_path(run_id) + "/backlog")["epics"]
        self.assertEqual(epics[-1]["features"][0]["stories"][0]["title"], "It broke")

    def test_backlog_answer_unknown(self):
        run_id = self.run_started()
        self.op("backlog.answer_unknown", {"unknown_id": "UK-1", "answer": "EUR"}, run_id=run_id)
        self.assertEqual(self.get(self.run_path(run_id) + "/backlog")["unknowns"][0]["answer"], "EUR")

    def test_backlog_close_and_reopen_a_story(self):
        run_id = self.run_started()
        body = self.op("backlog.close_story", {"story_id": "S-2", "note": "shipped by hand"}, run_id=run_id)
        self.assertEqual((body["result"]["closed"]["source"], body["result"]["closed"]["note"]), ("human", "shipped by hand"))
        story = self.features(run_id)[0]["stories"][1]
        self.assertEqual((story["story_id"], story["column"], story["closed"]["source"]), ("S-2", "done", "human"))
        self.op("backlog.reopen_story", {"story_id": "S-2"}, run_id=run_id)
        story = self.features(run_id)[0]["stories"][1]
        self.assertEqual((story["column"], story.get("closed")), ("ready", None))
        self.op("backlog.close_story", {"story_id": "S-9"}, run_id=run_id, expect=404)

    def test_a_backlog_edit_is_committed_so_the_checkout_stays_clean(self):
        """Closing shipped stories by hand left runs/_backlog.json modified in the project
        checkout until a later run's records took it."""
        run_id = self.run_started()
        project = self.daemon.project_path("acme")
        git = lambda *a: subprocess.run(["git", "-C", str(project), *a], capture_output=True, text=True).stdout.strip()
        self.op("backlog.close_story", {"story_id": "S-2", "note": "shipped by hand"}, run_id=run_id)
        self.assertEqual(git("log", "-1", "--format=%s %ae"), "chore(runs): backlog close story springer@local")
        self.assertEqual(git("status", "--porcelain", "--", "runs/_backlog.json"), "")
        self.op("backlog.reopen_story", {"story_id": "S-2"}, run_id=run_id)
        self.assertEqual(git("log", "-1", "--format=%s"), "chore(runs): backlog reopen story")

    def test_project_reconcile_answer_records_the_answer_to_a_question(self):
        """The full reconcile flow is in test_harness_reconcile. This covers the operation."""
        self.start()
        self.daemon.reconciler.tick("acme", self.clock())
        (self.project_path / "billing").mkdir()
        (self.project_path / "billing" / "plans.py").write_text("PRO = 20\n")
        subprocess.run(["git", "-C", str(self.project_path), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.project_path), "-c", "user.name=Dev", "-c", "user.email=dev@example.com",
                        "commit", "-q", "-m", "Price the pro plan"], check=True)
        record = self.daemon.reconciler.tick("acme", self.clock() + 61)
        self.assertTrue(record["changes"][0]["question"])
        out = self.op("project.reconcile_answer", {"change_id": "R-1", "option": "not-architecture"})
        self.assertEqual(out["result"]["answer"]["option"], "not-architecture")
        self.op("project.reconcile_answer", {"change_id": "R-1", "option": "not-architecture"}, expect=409)

    def test_a_polish_run_puts_its_issue_on_the_project_backlog(self):
        run_id = self.confirmed("run.start", {"base_version": self.version, "lane": "polish",
                                              "issue": "The footer link is broken on the About page"})["result"]["run_id"]
        brief = json.loads((self.daemon.engine("acme", run_id).run_dir / "run-brief.json").read_text())["content"]
        year = time.strftime("%Y", time.gmtime())
        self.assertEqual((brief["lane"], brief["story_ids"]), ("polish", [f"BUG-{year}-1"]))
        view = self.get(self.run_path(run_id) + "/backlog")
        polish = next(f for e in view["epics"] for f in e["features"] if f["feature_id"] == "F-POLISH")
        story = polish["stories"][0]
        self.assertEqual((view["run_id"], story["story_id"], story["in_run"], story["work_type"]),
                         (run_id, f"BUG-{year}-1", True, "bug"))
        self.assertEqual(story["title"], "The footer link is broken on the About page")

    def test_a_burndown_run_takes_the_named_items_one_change_each(self):
        bug = self.confirmed("run.start", {"base_version": self.version, "lane": "polish",
                                           "issue": "The footer link is broken"})["result"]["run_id"]
        self.confirmed("run.cancel", {}, run_id=bug)
        year = time.strftime("%Y", time.gmtime())
        out = self.confirmed("run.start", {"base_version": self.version, "lane": "polish", "burndown": True,
                                           "story_ids": [f"BUG-{year}-1"]})["result"]
        brief = json.loads((self.daemon.engine("acme", out["run_id"]).run_dir / "run-brief.json").read_text())
        brief = brief["content"]
        self.assertEqual(out["story_ids"], [f"BUG-{year}-1"])
        self.assertEqual((brief["lane"], brief["issue"], [i["story_id"] for i in brief["items"]]),
                         ("polish", None, [f"BUG-{year}-1"]))
        self.assertEqual(brief["items"][0]["title"], "The footer link is broken")

    def test_a_backlog_operation_before_generation_is_refused(self):
        run_id = self.start()
        self.op("backlog.reorder", {"story_id": "S-1", "position": 0}, run_id=run_id, expect=409)
        # Filing a bug is the exception: it gives a project with no PM artifact yet its board.
        self.op("backlog.add_bug", {"title": "x"}, run_id=run_id)
        self.assertEqual(self.get(self.run_path(run_id) + "/backlog")["state"], "generated")

    def test_provisioning_set_secret_records_no_value_anywhere(self):
        run_id = self.start()
        engine = self.daemon.engine("acme", run_id)
        (engine.run_dir / "provisioning.json").write_text(json.dumps(
            [{"item_id": "stripe", "secret_name": "STRIPE_KEY", "needed_by": "skeleton"}]))
        body = self.op("provisioning.set_secret", {"item_id": "stripe", "value": "sk_live_DO_NOT_LOG"})
        self.assertEqual(body["result"], {"item_id": "stripe", "present": True})
        self.assertEqual(self.secrets.values[("acme", "STRIPE_KEY")], "sk_live_DO_NOT_LOG")
        self.assertTrue(self.get("/v1/projects/acme/provisioning")[0]["present"])
        for path in (self.daemon.home.audit_path, engine.ledger.path):
            if path.exists():
                self.assertNotIn("sk_live_DO_NOT_LOG", path.read_text(), path)
        self.assertNotIn("sk_live_DO_NOT_LOG", self.client.get("/v1/audit").text)

    def test_config_set_role_model(self):
        self.confirmed("config.set_role_model", {"role": "reviewer", "model": "opus"}, project=None)
        self.assertEqual(self.daemon.home.config()["role_models"]["reviewer"], "opus")

    def test_config_set_gate_channels(self):
        self.confirmed("config.set_gate_channels", {"level": "L2", "channels": ["telegram"]}, project=None)
        self.assertEqual(self.daemon.home.config()["gate_channels"]["L2"], ["telegram"])


COVERAGE = {
    "project.create": "test_project_create_and_archive", "project.archive": "test_project_create_and_archive", "project.archive_run": "test_run_archive_restore_and_prune",
    "project.restore_run": "test_run_archive_restore_and_prune", "project.prune_run": "test_run_archive_restore_and_prune",
    "project.configure": "test_project_configure_sets_the_ci_signal",
    "brief.update_section": "test_brief_update_section_before_start_needs_no_confirmation",
    "brief.update_facts": "test_brief_update_facts_recomputes_the_derived_profile",
    "brief.confirm_section": "test_brief_confirm_section_clears_proposed",
    "brief.run_discovery": "test_brief_run_discovery_returns_accepted_and_runs",
    "brief.dismiss_recommendation": "test_brief_dismiss_recommendation", "run.start": "test_run_start_opens_a_run",
    "run.pause": "test_run_pause_and_resume", "run.resume": "test_run_pause_and_resume",
    "run.cancel": "test_run_cancel_ends_the_run_and_a_new_one_can_start",
    "unit.cancel": "test_unit_cancel", "unit.redispatch": "test_unit_redispatch",
    "gate.answer": "test_gate_answer_records_the_response_and_each_decision",
    "digest.mark_viewed": "test_digest_mark_viewed",
    "backlog.move_mvp_line": "test_backlog_move_mvp_line_confirms_outside_scope_review_only",
    "backlog.defer_feature": "test_backlog_defer_and_restore_keep_the_feature_in_the_graph",
    "backlog.restore_feature": "test_backlog_defer_and_restore_keep_the_feature_in_the_graph",
    "backlog.reorder": "test_backlog_reorder_refuses_to_break_a_dependency", "backlog.add_bug": "test_backlog_add_bug",
    "backlog.answer_unknown": "test_backlog_answer_unknown",
    "backlog.close_story": "test_backlog_close_and_reopen_a_story",
    "backlog.reopen_story": "test_backlog_close_and_reopen_a_story",
    "project.reconcile_answer": "test_project_reconcile_answer_records_the_answer_to_a_question",
    "provisioning.set_secret": "test_provisioning_set_secret_records_no_value_anywhere",
    "config.set_role_model": "test_config_set_role_model", "config.set_gate_channels": "test_config_set_gate_channels",
    "run.note": "test_run_note_reaches_the_next_session_of_each_open_unit",
    "project.unlock_config": "test_project_unlock_config_records_a_ruling_the_hook_reads",
    "daemon.restart": "test_daemon_restart_pauses_the_runs_and_drains_before_it_restarts",
    "project.set_release": "test_project_release_needs_a_command_a_run_and_a_clean_checkout",
    "project.release": "test_project_release_needs_a_command_a_run_and_a_clean_checkout",
    "project.set_checks": "test_project_set_checks_sets_and_clears_the_project_checks",
}


class OperationRulesTest(ApiCase):
    def test_every_catalog_entry_has_a_test(self):
        self.assertEqual(set(COVERAGE), set(CATALOG))
        for kind, name in COVERAGE.items():
            self.assertTrue(hasattr(OperationCatalogTest, name), f"{kind} names a missing test {name}")

    def test_the_catalog_publishes_each_args_schema(self):
        body = self.get("/v1/operations/catalog")
        self.assertEqual({e["type"] for e in body}, set(CATALOG))
        secret = next(e for e in body if e["type"] == "provisioning.set_secret")
        self.assertEqual(secret["chat"], False)
        self.assertIn("value", secret["args_schema"]["properties"])

    def test_a_repeated_op_id_applies_once_and_returns_the_recorded_outcome(self):
        identifier = op_id()
        args = {"section": "Glossary", "body": "One.", "base_version": self.version}
        first = self.op("brief.update_section", args, identifier=identifier)
        second = self.op("brief.update_section", args, identifier=identifier)
        self.assertEqual(first, second)
        self.assertEqual(self.get("/v1/projects/acme/brief")["version"], self.version + 1)

    def test_idempotency_survives_a_daemon_restart(self):
        identifier = op_id()
        args = {"section": "Glossary", "body": "One.", "base_version": self.version}
        first = self.op("brief.update_section", args, identifier=identifier)
        fresh = Daemon(self.root / "home", MockProvider(), self.host, demo_planner_factory(), self.secrets, self.clock,
                       local_host=self.host)
        client = TestClient(create_app(fresh), base_url="http://127.0.0.1",
                            headers={"Authorization": f"Bearer {self.token}"})
        second = client.post("/v1/operations", json={"op_id": identifier, "type": "brief.update_section",
                                                     "project": "acme", "args": args}).json()
        self.assertEqual(first, second)

    def test_unknown_type_and_bad_args_are_refused(self):
        self.assertEqual(self.op("nope.nope", expect=400)["error"]["code"], "unknown_operation")
        self.assertEqual(self.op("run.start", {"wrong": 1}, expect=400)["error"]["code"], "invalid_args")
        self.assertEqual(self.op("run.pause", project="acme", expect=400)["error"]["code"], "invalid_args")

    def test_a_confirm_token_is_single_use_bound_and_expires(self):
        args = {"role": "reviewer", "model": "opus"}
        first = self.op("config.set_role_model", args, project=None)
        token = first["confirm_token"]
        other = self.op("config.set_role_model", {"role": "reviewer", "model": "haiku"}, project=None, token=token, expect=409)
        self.assertEqual(other["error"]["code"], "confirmation_invalid")
        self.assertNotIn("reviewer", self.daemon.home.config()["role_models"])
        first = self.op("config.set_role_model", args, project=None)
        self.op("config.set_role_model", args, project=None, token=first["confirm_token"])
        self.op("config.set_role_model", args, project=None, token=first["confirm_token"], expect=409)
        first = self.op("config.set_role_model", args, project=None)
        self.clock.advance(301)
        self.op("config.set_role_model", args, project=None, token=first["confirm_token"], expect=409)

    def test_nothing_changes_until_confirmed(self):
        args = {"role": "reviewer", "model": "opus"}
        self.op("config.set_role_model", args, project=None)
        self.assertEqual(self.daemon.home.config()["role_models"], {})

    def test_an_externally_held_run_refuses_writes_and_keeps_serving_reads(self):
        run_id = self.start()
        engine = self.daemon.engine("acme", run_id)
        engine.lock.path.write_text(json.dumps({"session_id": "claude-session",
                                                "claimed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.clock()))}))
        body = self.op("run.pause", run_id=run_id, expect=423)
        self.assertEqual(body["error"]["code"], "run_externally_held")
        self.assertEqual(self.get("/v1/projects/acme")["active_run"]["externally_held"], True)
        self.assertTrue(self.get(self.run_path(run_id)))

    def test_every_applied_operation_reaches_the_ledger_and_the_audit_log(self):
        run_id = self.start()
        self.op("run.pause", {"reason": "lunch"}, run_id=run_id)
        lines = [e.line for e in self.daemon.engine("acme", run_id).ledger.read()
                 if e.line.get("event") == "operation_applied"]
        self.assertEqual([(line["type"], line["actor"]) for line in lines], [("run.start", "tui"), ("run.pause", "tui")])
        audit = self.get("/v1/audit", project="acme")["items"]
        self.assertEqual([a["type"] for a in audit], ["run.start", "run.pause"])

    def test_a_client_cannot_claim_an_actor(self):
        response = self.client.post("/v1/operations", json={"op_id": "1", "type": "run.pause", "actor": "chat"})
        self.error(response, 400, "invalid_args")


class ChatActorTest(ApiCase):
    """The chat agent calls the same operations from inside the daemon."""

    def ops(self):
        return self.app.state.operations

    def test_chat_cannot_set_a_secret(self):
        with self.assertRaises(Exception) as caught:
            self.ops().apply(op_id(), "provisioning.set_secret", "acme", None, {"item_id": "x", "value": "y"}, None, "chat")
        self.assertEqual(caught.exception.code, "not_allowed_for_actor")

    def test_chat_always_confirms_a_state_change(self):
        outcome = self.ops().apply(op_id(), "brief.confirm_section", "acme", None,
                                   {"section": "Users", "base_version": self.version}, None, "chat")
        self.assertEqual(outcome["status"], "needs_confirmation")

    def test_chat_never_answers_a_production_release(self):
        run_id = self.start()
        gate_id = self.daemon.engine("acme", run_id).gates.open(
            "production-release", "L3", [], "Ship?", [{"option": "ship", "consequence": "It ships."}])["content"]["checkpoint_id"]
        args = {"gate_id": gate_id, "option": "ship"}
        first = self.ops().apply(op_id(), "gate.answer", "acme", run_id, args, None, "chat")
        with self.assertRaises(Exception) as caught:
            self.ops().apply(op_id(), "gate.answer", "acme", run_id, args, first["confirm_token"], "chat")
        self.assertEqual(caught.exception.code, "not_allowed_for_actor")
        self.assertIsNone(self.daemon.engine("acme", run_id).gates.get(gate_id)["content"]["response"])

    def test_chat_stub_says_it_is_not_built_and_proposes_nothing(self):
        response = self.client.post("/v1/chat", json={"message": "defer billing"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("not built", response.text)
        self.assertIn("event: done", response.text)
        self.assertNotIn("proposed_operation", response.text)


class ContractDriftTest(ApiCase):
    def test_the_served_schema_matches_the_committed_file(self):
        self.assertEqual(json.loads(current()), json.loads(OPENAPI_PATH.read_text()),
                         "run python -m springer_harness.api.export and review the diff")


class MockDesignTest(ApiCase):
    def test_the_canned_run_writes_a_mockup_the_review_can_open_and_keeps_an_existing_one(self):
        run_id = self.start()
        index = self.project_path / "docs" / "design" / "index.html"
        for _ in range(30):
            self.tick()
            if index.exists():
                break
        self.assertIn("This is a mock", index.read_text())
        browser = TestClient(self.app, base_url="http://127.0.0.1")
        page = browser.get(self.get("/v1/projects/acme/design-session")["url"].split("127.0.0.1", 1)[-1])
        self.assertEqual(page.status_code, 200)
        self.assertIn("This is a mock", page.text)
        index.write_text("mine")
        for _ in range(8):
            self.tick()
            for gate in self.get(self.run_path(run_id) + "/gates", state="open", digest=False)["items"]:
                self.op("gate.answer", {"gate_id": gate["checkpoint_id"], "option": gate["options"][0]["option"]}, run_id=run_id)
        self.assertEqual(index.read_text(), "mine")


class FullRunTest(ApiCase):
    def test_a_person_drives_a_whole_run_through_the_api_alone(self):
        """Nothing here reaches past the API except the tick, which the loop owns."""
        run_id = self.start()
        run = self.run_path(run_id)
        seen = set()
        for _ in range(120):
            self.tick()
            for gate in self.get(run + "/gates", state="open", digest=False)["items"]:
                seen.add(gate["checkpoint_type"])
                self.op("gate.answer", {"gate_id": gate["checkpoint_id"], "option": gate["options"][0]["option"]},
                        run_id=run_id)
            body = self.get(run)
            if body["complete"]:
                break
        else:
            self.fail(f"did not complete: {self.get(run + '/units')}")
        self.assertEqual(seen, {"direction-review", "pr-merge"})
        units = self.get(run + "/units")["items"]
        self.assertEqual({u["state"] for u in units}, {"done"})
        self.assertCountEqual(self.host.merged, [1, 2, 3, 4])
        digest = self.get(run + "/gates", digest=True)["items"]
        self.assertEqual(len(digest), 1)
        metrics = self.get(run + "/metrics")
        self.assertEqual(metrics["dispatches"], len(units))
        self.assertGreater(metrics["list_price_spend_usd"], 0)
        # A session folder with only its brief, before usage.json lands, does not break the sum.
        spawning = self.daemon.engine("acme", run_id).sessions(units[0]["unit_id"]).dir("S-0099")
        spawning.mkdir(parents=True)
        (spawning / "brief.md").write_text("brief")
        self.assertEqual(self.get(run + "/metrics")["list_price_spend_usd"], metrics["list_price_spend_usd"])
        self.get(f"{run}/units/{units[0]['unit_id']}")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class StreamTest(ApiCase):
    """SSE over a real socket, because a test client cannot show a stream staying open."""

    def setUp(self):
        super().setUp()
        self.app.state.heartbeat_seconds = 0.3
        self.port = free_port()
        self.server = uvicorn.Server(uvicorn.Config(self.app, host="127.0.0.1", port=self.port, log_level="error"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        deadline = time.time() + 10
        while not self.server.started and time.time() < deadline:
            time.sleep(0.02)
        self.addCleanup(self.thread.join, 5)
        self.addCleanup(setattr, self.server, "should_exit", True)
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def read_frames(self, path, until, headers=None, timeout=10):
        """Read frames until until(frames) is true, then drop the connection."""
        frames = []
        current = {}
        url = f"http://127.0.0.1:{self.port}{path}"
        with httpx.stream("GET", url, headers={**self.headers, **(headers or {})}, timeout=timeout) as response:
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/event-stream", response.headers["content-type"])
            for line in response.iter_lines():
                if line.startswith(("id: ", "event: ", "data: ")):
                    key, _, value = line.partition(": ")
                    current[key] = value
                elif not line and current:
                    frames.append({**current, "data": json.loads(current["data"])})
                    current = {}
                    if until(frames):
                        return frames
        return frames

    def test_run_stream_replays_then_follows_and_resumes_from_a_cursor(self):
        run_id = self.start()
        self.tick_to_unit(run_id)
        snapshot = self.get(self.run_path(run_id))["as_of"]
        path = self.run_path(run_id) + "/events"
        frames = self.read_frames(path, lambda f: any(x["event"] == "session_started" for x in f))
        self.assertEqual(frames[0]["event"], "operation_applied")
        self.assertEqual(frames[0]["data"]["type"], "run.start")
        self.assertTrue(all(f["id"].startswith("c-") for f in frames))
        self.op("run.pause", {"reason": "after snapshot"}, run_id=run_id)
        resumed = self.read_frames(f"{path}?after={snapshot}", lambda f: any(x["event"] == "operation_applied" for x in f))
        self.assertEqual(resumed[-1]["data"]["type"], "run.pause")
        self.assertFalse([f for f in resumed if f["event"] == "session_started"], "nothing before the cursor is replayed")

    def test_last_event_id_resumes_a_dropped_connection(self):
        run_id = self.start()
        path = self.run_path(run_id) + "/events"
        first = self.read_frames(path, lambda f: f)
        self.op("run.pause", run_id=run_id)
        frames = self.read_frames(path, lambda f: any(x["event"] == "operation_applied" for x in f),
                                  headers={"Last-Event-ID": first[0]["id"]})
        self.assertEqual(frames[-1]["data"]["type"], "run.pause")

    def test_lines_a_hook_wrote_with_no_seq_still_reach_the_stream(self):
        run_id = self.start()
        engine = self.daemon.engine("acme", run_id)
        with open(engine.ledger.path, "a") as fh:
            fh.write(json.dumps({"ts": "x", "event": "agent_dispatched", "tool_use_id": "t"}) + "\n")
        frames = self.read_frames(self.run_path(run_id) + "/events", lambda f: f[-1]["event"] == "agent_dispatched")
        self.assertNotIn("seq", frames[-1]["data"])

    def test_a_cursor_that_cannot_be_honored_gets_resync(self):
        run_id = self.start()
        frames = self.read_frames(self.run_path(run_id) + "/events?after=c-999999", lambda f: f)
        self.assertEqual(frames[0]["event"], "resync")
        self.assertEqual(frames[0]["data"]["cursor"], self.daemon.engine("acme", run_id).ledger.head())

    def test_heartbeat_arrives_on_a_quiet_stream(self):
        run_id = self.start()
        frames = self.read_frames(self.run_path(run_id) + "/events", lambda f: any(x["event"] == "heartbeat" for x in f))
        self.assertEqual(frames[-1]["event"], "heartbeat")

    def test_session_stream_replays_and_closes_when_the_session_ends(self):
        run_id = self.start()
        unit_id = self.tick_to_unit(run_id)["unit_id"]
        self.tick(3)
        engine = self.daemon.engine("acme", run_id)
        session = engine.units.state(unit_id)["sessions"][0]
        frames = self.read_frames(f"{self.run_path(run_id)}/units/{unit_id}/sessions/{session}/stream", lambda f: False)
        self.assertEqual(frames[0]["event"], "stream")
        self.assertEqual(frames[0]["data"]["type"], "tool_use")

    def test_daemon_stream_reports_a_gate_and_a_status_change(self):
        run_id = self.start()
        gate_box = {}

        def later():
            time.sleep(0.6)
            engine = self.daemon.engine("acme", run_id)
            gate = engine.gates.open("scope-review", "L3", [], "x", [{"option": "a", "consequence": "b"}])
            gate_box["id"] = gate["content"]["checkpoint_id"]

        threading.Thread(target=later, daemon=True).start()
        frames = self.read_frames("/v1/events", lambda f: any(x["event"] == "gate_opened" for x in f))
        opened = next(f for f in frames if f["event"] == "gate_opened")
        self.assertEqual(opened["data"], {"project": "acme", "run_id": run_id, "gate_id": gate_box["id"], "level": "L3"})

    def test_daemon_recovers_and_serves_after_a_restart(self):
        run_id = self.start()
        self.tick_to_unit(run_id)
        fresh = Daemon(self.root / "home", MockProvider(demo_script()), self.host, demo_planner_factory(), self.secrets,
                       self.clock, local_host=self.host)
        fresh.recover()
        engine = fresh.engine("acme", run_id)
        self.assertIn(engine.units.state("U-0001")["state"], ("redispatch", "done", "checking", "returned"))
        self.assertTrue(fresh.tick_all())


    def test_a_failing_tick_is_written_to_the_run_ledger_once(self):
        run_id = self.start()
        engine = self.daemon.engine("acme", run_id)
        engine.tick = lambda: (_ for _ in ()).throw(RuntimeError("gh pr merge failed"))
        with contextlib.redirect_stderr(io.StringIO()):
            self.tick(3)
        failures = [e.line for e in engine.ledger.read() if e.line.get("event") == "tick_failed"]
        self.assertEqual([f["detail"] for f in failures], ["RuntimeError: gh pr merge failed"])


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAVE_API, "the harness API dependencies are not installed")
class RunCleanupTest(ApiCase):
    """Archive hides a finished run and deletes nothing. Prune removes an archived run's
    folder, keeping what the repository cites and moving the ignored working state."""

    GIT = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]

    def setUp(self):
        super().setUp()
        old = self.project_path / "runs" / "old"
        (old / "artifacts").mkdir(parents=True)
        (old / "artifacts" / "prd-old.json").write_text("{}\n")
        (old / "artifacts" / "notes-old.json").write_text("{}\n")
        (self.project_path / "docs").mkdir(exist_ok=True)
        (self.project_path / "docs" / "decisions.md").write_text("See runs/old/artifacts/prd-old.json.\n")
        (self.project_path / ".gitignore").write_text("runs/*/events.jsonl\n")
        self.git("add", "-A")
        self.git(*self.GIT, "commit", "-q", "-m", "an old run")
        (old / "events.jsonl").write_text('{"event": "x"}\n')

    def git(self, *args, cwd=None):
        return subprocess.run(["git", "-C", str(cwd or self.project_path), *args], capture_output=True, text=True,
                              check=True).stdout

    def finish(self, run_id):
        first = self.op("run.cancel", run_id=run_id)
        if first["status"] == "needs_confirmation":
            self.op("run.cancel", run_id=run_id, token=first["confirm_token"])

    def history_ids(self, **params):
        return [r["run_id"] for r in self.get("/v1/projects/acme/history", **params)["runs"]]

    def test_archive_hides_a_finished_run_and_restore_brings_it_back(self):
        run_id = self.start()
        self.op("project.archive_run", {"run_id": run_id}, expect=409)  # still in progress
        self.finish(run_id)
        self.op("project.archive_run", {"run_id": run_id})
        self.assertNotIn(run_id, [r["run_id"] for r in self.get("/v1/projects/acme/runs")])
        archived = self.get("/v1/projects/acme/runs", include_archived="true")
        self.assertEqual([(r["run_id"], r["archived"]) for r in archived], [(run_id, True)])
        self.op("project.restore_run", {"run_id": run_id})
        self.assertEqual([r["run_id"] for r in self.get("/v1/projects/acme/runs")], [run_id])
        self.assertTrue((self.project_path / "runs" / run_id).is_dir(), "archive deletes nothing")

    def test_an_imported_run_is_archived_by_its_folder(self):
        self.op("project.archive_run", {"run_id": "old"})
        self.assertIn("old", self.daemon.archived_runs("acme"))
        self.op("project.archive_run", {"run_id": "nope"}, expect=404)

    def test_prune_needs_an_archived_run(self):
        self.op("project.prune_run", {"run_id": "old"}, expect=409)

    def test_prune_on_a_local_project_commits_the_removal_and_keeps_what_is_cited(self):
        self.op("project.archive_run", {"run_id": "old"})
        result = self.confirmed("project.prune_run", {"run_id": "old"})["result"]
        self.assertEqual((result["removed"], result["kept"], result["moved"]),
                         (1, ["runs/old/artifacts/prd-old.json"], 1))
        self.assertEqual(self.git("log", "-1", "--format=%s"), "chore(runs): prune old\n")
        self.assertEqual(self.git("ls-files", "runs/old").split(), ["runs/old/artifacts/prd-old.json"])
        moved = Path(result["moved_to"]) / "events.jsonl"
        self.assertEqual(moved.read_text(), '{"event": "x"}\n')
        self.assertFalse((self.project_path / "runs/old/events.jsonl").exists())
        self.op("project.restore_run", {"run_id": "old"}, expect=409)
        self.assertEqual(self.history_ids(include_archived="true"), [])  # no index for this project

    def test_a_pruned_run_keeps_its_number(self):
        first = self.start()
        self.finish(first)
        self.op("project.archive_run", {"run_id": first})
        self.confirmed("project.prune_run", {"run_id": first})
        self.assertNotIn(first, self.daemon.run_ids("acme"))
        self.assertNotEqual(self.start(), first)

    def test_prune_on_a_github_project_opens_a_pull_request_and_leaves_the_checkout(self):
        origin = self.root / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
        self.git("remote", "add", "origin", str(origin))
        self.git("push", "-q", "origin", "main")
        self.daemon.save_settings("acme", source_host="github")
        self.op("project.archive_run", {"run_id": "old"})
        result = self.confirmed("project.prune_run", {"run_id": "old"})["result"]
        self.assertEqual(result["change"], "https://example.invalid/pull/1")
        self.assertEqual(self.host.opened, [("springer/prune-old", "main", "chore(runs): prune old")])
        on_branch = self.git("ls-tree", "-r", "--name-only", "springer/prune-old", "runs/old", cwd=origin).split()
        self.assertEqual(on_branch, ["runs/old/artifacts/prd-old.json"])
        self.assertTrue((self.project_path / "runs/old/artifacts/notes-old.json").exists(),
                        "the checkout keeps the files until the pull request merges")
        self.assertFalse(any(p.name.startswith("_prune") for p in (self.daemon.home.root / "worktrees" / "acme").iterdir()))


class HostedCloneTest(ApiCase):
    """A hosted project works from the daemon's own clone, so the person's checkout is
    read for the brief and never committed in (Modes in pdca-harness)."""

    GIT = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]

    def git(self, *args, cwd=None):
        return subprocess.run(["git", "-C", str(cwd or self.project_path), *args], capture_output=True, text=True,
                              check=True).stdout

    def hosted(self):
        origin = self.root / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
        self.git("remote", "add", "origin", str(origin))
        self.git("push", "-q", "origin", "main")
        out = self.confirmed("project.configure", {"source_host": "github"})
        return origin, Path(out["result"]["clone"])

    def finish(self, run_id):
        first = self.op("run.cancel", run_id=run_id)
        if first["status"] == "needs_confirmation":
            self.op("run.cancel", run_id=run_id, token=first["confirm_token"])
        self.daemon.tick_all()

    def test_opting_into_github_gives_the_daemon_a_clone_and_leaves_the_checkout_alone(self):
        _, clone = self.hosted()
        self.assertEqual(clone, self.daemon.home.root / "clones" / "acme")
        self.assertEqual(self.daemon.project_path("acme"), clone)
        self.assertEqual(self.daemon.checkout_path("acme"), self.project_path)
        (self.project_path / "scratch.txt").write_text("work in progress in the person's editor\n")
        run_id = self.start()
        brief = json.loads((clone / "runs" / run_id / "run-brief.json").read_text())["content"]
        self.assertEqual(brief["brief_source"], "working_tree")
        self.assertEqual((clone / "docs" / "brief.md").read_text(), (self.project_path / "docs" / "brief.md").read_text())
        self.assertIn(f"docs: the brief for {run_id}", self.git("log", "--oneline", "-1", cwd=clone))
        self.assertFalse((self.project_path / "runs").exists(), "the person's checkout holds no run store")
        self.assertEqual(self.git("log", "--oneline").count("\n"), 1, "the person's main did not move")
        self.assertEqual(self.get("/v1/projects")[0]["clone"], str(clone))

    def test_a_newer_brief_on_origin_wins_over_an_older_one_in_the_checkout(self):
        origin, clone = self.hosted()
        other = self.root / "other"
        subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True)
        text = (self.project_path / "docs" / "brief.md").read_text()
        (other / "docs").mkdir()
        (other / "docs" / "brief.md").write_text(text.replace(f"brief_version: {self.version}", "brief_version: 40", 1))
        self.git("add", "-A", cwd=other)
        self.git(*self.GIT, "commit", "-q", "-m", "a later brief from another machine", cwd=other)
        self.git("push", "-q", "origin", "main", cwd=other)
        run_id = self.start()
        brief = json.loads((clone / "runs" / run_id / "run-brief.json").read_text())["content"]
        self.assertEqual((brief["brief_source"], brief["brief_version"]), ("commit", 40))
        self.assertIn("brief_version: 40", (clone / "docs" / "brief.md").read_text())

    def test_switching_hosts_moves_the_working_state_with_the_daemon(self):
        run_id = self.start()
        self.finish(run_id)
        self.assertTrue((self.project_path / "runs" / run_id / "events.jsonl").exists())
        _, clone = self.hosted()
        self.assertTrue((clone / "runs" / run_id / "events.jsonl").exists())
        self.assertFalse((self.project_path / "runs" / run_id / "events.jsonl").exists())
        self.assertIn(run_id, self.daemon.run_ids("acme"))
        self.confirmed("project.configure", {"source_host": "local"})
        self.assertTrue((self.project_path / "runs" / run_id / "events.jsonl").exists())
        self.assertIsNone(self.daemon.home.project("acme").get("clone"))
        self.assertEqual(self.daemon.project_path("acme"), self.project_path)

    def test_a_local_project_keeps_the_person_s_checkout_as_the_run_store(self):
        run_id = self.start()
        self.assertEqual(self.daemon.project_path("acme"), self.project_path)
        brief = json.loads((self.project_path / "runs" / run_id / "run-brief.json").read_text())["content"]
        self.assertEqual(brief["brief_source"], "working_tree")
        self.assertIsNone(self.daemon.home.project("acme").get("clone"))
