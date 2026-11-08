"""Reconcile: the daemon learns about changes it did not make (Modes in pdca-harness)."""

import json
import subprocess
import unittest
from pathlib import Path

from test_harness_api import HAVE_API, ApiCase

if HAVE_API:
    from springer_harness.notify.slack import handle_command

ME = "U-ME"
DEV = ["-c", "user.name=Dev", "-c", "user.email=dev@example.com", "-c", "commit.gpgsign=false"]
STORIES = {"epics": [{"epic_id": "E-1", "title": "Site", "critical": False, "features": [
    {"feature_id": "F-1", "title": "Pages", "mvp": True, "deferred": False, "stories": [
        {"story_id": "STORY-2026-001", "title": "Hero", "wave": 1, "unit_ids": [], "pr": None, "depends_on": []},
        {"story_id": "STORY-2026-002", "title": "Footer", "wave": 1, "unit_ids": [], "pr": None, "depends_on": []}]}]}],
    "unknowns": []}


@unittest.skipUnless(HAVE_API, "the harness API dependencies are not installed")
class ReconcileTest(ApiCase):
    def git(self, *args, cwd=None):
        return subprocess.run(["git", "-C", str(cwd or self.project_path), *args], capture_output=True, text=True,
                              check=True).stdout.strip()

    def person_commit(self, files, message, cwd=None):
        root = cwd or self.project_path
        for rel, text in files.items():
            path = Path(root) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        self.git("add", "-A", cwd=root)
        self.git(*DEV, "commit", "-q", "-m", message, cwd=root)
        return self.git("rev-parse", "HEAD", cwd=root)

    def look(self):
        self.clock.advance(61)
        return self.daemon.reconciler.tick("acme", self.clock())

    def finish(self, run_id):
        first = self.op("run.cancel", run_id=run_id)
        if first["status"] == "needs_confirmation":
            self.op("run.cancel", run_id=run_id, token=first["confirm_token"])
        self.daemon.tick_all()

    def backlog(self):
        return self.daemon.project_path("acme") / "runs" / "_backlog.json"

    def story(self, run_id, story_id):
        view = self.get(self.run_path(run_id) + "/backlog")
        return next(s for e in view["epics"] for f in e["features"] for s in f["stories"] if s["story_id"] == story_id)

    def test_the_first_look_seeds_and_the_daemons_own_commits_are_not_changes(self):
        record = self.look()
        self.assertTrue(record["seed"])
        self.assertEqual(record["to"], self.git("rev-parse", "HEAD"))
        self.start()  # the brief commit, by the Springer identity
        self.assertEqual(self.look()["changes"], [])
        self.assertIsNone(self.look(), "a tip that did not move writes nothing")
        self.assertEqual(self.daemon.announcements, [])

    def test_the_tick_looks_once_a_minute_per_project(self):
        self.daemon.tick_all()
        self.assertTrue((self.project_path / "runs" / "_reconcile.jsonl").exists())
        self.assertEqual(len(self.daemon.reconciler.records("acme")), 1)
        self.daemon.tick_all()
        self.assertEqual(len(self.daemon.reconciler.records("acme")), 1, "the same minute looks once")

    def test_an_external_change_closes_by_trailer_hints_by_path_and_posts_one_digest(self):
        run_id = self.start()
        self.backlog().write_text(json.dumps(STORIES))
        engine = self.daemon.engine("acme", run_id)
        unit = None
        for _ in range(12):
            self.tick()
            unit = next((u for u in engine.units.ids() if engine.units.spec(u).get("declared_paths")
                         and engine.units.state(u)["state"] in ("running", "ready", "retry", "gated", "returned")), None)
            if unit:
                break
        self.assertIsNotNone(unit, "an in-flight unit with declared paths")
        spec_path = engine.units.unit_dir(unit) / "spec.json"
        spec = json.loads(spec_path.read_text())
        spec["story_ids"] = ["STORY-2026-001"]
        spec_path.write_text(json.dumps(spec))
        declared = spec["declared_paths"][0]
        touched = declared + "notes.md" if declared.endswith("/") else declared
        self.look()
        sha = self.person_commit({touched: "by hand\n", "README.md": "edited\n"},
                                 "Fix the footer by hand\n\nCloses STORY-2026-002\n")
        record = self.look()
        change = record["changes"][0]
        self.assertEqual((change["id"], change["commit"], change["author"], change["pr"]), ("R-1", sha, "Dev", None))
        self.assertEqual((change["closed"], change["hints"]), (["STORY-2026-002"], ["STORY-2026-001"]))
        # A person's git add -A in a shared checkout sweeps the daemon's untracked records in too.
        self.assertEqual(sorted(p for p in change["paths"] if not p.startswith("runs/")), sorted([touched, "README.md"]))
        self.assertEqual(change["checks"]["ran"], False)
        self.assertEqual(change["question"], False)
        closed = self.story(run_id, "STORY-2026-002")
        self.assertEqual((closed["column"], closed["closed"]["source"], closed["closed"]["commit"], closed["closed"]["by"]),
                         ("done", "external", sha, "Dev"))
        hinted = self.story(run_id, "STORY-2026-001")
        self.assertEqual((hinted["hints"][0]["change"], hinted["hints"][0]["paths"]), ("R-1", [touched]))
        self.assertEqual(len(self.daemon.announcements), 1)
        digest = self.daemon.announcements[0]
        for piece in ("acme: main moved by 1 external change", "R-1", "by Dev", "closed STORY-2026-002",
                      "hinted STORY-2026-001", "1 in-flight unit told"):
            self.assertIn(piece, digest)
        # The in-flight unit whose paths moved was told, and its run says so.
        self.assertEqual(change["overlap"], [{"run_id": run_id, "unit_id": unit, "paths": [touched]}])
        self.assertIn("Rebase your branch onto main", (engine.units.unit_dir(unit) / "redispatch-notes.txt").read_text())
        self.assertIn("external_overlap", [e.line["event"] for e in engine.ledger.read()])

    def test_product_checks_run_for_product_paths_and_mark_the_close_verified(self):
        run_id = self.start()
        self.backlog().write_text(json.dumps(STORIES))
        (self.project_path / "runs" / "_product-check.json").write_text(json.dumps({"checks": [
            {"id": "home", "flow": "open the home page", "expect": "it renders", "command": "true",
             "touches": ["src/"]}]}))
        self.look()
        self.person_commit({"src/footer.py": "x = 1\n"}, "Footer\n\nFixes STORY-2026-002\n")
        change = self.look()["changes"][0]
        self.assertEqual((change["checks"]["ran"], change["checks"]["passed"]), (True, True))
        self.assertTrue(self.story(run_id, "STORY-2026-002")["closed"]["verified"])
        self.assertTrue(list((self.project_path / "runs" / "_reconcile" / "product-checks").glob("*.json")))
        self.assertIn("product checks passed", self.daemon.announcements[-1])

    def test_a_gate_list_change_asks_and_the_answer_is_recorded_once(self):
        self.start()
        self.look()
        self.person_commit({"packages/auth/session.py": "TTL = 12\n"}, "Tighten the session")
        change = self.look()["changes"][0]
        self.assertTrue(change["question"])
        self.assertEqual((change["risk"]["level"], change["risk"]["categories"]), ("high", ["auth"]))
        question = self.daemon.announcements[-1]
        self.assertIn("R-1 touches auth", question)
        self.assertIn("/springer reconcile acme R-1 decision", question)
        self.op("project.reconcile_answer", {"change_id": "R-1", "option": "decision"}, expect=400)
        out = self.op("project.reconcile_answer", {"change_id": "R-1", "option": "decision",
                                                   "text": "ADR-001: a session lasts 12 hours"})
        self.assertEqual(out["result"]["answer"]["option"], "decision")
        self.op("project.reconcile_answer", {"change_id": "R-1", "option": "not-architecture"}, expect=409)
        self.op("project.reconcile_answer", {"change_id": "R-9", "option": "review"}, expect=404)
        self.assertEqual(self.daemon.reconciler.records("acme")[-1]["answer"]["text"], "ADR-001: a session lasts 12 hours")

    def test_review_opens_a_polish_run_on_the_change_and_slack_answers_too(self):
        run_id = self.start()
        self.finish(run_id)
        self.look()
        self.person_commit({"migrations/002_users.sql": "DROP TABLE users;\n"}, "Drop the users table")
        change = self.look()["changes"][0]
        self.assertIn("data", change["risk"]["categories"])
        reply = handle_command("reconcile acme R-1 review", self.daemon, self.daemon.operations, ME, ME)
        self.assertRegex(reply, r"Started acme-\d+ to review it")
        polish = self.daemon.run_ids("acme")[-1]
        brief = json.loads((self.project_path / "runs" / polish / "run-brief.json").read_text())["content"]
        self.assertEqual(brief["lane"], "polish")
        self.assertIn("Review the external change", brief["issue"])
        self.assertIn("Drop the users table", brief["issue"])
        self.assertEqual(len(brief["story_ids"]), 1)
        self.assertIn("How?", handle_command("reconcile acme R-1", self.daemon, self.daemon.operations, ME, ME))

    def test_a_rewritten_history_reseeds_with_one_line(self):
        self.look()
        self.git("checkout", "-q", "--orphan", "fresh")
        self.git(*DEV, "commit", "-q", "--allow-empty", "-m", "a new root")
        self.git("branch", "-D", "main")
        self.git("branch", "-m", "main")
        record = self.look()
        self.assertTrue(record["rewritten"])
        self.assertIn("was rewritten", self.daemon.announcements[-1])
        self.assertIsNone(self.look())

    def test_a_hosted_change_is_attributed_by_pull_request_number(self):
        origin = self.root / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
        self.git("remote", "add", "origin", str(origin))
        self.git("push", "-q", "origin", "main")
        clone = Path(self.confirmed("project.configure", {"source_host": "github"})["result"]["clone"])
        self.look()
        other = self.root / "other"
        subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True)
        sha = self.person_commit({"src/footer.py": "x\n"}, "Add the footer (#12)", cwd=other)
        self.git("push", "-q", "origin", "main", cwd=other)
        change = self.look()["changes"][0]
        self.assertEqual((change["pr"], change["commit"], change["author"]), (12, sha, "Dev"))
        self.assertTrue((clone / "runs" / "_reconcile.jsonl").exists())
        self.assertFalse((self.project_path / "runs").exists(), "the person's checkout is never written")
        self.assertIn("#12 by Dev", self.daemon.announcements[-1])


if __name__ == "__main__":
    unittest.main()
