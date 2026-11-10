"""The project backlog at runs/_backlog.json, merged from every run's prioritized-backlog."""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

import harness_support  # noqa: F401  (puts the harness package on the path)
from springer_harness.state.backlog import BacklogStore

YEAR = time.strftime("%Y", time.gmtime())


def artifact(items, epics=(), features=(), deferred=(), status="proposed"):
    return {"artifact_type": "prioritized-backlog", "schema_version": "v1",
            "content": {"status": status, "backlog": list(items), "epics": list(epics),
                        "features": list(features), "deferred_stories": list(deferred)}}


def item(n, **extra):
    return {"story_id": f"STORY-2026-{n:03d}", "title": f"Story {n}", "position": n, **extra}


class Units:
    """The calls the backlog makes on the unit store."""

    def __init__(self, specs=None, states=None, prs=None):
        self.specs, self.states, self.prs = specs or {}, states or {}, prs or {}
        self.root = Path(tempfile.mkdtemp())

    def ids(self):
        return sorted(self.specs)

    def spec(self, unit_id):
        return self.specs[unit_id]

    def state(self, unit_id):
        record = {"state": self.states.get(unit_id, "planned")}
        if unit_id in self.prs:
            record["pr"] = {"number": self.prs[unit_id]}
        return record

    def unit_dir(self, unit_id):
        return self.root / unit_id


class BacklogFromArtifactTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        self.run_dir = self.project / "runs" / "acme-1"
        (self.run_dir / "artifacts").mkdir(parents=True)
        self.store = BacklogStore(self.project)
        self.file = self.project / "runs" / "_backlog.json"

    def write(self, name, doc, tick=0, run="acme-1", kind="build"):
        """An artifact in a run. A daemon run's brief carries a kind, a pre-daemon one's
        does not, and that is how the store tells history from the runs it drives."""
        path = self.project / "runs" / run / "artifacts" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc))
        os.utime(path, ns=(10**18 + tick, 10**18 + tick))
        brief = path.parents[1] / "run-brief.json"
        if not brief.exists():
            brief.write_text(json.dumps({"content": {"run_id": run, **({"kind": kind} if kind else {})}}))
        return path

    def stories(self, view):
        return [(f["feature_id"], s["story_id"]) for e in view["epics"] for f in e["features"] for s in f["stories"]]

    def feature(self, view, feature_id):
        return next(f for e in view["epics"] for f in e["features"] if f["feature_id"] == feature_id)

    def test_no_artifact_means_not_generated(self):
        self.assertEqual(self.store.view(Units(), "0")["state"], "not_generated")
        self.assertFalse(self.file.exists())

    def test_a_flat_backlog_sits_under_one_stories_feature_in_order(self):
        self.write("prioritized-backlog-x.json", artifact([item(2), item(1, dependencies=["STORY-2026-002"])]))
        view = self.store.view(Units(), "0")
        self.assertEqual(view["state"], "generated")
        self.assertEqual(self.stories(view), [("F-STORIES", "STORY-2026-001"), ("F-STORIES", "STORY-2026-002")])
        self.assertEqual(view["epics"][0]["features"][0]["stories"][0]["depends_on"], ["STORY-2026-002"])
        self.assertTrue(self.file.exists())
        self.assertEqual([s["run_id"] for s in json.loads(self.file.read_text())["sources"]], ["acme-1"])

    def test_epics_and_features_nest_and_deferrals_sit_below_the_line(self):
        self.write("prioritized-backlog-x.json", artifact(
            [item(1, feature_id="FEAT-1"), item(2, feature_id="FEAT-9")],
            epics=[{"epic_id": "EPIC-1", "name": "Reading"}],
            features=[{"feature_id": "FEAT-1", "epic_id": "EPIC-1", "name": "Hero", "outcome": "A visitor sees it"}],
            deferred=[{"item": "A second page", "reason": "Out of scope"}]))
        view = self.store.view(Units(), "0")
        self.assertEqual([(e["epic_id"], e["title"]) for e in view["epics"]],
                         [("EPIC-1", "Reading"), ("E-BACKLOG", "Backlog")])
        self.assertEqual(self.stories(view), [("FEAT-1", "STORY-2026-001"), ("F-STORIES", "STORY-2026-002"),
                                              ("F-DEFERRED", "DEFERRED-1")])
        deferred = view["epics"][1]["features"][1]
        self.assertEqual((deferred["mvp"], deferred["deferred"], deferred["stories"][0]["note"]),
                         (False, True, "Out of scope"))

    def test_the_inventory_is_not_the_backlog(self):
        self.write("prioritized-backlog-x.json", artifact([item(1)]), tick=1)
        self.write("prioritized-backlog-inventory.json", artifact([item(7)]), tick=2)
        self.assertEqual(self.stories(self.store.view(Units(), "0")), [("F-STORIES", "STORY-2026-001")])

    def test_a_revision_merges_and_keeps_what_the_person_changed(self):
        self.write("prioritized-backlog-x.json", artifact(
            [item(1, feature_id="FEAT-1"), item(2, feature_id="FEAT-1")],
            features=[{"feature_id": "FEAT-1", "epic_id": "EPIC-1", "name": "Hero", "outcome": "o"},
                      {"feature_id": "FEAT-2", "epic_id": "EPIC-1", "name": "Footer", "outcome": "o"}]), tick=1)
        self.store.set_deferred("FEAT-2", True)
        self.store.reorder("STORY-2026-002", 0)
        bug = self.store.add_bug("Broken link", "The footer link 404s", "low")
        self.write("prioritized-backlog-x.json", artifact(
            [item(1, feature_id="FEAT-1", title="Story 1, revised"), item(2, feature_id="FEAT-1"),
             item(3, feature_id="FEAT-1")],
            features=[{"feature_id": "FEAT-1", "epic_id": "EPIC-1", "name": "Hero", "outcome": "o"},
                      {"feature_id": "FEAT-2", "epic_id": "EPIC-1", "name": "Footer", "outcome": "o"}]), tick=2)
        view = self.store.view(Units(), "0")
        hero, footer = view["epics"][0]["features"]
        self.assertEqual([s["story_id"] for s in hero["stories"]],
                         ["STORY-2026-002", "STORY-2026-001", "STORY-2026-003"])
        self.assertEqual(hero["stories"][1]["title"], "Story 1, revised")
        self.assertTrue(footer["deferred"])
        self.assertEqual(bug, f"BUG-{YEAR}-1")
        self.assertIn(bug, [s["story_id"] for s in self.feature(view, "F-BUGS")["stories"]])

    def test_an_unchanged_artifact_keeps_the_board_as_edited(self):
        self.write("prioritized-backlog-x.json", artifact(
            [item(1, feature_id="FEAT-1")],
            features=[{"feature_id": "FEAT-1", "epic_id": "EPIC-1", "name": "Hero", "outcome": "o"}]))
        self.store.set_deferred("FEAT-1", True)
        self.assertTrue(self.store.view(Units(), "0")["epics"][0]["features"][0]["deferred"])

    def test_a_later_run_defers_what_it_leaves_out_and_keeps_what_is_done(self):
        self.write("prioritized-backlog-x.json", artifact([item(1), item(2), item(3)]), tick=1)
        self.store.close_story("STORY-2026-001", "human", "2026-11-07T00:00:00Z")
        self.write("prioritized-backlog-y.json", artifact([item(3, title="Story 3 again"), item(4)]), tick=2,
                   run="acme-2")
        view = self.store.view(Units(), "0")
        self.assertEqual(self.stories(view), [("F-STORIES", "STORY-2026-001"), ("F-STORIES", "STORY-2026-003"),
                                              ("F-STORIES", "STORY-2026-004"), ("F-DEFERRED", "STORY-2026-002")])
        left_out = self.feature(view, "F-DEFERRED")["stories"][0]
        self.assertEqual(left_out["note"], "left out by acme-2's backlog")
        self.assertEqual(view["epics"][0]["features"][0]["stories"][0]["closed"]["source"], "human")
        self.assertEqual(view["epics"][0]["features"][0]["stories"][1]["title"], "Story 3 again")
        self.assertEqual([s["run_id"] for s in json.loads(self.file.read_text())["sources"]], ["acme-1", "acme-2"])

    def test_a_pre_daemon_runs_stories_a_later_run_leaves_out_close_as_history(self):
        self.write("prioritized-backlog-old.json", artifact([item(1), item(2)]), tick=1, run="redesign", kind=None)
        self.write("prioritized-backlog-x.json", artifact([item(2, title="Story 2 again"), item(3)]), tick=2)
        view = self.store.view(Units(), "0")
        self.assertEqual(self.stories(view), [("F-STORIES", "STORY-2026-001"), ("F-STORIES", "STORY-2026-002"),
                                              ("F-STORIES", "STORY-2026-003")])
        shipped, kept, new = view["epics"][0]["features"][0]["stories"]
        self.assertEqual((shipped["column"], shipped["closed"]["source"], shipped["closed"]["run_id"],
                          shipped["closed"]["left_out_by"]), ("done", "history", "redesign", "acme-1"))
        self.assertEqual((kept["title"], kept["run_id"], kept.get("closed")), ("Story 2 again", "redesign", None))
        self.assertEqual(new["run_id"], "acme-1")

    def test_a_polish_issue_is_one_item_the_run_carries(self):
        task = self.store.add_issue("acme-2", "Move the newsletter form above the footer")
        bug = self.store.add_issue("acme-3", "The footer link is broken")
        self.assertEqual((task, bug), (f"TASK-{YEAR}-1", f"BUG-{YEAR}-1"))
        view = self.store.view(Units(), "0", run_id="acme-3")
        polish = self.feature(view, "F-POLISH")
        self.assertEqual([(s["story_id"], s["work_type"], s["in_run"]) for s in polish["stories"]],
                         [(task, "task", False), (bug, "bug", True)])
        self.assertEqual(polish["stories"][1]["title"], "The footer link is broken")

    def test_a_polish_issue_that_names_an_open_story_carries_it(self):
        """Building a deferred item as a polish run made a new TASK, and the deferred item
        stayed open after the merge."""
        self.write("prioritized-backlog-x.json", artifact([item(1), item(2)]))
        self.store.close_story("STORY-2026-002", "human", "2026-11-08T00:00:00Z")
        self.assertEqual(self.store.add_issue("acme-2", "STORY-2026-001: split the stylesheet"), "STORY-2026-001")
        self.assertEqual(self.store.story(self.store.load(), "STORY-2026-001")["run_id"], "acme-2")
        self.assertEqual(self.store.add_issue("acme-3", "STORY-2026-002: again"), f"TASK-{YEAR}-1",
                         "a closed story is not reopened by naming it")
        self.assertEqual(self.store.add_issue("acme-4", "STORY-2026-999 does not exist"), f"TASK-{YEAR}-2")
        self.assertEqual(self.store.add_issue("acme-5", "Tidy up after STORY-2026-001"), f"TASK-{YEAR}-3",
                         "only an id the issue opens with counts")

    def test_a_burndown_claims_the_open_items_above_the_line_or_the_ones_named(self):
        """Polish built one hand-typed issue per run, so the backlog never burned down."""
        from springer_harness.errors import IllegalTransition
        self.write("prioritized-backlog-x.json", artifact(
            [item(1, feature_id="FEAT-1"), item(2, feature_id="FEAT-1"), item(3, feature_id="FEAT-2"),
             item(4, feature_id="FEAT-3")],
            features=[{"feature_id": f"FEAT-{n}", "epic_id": "EPIC-1", "name": f"F{n}", "outcome": "o"}
                      for n in (1, 2, 3)]))
        self.store.sync()
        self.store.move_mvp_line("FEAT-2")
        self.store.set_deferred("FEAT-2", True)
        self.store.close_story("STORY-2026-002", "human", "2026-11-08T00:00:00Z")
        items = self.store.claim("acme-2")
        self.assertEqual([i["story_id"] for i in items], ["STORY-2026-001"],
                         "closed, deferred, and below-the-line items stay")
        self.assertEqual(self.store.story(self.store.load(), "STORY-2026-001")["run_id"], "acme-2")
        named = self.store.claim("acme-3", ["STORY-2026-004", "STORY-2026-003", "STORY-2026-004"])
        self.assertEqual([i["story_id"] for i in named], ["STORY-2026-004", "STORY-2026-003"],
                         "named items are taken as given, once each, whatever the line")
        with self.assertRaisesRegex(IllegalTransition, "STORY-2026-002 is closed"):
            self.store.claim("acme-4", ["STORY-2026-002"])
        self.store.close_story("STORY-2026-001", "human", "2026-11-08T00:00:00Z")
        with self.assertRaisesRegex(IllegalTransition, "nothing is open"):
            self.store.claim("acme-5")

    def test_a_story_takes_its_column_from_the_unit_that_builds_it(self):
        self.write("prioritized-backlog-x.json", artifact([item(1), item(2), item(3)]))
        units = Units({"U-0001": {"story_ids": ["STORY-2026-001"], "expected_outcome": "x"},
                       "U-0002": {"expected_outcome": "A PR for STORY-2026-002"},
                       "U-0003": {"review_of": "U-0001", "expected_outcome": "A verdict on STORY-2026-003"}},
                      {"U-0001": "gated", "U-0002": "running", "U-0003": "running"})
        stories = self.store.view(units, "0", run_id="acme-1")["epics"][0]["features"][0]["stories"]
        self.assertEqual([(s["unit_ids"], s["column"], s["in_run"]) for s in stories],
                         [(["U-0001"], "in_review", True), (["U-0002"], "in_progress", True), ([], "ready", True)])
        # Seen from another run, only a unit of that run puts a story in it.
        stories = self.store.view(units, "0", run_id="acme-2")["epics"][0]["features"][0]["stories"]
        self.assertEqual([s["in_run"] for s in stories], [True, True, False])

    def test_a_done_unit_closes_its_story_once_and_a_closed_record_wins(self):
        self.write("prioritized-backlog-x.json", artifact([item(1), item(2)]))
        units = Units({"U-0001": {"story_ids": ["STORY-2026-001"]}}, {"U-0001": "done"}, {"U-0001": 7})
        story = self.store.view(units, "2026-11-07T10:00:00Z", run_id="acme-1")["epics"][0]["features"][0]["stories"][0]
        self.assertEqual((story["column"], story["closed"]["source"], story["closed"]["pr"], story["closed"]["run_id"]),
                         ("done", "unit", 7, "acme-1"))
        saved = json.loads(self.file.read_text())["epics"][0]["features"][0]["stories"][0]
        self.assertEqual(saved["closed"]["at"], "2026-11-07T10:00:00Z")
        self.assertNotIn("column", saved, "the view's own fields stay out of the file")
        # Seen from a later run with no units, the close still holds. A person can reopen it.
        later = self.store.view(Units(), "0", run_id="acme-2")["epics"][0]["features"][0]["stories"][0]
        self.assertEqual((later["column"], later["in_run"]), ("done", False))
        self.store.reopen_story("STORY-2026-001")
        self.assertEqual(self.store.view(Units(), "0")["epics"][0]["features"][0]["stories"][0]["column"], "ready")
        self.store.close_story("STORY-2026-002", "human", "0")
        running = Units({"U-0002": {"story_ids": ["STORY-2026-002"]}}, {"U-0002": "running"})
        self.assertEqual(self.store.view(running, "0")["epics"][0]["features"][0]["stories"][1]["column"], "done")

    def test_an_older_nested_artifact_builds_a_tree_and_a_broken_one_is_skipped(self):
        self.write("prioritized-backlog-old.json", artifact([], epics=[
            {"title": "Log an order", "goal": "The order shows in the list.",
             "stories": [{"title": "Order form"}, {"title": "Order list"}]}]), tick=1)
        self.write("prioritized-backlog-bad.json", {"artifact_type": "prioritized-backlog", "content": {"epics": [7]}},
                   tick=2, run="acme-0")
        (self.project / "runs" / "acme-0" / "artifacts" / "prioritized-backlog-bad.json").write_text(
            json.dumps({"artifact_type": "prioritized-backlog", "content": {"backlog": [{"story_id": None, "x": 1}],
                                                                             "features": [None]}}))
        view = self.store.view(Units(), "0")
        self.assertEqual([(e["epic_id"], e["title"]) for e in view["epics"]], [("E-1", "Log an order")])
        self.assertEqual(self.stories(view), [("F-E-1", "STORY-1"), ("F-E-1", "STORY-2")])
        self.assertEqual(self.feature(view, "F-E-1")["outcome"], "The order shows in the list.")
        sources = json.loads(self.file.read_text())["sources"]
        self.assertEqual([(s["run_id"], "skipped" in s) for s in sources], [("acme-1", False), ("acme-0", True)])

    def test_the_first_build_carries_the_boards_older_runs_kept(self):
        self.write("prioritized-backlog-x.json", artifact(
            [item(1, feature_id="FEAT-1"), item(2, feature_id="FEAT-1")],
            features=[{"feature_id": "FEAT-1", "epic_id": "EPIC-1", "name": "Hero"},
                      {"feature_id": "FEAT-2", "epic_id": "EPIC-1", "name": "Footer"}]))
        old = {"epics": [
            {"epic_id": "EPIC-1", "title": "EPIC-1", "critical": False, "features": [
                {"feature_id": "FEAT-1", "title": "Hero", "mvp": True, "deferred": False, "stories": [
                    {"story_id": "STORY-2026-002", "title": "Story 2", "closed": {"source": "human", "at": "1"}},
                    {"story_id": "STORY-2026-001", "title": "Story 1"}]},
                {"feature_id": "FEAT-2", "title": "Footer", "mvp": False, "deferred": True, "stories": []}]},
            {"epic_id": "E-BUGS", "title": "Bugs", "critical": False, "features": [
                {"feature_id": "F-BUGS", "title": "Bugs", "mvp": True, "deferred": False, "stories": [
                    {"story_id": "BUG-1", "title": "Old bug", "wave": None, "unit_ids": [], "pr": None, "depends_on": []}]}]}],
            "unknowns": [{"unknown_id": "UK-1", "question": "Which currency?", "answer": "EUR"}]}
        (self.run_dir / "backlog.json").write_text(json.dumps(old))
        view = self.store.view(Units(), "0")
        hero, footer = view["epics"][0]["features"]
        self.assertEqual([s["story_id"] for s in hero["stories"]], ["STORY-2026-002", "STORY-2026-001"])
        self.assertEqual(hero["stories"][0]["column"], "done")
        self.assertEqual((footer["mvp"], footer["deferred"]), (False, True))
        self.assertEqual([s["story_id"] for s in self.feature(view, "F-BUGS")["stories"]], ["BUG-1"])
        self.assertEqual(view["unknowns"], old["unknowns"])
        self.assertTrue((self.run_dir / "backlog.json").exists(), "the old board is left where it was")


if __name__ == "__main__":
    unittest.main()
