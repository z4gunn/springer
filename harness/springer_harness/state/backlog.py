"""The backlog as a file in the run store. Files plus the TUI board are the default,
and a tracker is only ever a one-way projection of this."""

from pathlib import Path

from ..common import read_json, write_json
from ..errors import IllegalTransition, NotFound

BUG_EPIC = "E-BUGS"
BUG_FEATURE = "F-BUGS"
COLUMNS = {"planned": "ready", "ready": "ready", "retry": "in_progress", "redispatch": "in_progress",
           "running": "in_progress", "abandoned": "in_progress", "returned": "in_review", "checking": "in_review",
           "gated": "in_review", "blocked": "blocked", "done": "done", "cancelled": "done"}


class BacklogStore:
    def __init__(self, run_dir):
        self.path = Path(run_dir) / "backlog.json"

    def load(self):
        return read_json(self.path)

    def require(self):
        backlog = self.load()
        if backlog is None:
            raise IllegalTransition("the backlog is not generated yet")
        return backlog

    def save(self, backlog):
        write_json(self.path, backlog)

    def features(self, backlog):
        return [f for epic in backlog["epics"] for f in epic["features"]]

    def feature(self, backlog, feature_id):
        for feature in self.features(backlog):
            if feature["feature_id"] == feature_id:
                return feature
        raise NotFound(f"no feature {feature_id}")

    def move_mvp_line(self, after_feature_id):
        """Every feature up to and including after_feature_id is above the line."""
        backlog = self.require()
        features = self.features(backlog)
        ids = [f["feature_id"] for f in features]
        if after_feature_id not in ids:
            raise NotFound(f"no feature {after_feature_id}")
        cut = ids.index(after_feature_id)
        for index, feature in enumerate(features):
            feature["mvp"] = index <= cut
        self.save(backlog)

    def set_deferred(self, feature_id, deferred):
        backlog = self.require()
        self.feature(backlog, feature_id)["deferred"] = deferred
        self.save(backlog)

    def reorder(self, story_id, position):
        backlog = self.require()
        for feature in self.features(backlog):
            stories = feature["stories"]
            found = next((s for s in stories if s["story_id"] == story_id), None)
            if found is None:
                continue
            wave = [s for s in stories if s.get("wave") == found.get("wave")]
            wave.remove(found)
            position = max(0, min(position, len(wave)))
            wave.insert(position, found)
            order = [s["story_id"] for s in wave]
            for story in wave:
                for dep in story.get("depends_on", []):
                    if dep in order and order.index(dep) > order.index(story["story_id"]):
                        raise IllegalTransition(f"{story['story_id']} depends on {dep}, which would come after it")
            others = iter(wave)
            feature["stories"] = [next(others) if s.get("wave") == found.get("wave") else s for s in stories]
            self.save(backlog)
            return
        raise NotFound(f"no story {story_id}")

    def add_bug(self, title, description, severity):
        backlog = self.require()
        epic = next((e for e in backlog["epics"] if e["epic_id"] == BUG_EPIC), None)
        if epic is None:
            epic = {"epic_id": BUG_EPIC, "title": "Bugs", "critical": False,
                    "features": [{"feature_id": BUG_FEATURE, "title": "Bugs", "mvp": True, "deferred": False,
                                  "stories": []}]}
            backlog["epics"].append(epic)
        stories = epic["features"][0]["stories"]
        story_id = f"BUG-{len(stories) + 1}"
        stories.append({"story_id": story_id, "title": title, "description": description, "severity": severity,
                        "wave": None, "unit_ids": [], "pr": None, "depends_on": []})
        self.save(backlog)
        return story_id

    def answer_unknown(self, unknown_id, answer):
        backlog = self.require()
        for unknown in backlog.get("unknowns", []):
            if unknown["unknown_id"] == unknown_id:
                unknown["answer"] = answer
                self.save(backlog)
                return
        raise NotFound(f"no unknown {unknown_id}")

    def view(self, units, as_of):
        backlog = self.load()
        if backlog is None:
            return {"as_of": as_of, "state": "not_generated", "epics": [], "unknowns": []}
        for feature in self.features(backlog):
            for story in feature["stories"]:
                self._annotate(story, units)
        return {"as_of": as_of, "state": "generated", "epics": backlog["epics"],
                "unknowns": backlog.get("unknowns", [])}

    def _annotate(self, story, units):
        """Column and risk come from the units, so the board never diverges from them."""
        states, risks = [], []
        for unit_id in story.get("unit_ids", []):
            states.append(units.state(unit_id)["state"])
            risk = read_json(units.unit_dir(unit_id) / "risk.json") or {}
            if risk.get("level"):
                risks.append(risk["level"])
        columns = [COLUMNS[s] for s in states]
        for column in ("blocked", "in_progress", "in_review", "ready"):
            if column in columns:
                story["column"] = column
                break
        else:
            story["column"] = "done" if columns else "ready"
        story["risk"] = max(risks) if risks else story.get("risk")
