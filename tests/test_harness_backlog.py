"""The Backlog screen's backlog.json, built from the PM unit's prioritized-backlog."""

import json
import os
import tempfile
import unittest
from pathlib import Path

import harness_support  # noqa: F401  (puts the harness package on the path)
from springer_harness.state.backlog import BacklogStore


def artifact(items, epics=(), features=(), deferred=(), status="proposed"):
    return {"artifact_type": "prioritized-backlog", "schema_version": "v1",
            "content": {"status": status, "backlog": list(items), "epics": list(epics),
                        "features": list(features), "deferred_stories": list(deferred)}}


def item(n, **extra):
    return {"story_id": f"STORY-2026-{n:03d}", "title": f"Story {n}", "position": n, **extra}


class Units:
    """The two calls the backlog makes on the unit store."""

    def __init__(self, specs=None, states=None):
        self.specs, self.states, self.root = specs or {}, states or {}, Path(tempfile.mkdtemp())

    def ids(self):
        return sorted(self.specs)

    def spec(self, unit_id):
        return self.specs[unit_id]

    def state(self, unit_id):
        return {"state": self.states.get(unit_id, "planned")}

    def unit_dir(self, unit_id):
        return self.root / unit_id


class BacklogFromArtifactTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name)
        (self.run_dir / "artifacts").mkdir()
        self.store = BacklogStore(self.run_dir)

    def write(self, name, doc, tick=0):
        path = self.run_dir / "artifacts" / name
        path.write_text(json.dumps(doc))
        os.utime(path, ns=(10**18 + tick, 10**18 + tick))
        return path

    def stories(self, view):
        return [(f["feature_id"], s["story_id"]) for e in view["epics"] for f in e["features"] for s in f["stories"]]

    def test_no_artifact_means_not_generated(self):
        self.assertEqual(self.store.view(Units(), "0")["state"], "not_generated")
        self.assertFalse((self.run_dir / "backlog.json").exists())

    def test_a_flat_backlog_sits_under_one_stories_feature_in_order(self):
        self.write("prioritized-backlog-x.json", artifact([item(2), item(1, dependencies=["STORY-2026-002"])]))
        view = self.store.view(Units(), "0")
        self.assertEqual(view["state"], "generated")
        self.assertEqual(self.stories(view), [("F-STORIES", "STORY-2026-001"), ("F-STORIES", "STORY-2026-002")])
        self.assertEqual(view["epics"][0]["features"][0]["stories"][0]["depends_on"], ["STORY-2026-002"])
        self.assertTrue((self.run_dir / "backlog.json").exists())

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

    def test_a_revision_rebuilds_and_keeps_what_the_person_changed(self):
        self.write("prioritized-backlog-x.json", artifact(
            [item(1, feature_id="FEAT-1"), item(2, feature_id="FEAT-1")],
            features=[{"feature_id": "FEAT-1", "epic_id": "EPIC-1", "name": "Hero", "outcome": "o"},
                      {"feature_id": "FEAT-2", "epic_id": "EPIC-1", "name": "Footer", "outcome": "o"}]), tick=1)
        self.store.set_deferred("FEAT-2", True)
        self.store.reorder("STORY-2026-002", 0)
        bug = self.store.add_bug("Broken link", "The footer link 404s", "low")
        self.write("prioritized-backlog-x.json", artifact(
            [item(1, feature_id="FEAT-1"), item(2, feature_id="FEAT-1"), item(3, feature_id="FEAT-1")],
            features=[{"feature_id": "FEAT-1", "epic_id": "EPIC-1", "name": "Hero", "outcome": "o"},
                      {"feature_id": "FEAT-2", "epic_id": "EPIC-1", "name": "Footer", "outcome": "o"}]), tick=2)
        view = self.store.view(Units(), "0")
        hero, footer = view["epics"][0]["features"]
        self.assertEqual([s["story_id"] for s in hero["stories"]],
                         ["STORY-2026-002", "STORY-2026-001", "STORY-2026-003"])
        self.assertTrue(footer["deferred"])
        self.assertIn(bug, [s["story_id"] for s in view["epics"][-1]["features"][0]["stories"]])

    def test_an_unchanged_artifact_keeps_the_board_as_edited(self):
        self.write("prioritized-backlog-x.json", artifact(
            [item(1, feature_id="FEAT-1")],
            features=[{"feature_id": "FEAT-1", "epic_id": "EPIC-1", "name": "Hero", "outcome": "o"}]))
        self.store.set_deferred("FEAT-1", True)
        self.assertTrue(self.store.view(Units(), "0")["epics"][0]["features"][0]["deferred"])

    def test_a_story_takes_its_column_from_the_unit_that_builds_it(self):
        self.write("prioritized-backlog-x.json", artifact([item(1), item(2), item(3)]))
        units = Units({"U-0001": {"story_ids": ["STORY-2026-001"], "expected_outcome": "x"},
                       "U-0002": {"expected_outcome": "A PR for STORY-2026-002"},
                       "U-0003": {"review_of": "U-0001", "expected_outcome": "A verdict on STORY-2026-003"}},
                      {"U-0001": "gated", "U-0002": "running", "U-0003": "running"})
        stories = self.store.view(units, "0")["epics"][0]["features"][0]["stories"]
        self.assertEqual([(s["unit_ids"], s["column"]) for s in stories],
                         [(["U-0001"], "in_review"), (["U-0002"], "in_progress"), ([], "ready")])


if __name__ == "__main__":
    unittest.main()
