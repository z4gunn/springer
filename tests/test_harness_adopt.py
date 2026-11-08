"""Adopting an existing Springer instance: the update path, the brief derived from its
run store, its history in the daemon index, and nothing of the project's written. The
instance is built here with new-project.sh and synthetic run records."""

import hashlib
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from harness_support import REPO

sys.path.insert(0, str(REPO / "harness"))

try:
    from fastapi.testclient import TestClient

    from springer_harness import adopt
    from springer_harness.api.app import create_app
    from springer_harness.daemon import Daemon
    from springer_harness.providers.mock import MockProvider, MockSourceHost
    from springer_harness.providers.mock_scenario import demo_planner_factory, demo_script
    from springer_harness.providers.secrets import MemorySecrets
    from springer_harness.state.brief import BriefStore
    HAVE = True
except ImportError:
    HAVE = False

OWNED = (".claude/skills/", ".claude/agents/", ".claude/references/", ".claude/hooks/", "schemas/",
         ".claude/springer-update/", ".claude/springer-manifest.json", "docs/brief.md", "DESIGN.md")


def envelope(kind, artifact_id, content, when):
    return {"artifact_id": artifact_id, "artifact_type": kind, "schema_version": "v1", "producing_agent": "x",
            "timestamp": when, "version": "v1.0", "content": content}


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data) if not isinstance(data, str) else data)


def build_instance(root):
    target = root / "shop"
    subprocess.run(["bash", str(REPO / "scripts/new-project.sh"), str(target), "small"], check=True, capture_output=True)
    # The instance's own edits and folders.
    ref = target / ".claude/references/pdca-harness.md"
    ref.write_text(ref.read_text() + "\nA local note.\n")
    (target / "CLAUDE.md").write_text((target / "CLAUDE.md").read_text() + "\n## Run-local conventions\n\nKeep me.\n")
    write(target / "Claude outputs/notes.md", "mine")
    write(target / "dist-deploy/site.tar", "bytes")
    write(target / "verification/check.py", "print('ok')")
    write(target / "package.json", {"dependencies": {"react": "1", "express": "1"}})
    runs = target / "runs"
    write(runs / "first/run-brief.json", envelope("run-brief", "rb-first", {
        "run_id": "first", "profile": "small", "flags": {"autonomy": "standard"},
        "pinned_rulings": ["R1: keep the palette", "R2: no client names"]}, "2026-01-01T00:00:00Z"))
    write(runs / "second/run-brief.json", envelope("run-brief", "rb-second", {
        "run_id": "second", "profile": "small", "flags": {"autonomy": "autopilot", "reference": "../poc"},
        "pinned_rulings": ["R2: no client names", "R3: one PR per page"]}, "2026-02-01T00:00:00Z"))
    write(runs / "second/artifacts/prd-second.json", envelope("prd", "prd-second", {
        "status": "confirmed", "problem_statement": {"text": "Shop owners lose orders in email."},
        "personas": [{"persona_id": "P-1", "primary_use_case": "Ola the shop owner (primary): takes orders by phone."}],
        "goals": [{"goal": "G1. An order is never lost", "success_metric": "Zero lost orders a week"}],
        "out_of_scope": [{"item": "Payments", "reason_excluded": "later"}],
        "success_metrics": [{"metric": "Orders logged", "target": "every one"}]}, "2026-02-02T00:00:00Z"))
    write(runs / "second/artifacts/prioritized-backlog-second.json", envelope("prioritized-backlog", "pb", {
        "status": "confirmed", "epics": [{"title": "Log an order", "goal": "The order shows in the list.",
                                          "stories": [{"title": "Order form"}, {"title": "Order list"}]}]},
        "2026-02-03T00:00:00Z"))
    write(runs / "second/artifacts/design-system-second.json", envelope("design-system", "ds", {
        "status": "confirmed", "tokens": {"color": {"ink": "#111"}}}, "2026-02-04T00:00:00Z"))
    write(runs / "second/artifacts/pdca-cycle-0001-second.json", envelope("pdca-cycle", "c1", {
        "cycle_id": "CYCLE-0001", "phase": "development", "plan": {"routed_batch": [{"agent": "spgr-agent-frontend-developer"}]},
        "do": {"dispatched": []}, "check": {"verdict": "pass"}, "act": {"transition": "complete"}}, "2026-02-05T00:00:00Z"))
    write(runs / "second/pending-defaults.md", "# defaults\n\n- DEF-1 | the heading | accepted\n")
    write(runs / "second/artifacts/run-retrospective-second.json", envelope("run-retrospective", "retro", {
        "run_id": "second", "learnings": [{"learning_id": "L-1", "category": "process", "observation": "Frozen lists help."}]},
        "2026-02-06T00:00:00Z"))
    (root / "poc").mkdir()
    return target


def snapshot(target):
    out = {}
    for path in target.rglob("*"):
        rel = path.relative_to(target).as_posix()
        if path.is_file() and not rel.startswith(".git/"):
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


@unittest.skipUnless(HAVE, "the harness dependencies are not installed")
class AdoptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = build_instance(self.root)
        self.daemon = Daemon(self.root / "home", MockProvider(demo_script()), MockSourceHost(), demo_planner_factory(),
                             MemorySecrets(), time.time)
        self.client = TestClient(create_app(self.daemon), base_url="http://127.0.0.1",
                                 headers={"Authorization": f"Bearer {self.daemon.home.token()}"})

    def op(self, kind, args, project=None):
        body = {"op_id": str(time.time_ns()), "type": kind, "project": project, "args": args}
        first = self.client.post("/v1/operations", json=body).json()
        if first.get("status") == "needs_confirmation":
            first = self.client.post("/v1/operations", json={**body, "confirm_token": first["confirm_token"]}).json()
        return first

    def test_the_preview_derives_and_writes_nothing(self):
        before = snapshot(self.target)
        preview = self.client.get("/v1/adopt/preview", params={"path": str(self.target)}).json()
        self.assertEqual(snapshot(self.target), before)
        self.assertTrue(preview["instance"])
        self.assertEqual(preview["runtime"]["edited"], [".claude/references/pdca-harness.md"])
        self.assertGreater(preview["runtime"]["unchanged"], 100, "the old runtime paths map to runtime/")
        self.assertIn("for a hand merge", preview["templates"]["CLAUDE.md"])
        self.assertEqual(sorted(preview["project_owned"]), ["Claude outputs", "dist-deploy", "verification"])
        self.assertNotIn("_update", preview)

    def test_adopting_writes_only_what_springer_owns(self):
        before = snapshot(self.target)
        out = self.op("project.create", {"name": "Shop", "path": str(self.target), "mode": "adopt"})
        self.assertEqual(out["status"], "applied", out)
        after = snapshot(self.target)
        changed = {rel for rel in set(before) | set(after) if before.get(rel) != after.get(rel)}
        self.assertTrue(changed)
        self.assertEqual({rel for rel in changed if not rel.startswith(OWNED)}, set(), "a project file was written")
        self.assertEqual(after[".claude/references/pdca-harness.md"], before[".claude/references/pdca-harness.md"])
        self.assertEqual(after["CLAUDE.md"], before["CLAUDE.md"], "CLAUDE.md is merged by hand")
        self.assertTrue((self.target / ".claude/springer-update/CLAUDE.md").exists())
        manifest = json.loads((self.target / ".claude/springer-manifest.json").read_text())
        edited = ".claude/references/pdca-harness.md"
        self.assertNotEqual(manifest["runtime"][edited], after[edited].join(["sha256:", ""]),
                            "an edit stays an edit for the next update")
        project = self.client.get("/v1/projects/shop").json()
        self.assertTrue(project["adopted"])
        self.assertIn(".claude/springer-update/CLAUDE.md", project["hand_merge"])

    def test_the_brief_comes_from_the_run_store(self):
        self.op("project.create", {"name": "Shop", "path": str(self.target), "mode": "adopt"})
        front, sections = BriefStore(self.target).load()
        self.assertEqual((front["profile"], front["lane"], front["live"]), ("small", "polish", True))
        self.assertEqual(front["reference"], str((self.root / "poc").resolve()))
        self.assertEqual(front["autonomy"], "autopilot")
        self.assertEqual(front["pinned_rulings"], ["R1: keep the palette", "R2: no client names", "R3: one PR per page"])
        self.assertIn("Shop owners lose orders in email.", sections["Problem"])
        self.assertIn("- Ola the shop owner:", sections["Users"])
        self.assertIn("### Log an order\nWho: Ola the shop owner", sections["Core flows"])
        self.assertIn("1. Order form", sections["Core flows"])
        self.assertIn("- Payments", sections["Non-goals"])
        self.assertEqual(front.get("proposed") or [], [], "derived sections arrive confirmed")
        self.assertIn('"ink": "#111"', (self.target / "DESIGN.md").read_text())

    def test_history_is_indexed_and_old_runs_are_not_daemon_runs(self):
        self.op("project.create", {"name": "Shop", "path": str(self.target), "mode": "adopt"})
        self.assertEqual(self.client.get("/v1/projects/shop/runs").json(), [])
        history = self.client.get("/v1/projects/shop/history").json()
        second = next(r for r in history["runs"] if r["run_id"] == "second")
        self.assertEqual(second["cycles"][0]["agents"], ["spgr-agent-frontend-developer"])
        self.assertEqual((second["complete"], second["defaults"]), (True, ["DEF-1 | the heading | accepted"]))
        self.assertEqual(history["learnings"][0]["observation"], "Frozen lists help.")
        self.assertFalse((self.target / "runs/second/events.jsonl").exists(), "the old run store is only read")

    def test_a_new_run_carries_every_pinned_ruling(self):
        self.op("project.create", {"name": "Shop", "path": str(self.target), "mode": "adopt"})
        run_id = self.daemon.start_run("shop", "build")
        brief = json.loads((self.target / "runs" / run_id / "run-brief.json").read_text())["content"]
        self.assertEqual(len(brief["pinned_rulings"]), 3)

    def test_a_live_lock_refuses_the_adoption(self):
        write(self.target / "runs/second/.lock", {"claimed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                                  "session_id": "s"})
        out = self.client.post("/v1/operations", json={"op_id": "x", "type": "project.create", "args": {
            "name": "Shop", "path": str(self.target), "mode": "adopt"}}).json()
        if out.get("status") == "needs_confirmation":
            out = self.client.post("/v1/operations", json={"op_id": "x", "type": "project.create", "confirm_token":
                                   out["confirm_token"], "args": {"name": "Shop", "path": str(self.target),
                                                                  "mode": "adopt"}}).json()
        self.assertIn("live lock", json.dumps(out))


if __name__ == "__main__":
    unittest.main()
