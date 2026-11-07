"""The backlog as a file in the run store, shown on the TUI board.

The PM unit writes the backlog as a prioritized-backlog artifact. backlog.json is built
from the latest one and rebuilt when the PM revises it, keeping what a person changed
on the board (the MVP line, deferrals, story order, bugs, answers)."""

import hashlib
import re
from pathlib import Path

from ..common import read_json, write_json
from ..errors import IllegalTransition, NotFound

BUG_EPIC = "E-BUGS"
BUG_FEATURE = "F-BUGS"
LOOSE_EPIC = "E-BACKLOG"
LOOSE_FEATURE = "F-STORIES"
DEFERRED_FEATURE = "F-DEFERRED"
# A unit that names no story_ids still counts for a story its expected outcome names.
STORY_ID = re.compile(r"\b(?:STORY|TASK|BUG)-[0-9]{4}-[0-9]+\b")
COLUMNS = {"planned": "ready", "ready": "ready", "retry": "in_progress", "redispatch": "in_progress",
           "running": "in_progress", "abandoned": "in_progress", "returned": "in_review", "checking": "in_review",
           "gated": "in_review", "blocked": "blocked", "done": "done", "cancelled": "done"}


class BacklogStore:
    def __init__(self, run_dir):
        self.path = Path(run_dir) / "backlog.json"

    def load(self):
        return read_json(self.path)

    def require(self):
        backlog = self.sync()
        if backlog is None:
            raise IllegalTransition("the backlog is not generated yet")
        return backlog

    def save(self, backlog):
        write_json(self.path, backlog)

    def source(self):
        """The newest prioritized-backlog artifact that is not a reference inventory, as
        (file name, digest, document), or None."""
        found = []
        for path in Path(self.path.parent, "artifacts").glob("prioritized-backlog*.json"):
            doc = read_json(path)
            if not isinstance(doc, dict) or doc.get("artifact_type") != "prioritized-backlog" \
                    or not isinstance(doc.get("content"), dict) or _inventory(path, doc):
                continue
            found.append((path.stat().st_mtime_ns, path.name, path))
        if not found:
            return None
        _, name, path = max(found)
        raw = path.read_bytes()
        return name, hashlib.sha256(raw).hexdigest(), read_json(path)

    def sync(self):
        """backlog.json, built from the PM's artifact when that is newer than it. A
        backlog with no artifact behind it is left as it is."""
        backlog = self.load()
        found = self.source()
        if found is None:
            return backlog
        name, digest, doc = found
        if backlog and (backlog.get("source") or {}).get("digest") == digest:
            return backlog
        fresh = from_artifact(doc["content"])
        fresh["source"] = {"artifact": name, "digest": digest}
        if backlog:
            carry(backlog, fresh)
        self.save(fresh)
        return fresh

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
        backlog = self.sync()
        if backlog is None:
            return {"as_of": as_of, "state": "not_generated", "epics": [], "unknowns": []}
        links = story_units(units)
        for feature in self.features(backlog):
            for story in feature["stories"]:
                story["unit_ids"] = sorted(set(story.get("unit_ids") or ()) | links.get(story["story_id"], set()))
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


def _inventory(path, doc):
    """The PM writes a reference's feature inventory as a prioritized-backlog tagged
    inventory. It is the source the backlog is transcribed from, not the backlog."""
    content = doc["content"]
    tags = [*(doc.get("tags") or ()), *(content.get("tags") or ())]
    return "inventory" in path.name or "inventory" in tags or content.get("status") == "inventory"


def from_artifact(content):
    """The board's epic, feature, story tree from a prioritized-backlog's flat lists.
    Items with no known feature, and backlogs with no hierarchy at all, sit under one
    Stories feature. Every feature starts above the MVP line."""
    items = list(content.get("backlog") or ())
    order = content.get("backlog_order")
    if order:
        rank = {story_id: index for index, story_id in enumerate(order)}
        items.sort(key=lambda item: rank.get(item.get("story_id"), len(rank)))
    else:
        items.sort(key=lambda item: item.get("position") or len(items) + 1)
    epics, by_epic, features = [], {}, {}

    def epic(epic_id, title):
        if epic_id not in by_epic:
            by_epic[epic_id] = {"epic_id": epic_id, "title": title, "critical": False, "features": []}
            epics.append(by_epic[epic_id])
        return by_epic[epic_id]

    def feature(epic_id, feature_id, title, outcome=None, mvp=True, deferred=False):
        record = {"feature_id": feature_id, "title": title, "mvp": mvp, "deferred": deferred, "stories": []}
        if outcome:
            record["outcome"] = outcome
        epic(epic_id, "Backlog" if epic_id == LOOSE_EPIC else epic_id)["features"].append(record)
        features[feature_id] = record
        return record

    for item in content.get("epics") or ():
        epic(item["epic_id"], item.get("name") or item["epic_id"])
    for item in content.get("features") or ():
        feature(item["epic_id"], item["feature_id"], item.get("name") or item["feature_id"], item.get("outcome"))
    for item in items:
        home = features.get(item.get("feature_id"))
        if home is None:
            home = features.get(LOOSE_FEATURE) or feature(LOOSE_EPIC, LOOSE_FEATURE, "Stories")
        home["stories"].append({"story_id": item["story_id"], "title": item.get("title") or item["story_id"],
                                "work_type": item.get("work_type") or "story", "wave": None, "unit_ids": [],
                                "pr": None, "depends_on": list(item.get("dependencies") or ())})
    deferred = [d for d in content.get("deferred_stories") or () if isinstance(d, dict)]
    if deferred:
        home = feature(LOOSE_EPIC, DEFERRED_FEATURE, "Deferred", mvp=False, deferred=True)
        for number, item in enumerate(deferred, 1):
            home["stories"].append({
                "story_id": item.get("story_id") or f"DEFERRED-{number}",
                "title": item.get("title") or item.get("item") or "Deferred item",
                "note": item.get("reason") or item.get("deferral_reason"),
                "work_type": "story", "wave": None, "unit_ids": [], "pr": None, "depends_on": []})
    return {"epics": epics, "unknowns": []}


def carry(old, fresh):
    """What a person changed on the old board survives the PM's revision: the MVP line
    and deferral per feature, story order within a feature, the bugs they added, and
    the unknowns they answered."""
    old_features = {f["feature_id"]: f for e in old.get("epics") or () for f in e["features"]}
    for epic in fresh["epics"]:
        for feature in epic["features"]:
            before = old_features.get(feature["feature_id"])
            if before is None:
                continue
            feature["mvp"], feature["deferred"] = before["mvp"], before["deferred"]
            rank = {s["story_id"]: index for index, s in enumerate(before["stories"])}
            feature["stories"].sort(key=lambda s: rank.get(s["story_id"], len(rank)))
    bugs = next((e for e in old.get("epics") or () if e["epic_id"] == BUG_EPIC), None)
    if bugs is not None:
        fresh["epics"].append(bugs)
    answered = {u["unknown_id"]: u for u in old.get("unknowns") or ()}
    fresh["unknowns"] = [answered.get(u["unknown_id"], u) for u in fresh["unknowns"]]


def story_units(units):
    """story_id to the units that build it: the story_ids the Plan step named, else the
    story ids in the unit's expected outcome. A review unit is left out, because the
    PR it reviews already puts the story in review."""
    links = {}
    for unit_id in units.ids():
        spec = units.spec(unit_id)
        if spec.get("review_of"):
            continue
        for story_id in spec.get("story_ids") or STORY_ID.findall(spec.get("expected_outcome") or ""):
            links.setdefault(story_id, set()).add(unit_id)
    return links
