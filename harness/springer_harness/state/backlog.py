"""The backlog as one project fact at runs/_backlog.json, shown on the TUI board.

A build run's PM unit writes a prioritized-backlog artifact, and every such artifact in
the project merges into the one backlog by id: new items append, a known story takes
the new title and dependencies, a closed story stays closed, and a not-done story a later
artifact leaves out moves under Deferred with a note. A polish run adds its one issue as
an item. What a person changed on the board (the MVP line, deferrals, story order, bugs,
answers, closes) is never undone by an artifact. See Modes in pdca-harness."""

import hashlib
import re
import time
from pathlib import Path

from ..common import read_json, write_json
from ..errors import IllegalTransition, NotFound

FILE = "_backlog.json"
BUG_EPIC = "E-BUGS"
BUG_FEATURE = "F-BUGS"
LOOSE_EPIC = "E-BACKLOG"
LOOSE_FEATURE = "F-STORIES"
DEFERRED_FEATURE = "F-DEFERRED"
POLISH_FEATURE = "F-POLISH"
OWN_FEATURES = (BUG_FEATURE, DEFERRED_FEATURE, POLISH_FEATURE)  # items no artifact owns
# A unit that names no story_ids still counts for a story its expected outcome names.
STORY_ID = re.compile(r"\b(?:STORY|TASK|BUG)-[0-9]{4}-[0-9]+\b")
# An issue that opens with a backlog id, e.g. "DEFERRED-2:" or "STORY-2026-046 -".
NAMED_STORY = re.compile(r"\s*([A-Z][A-Z0-9]*(?:-\d+)+)\b")
# How many open items a burndown takes when the person names none.
BURNDOWN_CAP = 8
BUG_WORDS = re.compile(r"\b(bug|broken|breaks|fix|wrong|error|crash|fails?|404)\b", re.I)
COLUMNS = {"planned": "ready", "ready": "ready", "retry": "in_progress", "redispatch": "in_progress",
           "running": "in_progress", "abandoned": "in_progress", "returned": "in_review", "checking": "in_review",
           "gated": "in_review", "blocked": "blocked", "done": "done", "cancelled": "done"}


class BacklogStore:
    def __init__(self, project_path):
        self.root = Path(project_path) / "runs"
        self.path = self.root / FILE

    @classmethod
    def for_run(cls, run_dir):
        return cls(Path(run_dir).parents[1])

    def load(self):
        return read_json(self.path)

    def require(self):
        backlog = self.sync()
        if backlog is None:
            raise IllegalTransition("the backlog is not generated yet")
        return backlog

    def save(self, backlog):
        write_json(self.path, backlog)

    def sources(self):
        """Every prioritized-backlog artifact in the project that is not a reference
        inventory, oldest first, as (run_id, file name, digest, document)."""
        found = []
        for path in self.root.glob("*/artifacts/prioritized-backlog*.json"):
            doc = read_json(path)
            if not isinstance(doc, dict) or doc.get("artifact_type") != "prioritized-backlog" \
                    or not isinstance(doc.get("content"), dict) or _inventory(path, doc):
                continue
            found.append((path.stat().st_mtime_ns, path.parents[1].name, path.name, path))
        return [(run_id, name, hashlib.sha256(path.read_bytes()).hexdigest(), read_json(path))
                for _, run_id, name, path in sorted(found)]

    def sync(self):
        """The backlog, with every artifact not yet absorbed merged in. The first build of
        the file also carries over the boards older runs kept for themselves."""
        backlog = self.load()
        absorbed = {s["digest"] for s in (backlog or {}).get("sources") or ()}
        new = [s for s in self.sources() if s[2] not in absorbed]
        if not new:
            return backlog
        first = backlog is None
        backlog = backlog or _empty()
        history = self._history_runs()
        for run_id, name, digest, doc in new:
            source = {"run_id": run_id, "artifact": name, "digest": digest}
            try:
                merge(backlog, from_artifact(doc["content"]), run_id, history)
            except Exception as exc:  # noqa: BLE001, one unreadable artifact must not take the board down
                source["skipped"] = f"{type(exc).__name__}: {exc}"[:200]
            backlog["sources"].append(source)
        if first:
            for old in self._legacy_boards():
                carry(old, backlog)
        self.save(backlog)
        return backlog

    def _history_runs(self):
        """Runs from before the daemon, an adopted instance's history: a run folder whose
        brief carries no kind. Their stories are done when a later run leaves them out,
        because those runs shipped."""
        if not self.root.is_dir():
            return set()
        return {p.name for p in self.root.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))
                and not ((read_json(p / "run-brief.json") or {}).get("content") or {}).get("kind")}

    def _legacy_boards(self):
        """The per-run backlog.json files runs kept before the project backlog, oldest
        first, so the newest board's edits win."""
        paths = sorted((p for p in self.root.glob("*/backlog.json")), key=lambda p: p.stat().st_mtime_ns)
        return [b for b in (read_json(p) for p in paths) if isinstance(b, dict) and b.get("epics")]

    def features(self, backlog):
        return [f for epic in backlog["epics"] for f in epic["features"]]

    def feature(self, backlog, feature_id):
        for feature in self.features(backlog):
            if feature["feature_id"] == feature_id:
                return feature
        raise NotFound(f"no feature {feature_id}")

    def story(self, backlog, story_id):
        for feature in self.features(backlog):
            for story in feature["stories"]:
                if story["story_id"] == story_id:
                    return story
        raise NotFound(f"no story {story_id}")

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
        """A bug a person files on the board. The backlog exists from then on, so a
        project with no PM artifact yet has somewhere to put it."""
        backlog = self.sync() or _empty()
        feature = _own_feature(backlog, BUG_EPIC, "Bugs", BUG_FEATURE, "Bugs")
        story_id = _allocate(backlog, "BUG")
        feature["stories"].append({"story_id": story_id, "title": title, "description": description,
                                   "severity": severity, "work_type": "bug", "wave": None, "unit_ids": [],
                                   "pr": None, "depends_on": []})
        self.save(backlog)
        return story_id

    def add_issue(self, run_id, issue):
        """A polish run's one issue, in the person's words, as a TASK or a BUG the run's
        unit carries. The id comes from the project counter, so it never collides. An
        issue that opens with the id of an open story ("DEFERRED-2: ...") carries that
        story instead, so its merge closes it."""
        backlog = self.sync() or _empty()
        named = NAMED_STORY.match(issue or "")
        if named:
            try:
                story = self.story(backlog, named.group(1))
            except NotFound:
                story = None
            if story is not None and not story.get("closed"):
                story["run_id"] = run_id
                self.save(backlog)
                return story["story_id"]
        feature = _own_feature(backlog, LOOSE_EPIC, "Backlog", POLISH_FEATURE, "Polish")
        kind = "BUG" if BUG_WORDS.search(issue) else "TASK"
        story_id = _allocate(backlog, kind)
        title = issue.strip().splitlines()[0][:120] if issue.strip() else story_id
        feature["stories"].append({"story_id": story_id, "title": title, "description": issue.strip(),
                                   "work_type": kind.lower(), "run_id": run_id, "wave": None, "unit_ids": [],
                                   "pr": None, "depends_on": []})
        self.save(backlog)
        return story_id

    def claim(self, run_id, story_ids=None, cap=BURNDOWN_CAP):
        """The items a burndown run builds, each marked as the run's. Named ids are taken
        as given and must be open. With none, the open items above the MVP line and not
        deferred, in board order, up to cap. Returns what the planner needs of each."""
        backlog = self.require()
        if story_ids:
            picked = [self.story(backlog, story_id) for story_id in dict.fromkeys(story_ids)]
            closed = [s["story_id"] for s in picked if s.get("closed")]
            if closed:
                raise IllegalTransition(f"{', '.join(closed)} {'is' if len(closed) == 1 else 'are'} closed already")
        else:
            picked = [s for f in self.features(backlog) if f.get("mvp", True) and not f.get("deferred")
                      for s in f["stories"] if not s.get("closed")][:cap]
        if not picked:
            raise IllegalTransition("nothing is open above the MVP line to burn down")
        for story in picked:
            story["run_id"] = run_id
        self.save(backlog)
        return [{"story_id": s["story_id"], "title": s.get("title") or s["story_id"],
                 "detail": s.get("description") or s.get("note") or "", "depends_on": list(s.get("depends_on") or ())}
                for s in picked]

    def close_story(self, story_id, source, at, pr=None, note=None, **extra):
        """A story is done by the units that built it, by a pull request that names it,
        by an external change, or by a person on the board. The record says which."""
        backlog = self.require()
        story = self.story(backlog, story_id)
        if story.get("closed"):
            return story["closed"]
        story["closed"] = {k: v for k, v in {"source": source, "at": at, "pr": pr, "note": note, **extra}.items()
                           if v is not None}
        self.save(backlog)
        return story["closed"]

    def add_hint(self, story_id, hint):
        """An external change touched the paths a story's units declared. A hint, never
        a close."""
        backlog = self.require()
        self.story(backlog, story_id).setdefault("hints", []).append(hint)
        self.save(backlog)

    def verify(self, story_ids, passed):
        """The product checks ran after the change that closed these stories."""
        backlog = self.require()
        for story_id in story_ids:
            story = self.story(backlog, story_id)
            if story.get("closed"):
                story["closed"]["verified"] = bool(passed)
        self.save(backlog)

    def reopen_story(self, story_id):
        backlog = self.require()
        story = self.story(backlog, story_id)
        story.pop("closed", None)
        self.save(backlog)

    def answer_unknown(self, unknown_id, answer):
        backlog = self.require()
        for unknown in backlog.get("unknowns", []):
            if unknown["unknown_id"] == unknown_id:
                unknown["answer"] = answer
                self.save(backlog)
                return
        raise NotFound(f"no unknown {unknown_id}")

    def view(self, units, as_of, run_id=None, now=None):
        """The project backlog seen from one run: each story's units in that run, its
        column, and in_run for the items the run builds. A story whose units in the run
        are all done is closed by them, once, stamped now (as_of when no time is given)."""
        backlog = self.sync()
        if backlog is None:
            return {"as_of": as_of, "state": "not_generated", "epics": [], "unknowns": [], "run_id": run_id}
        links, known = story_units(units), set(units.ids())
        closed_now = {}
        for feature in self.features(backlog):
            for story in feature["stories"]:
                # Units the Plan step named or whose outcome names the story, plus any a
                # person pinned on the board, as long as this run still knows them.
                mine = sorted((set(story.get("unit_ids") or ()) & known) | links.get(story["story_id"], set()))
                story["unit_ids"] = mine
                story["in_run"] = bool(mine) or story.get("run_id") == run_id
                self._annotate(story, units)
                if mine and story["column"] == "done" and not story.get("closed"):
                    numbers = [(units.state(u).get("pr") or {}).get("number") for u in mine]
                    closed_now[story["story_id"]] = {"source": "unit", "at": now or as_of, "run_id": run_id, "unit_ids": mine,
                                                     "pr": next((n for n in numbers if n), None)}
                    story["closed"] = closed_now[story["story_id"]]
        if closed_now:
            # The view's own fields stay out of the file, so the closes are written alone.
            fresh = self.load()
            for feature in self.features(fresh):
                for story in feature["stories"]:
                    if story["story_id"] in closed_now and not story.get("closed"):
                        story["closed"] = closed_now[story["story_id"]]
            self.save(fresh)
        return {"as_of": as_of, "state": "generated", "epics": backlog["epics"],
                "unknowns": backlog.get("unknowns", []), "run_id": run_id}

    def _annotate(self, story, units):
        """Column and risk come from the closed record first, then the units, so the
        board never diverges from them."""
        states, risks = [], []
        for unit_id in story.get("unit_ids", []):
            states.append(units.state(unit_id)["state"])
            risk = read_json(units.unit_dir(unit_id) / "risk.json") or {}
            if risk.get("level"):
                risks.append(risk["level"])
        columns = [COLUMNS[s] for s in states]
        if story.get("closed"):
            story["column"] = "done"
        else:
            for column in ("blocked", "in_progress", "in_review", "ready"):
                if column in columns:
                    story["column"] = column
                    break
            else:
                story["column"] = "done" if columns else "ready"
        story["risk"] = max(risks) if risks else story.get("risk")


def _empty():
    return {"epics": [], "unknowns": [], "sources": [], "next": {}}


def _allocate(backlog, prefix):
    """The next id of a kind the daemon hands out, BUG-2026-3 style, past any id a PM
    artifact already used."""
    year = time.strftime("%Y", time.gmtime())
    taken = {s["story_id"] for e in backlog["epics"] for f in e["features"] for s in f["stories"]}
    counters = backlog.setdefault("next", {})
    number = counters.get(prefix, 0)
    while True:
        number += 1
        story_id = f"{prefix}-{year}-{number}"
        if story_id not in taken:
            counters[prefix] = number
            return story_id


def _own_feature(backlog, epic_id, epic_title, feature_id, title, mvp=True, deferred=False):
    """The feature the daemon keeps for items no artifact owns, made on first use."""
    epic = next((e for e in backlog["epics"] if e["epic_id"] == epic_id), None)
    if epic is None:
        epic = {"epic_id": epic_id, "title": epic_title, "critical": False, "features": []}
        backlog["epics"].append(epic)
    feature = next((f for f in epic["features"] if f["feature_id"] == feature_id), None)
    if feature is None:
        feature = {"feature_id": feature_id, "title": title, "mvp": mvp, "deferred": deferred, "stories": []}
        epic["features"].append(feature)
    return feature


def _inventory(path, doc):
    """The PM writes a reference's feature inventory as a prioritized-backlog tagged
    inventory. It is the source the backlog is transcribed from, not the backlog."""
    content = doc["content"]
    tags = [*(doc.get("tags") or ()), *(content.get("tags") or ())]
    return "inventory" in path.name or "inventory" in tags or content.get("status") == "inventory"


def from_artifact(content):
    """The board's epic, feature, story tree from a prioritized-backlog's flat lists.
    Items with no known feature, and backlogs with no hierarchy at all, sit under one
    Stories feature. Every feature starts above the MVP line. An older artifact that
    nests stories under its epics, or names nothing by id, gets ids by position."""
    content = _flatten(content)
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


def _flatten(content):
    """The flat lists the tree is built from, with ids filled in by position where an
    artifact has none, and the stories an epic nests lifted into the backlog list under
    a feature of their own."""
    epics, features, items = [], list(content.get("features") or ()), list(content.get("backlog") or ())
    for number, epic in enumerate(content.get("epics") or (), 1):
        if not isinstance(epic, dict):
            continue
        epic_id = epic.get("epic_id") or f"E-{number}"
        epics.append({**epic, "epic_id": epic_id, "name": epic.get("name") or epic.get("title") or epic_id})
        nested = [s for s in epic.get("stories") or () if isinstance(s, dict)]
        if nested:
            feature_id = f"F-{epic_id}"
            features.append({"feature_id": feature_id, "epic_id": epic_id,
                             "name": epic.get("name") or epic.get("title") or epic_id, "outcome": epic.get("goal")})
            items += [{**s, "feature_id": feature_id} for s in nested]
    for number, feature in enumerate(features, 1):
        feature.setdefault("feature_id", f"F-{number}")
        feature.setdefault("epic_id", epics[0]["epic_id"] if epics else LOOSE_EPIC)
    for number, item in enumerate(items, 1):
        item.setdefault("story_id", f"STORY-{number}")
    return {**content, "epics": epics, "features": features, "backlog": items}


def merge(backlog, fresh, run_id, history=()):
    """An artifact merges into the project backlog by id. New epics, features and
    stories append, each story remembering the run it came from. A known feature takes
    the new title and outcome, a known story the new title, type and dependencies, and
    keeps its place, its closed record, and what a person set. A not-done story the
    artifact leaves out moves under Deferred with a note naming the run, never deleted,
    unless it came from a run before the daemon, which shipped: that story closes with
    source history."""
    epics = {e["epic_id"]: e for e in backlog["epics"]}
    features = {f["feature_id"]: f for e in backlog["epics"] for f in e["features"]}
    stories = {s["story_id"]: (f, s) for f in features.values() for s in f["stories"]}
    seen = set()
    for epic in fresh["epics"]:
        home = epics.get(epic["epic_id"])
        if home is None:
            home = {**epic, "features": []}
            backlog["epics"].append(home)
            epics[epic["epic_id"]] = home
        else:
            home["title"] = epic["title"]
        for feature in epic["features"]:
            target = features.get(feature["feature_id"])
            if target is None:
                target = {**feature, "stories": []}
                home["features"].append(target)
                features[feature["feature_id"]] = target
            else:
                target["title"] = feature["title"]
                if feature.get("outcome"):
                    target["outcome"] = feature["outcome"]
            for story in feature["stories"]:
                seen.add(story["story_id"])
                known = stories.get(story["story_id"])
                if known is None:
                    story.setdefault("run_id", run_id)
                    target["stories"].append(story)
                    stories[story["story_id"]] = (target, story)
                    continue
                for key in ("title", "work_type", "depends_on", "note"):
                    if key in story:
                        known[1][key] = story[key]
    for story_id, (feature, story) in list(stories.items()):
        if story_id in seen or story.get("closed") or feature["feature_id"] in OWN_FEATURES:
            continue
        if story.get("run_id") in history:
            story["closed"] = {"source": "history", "run_id": story["run_id"], "left_out_by": run_id,
                               "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            continue
        feature["stories"].remove(story)
        story["note"] = f"left out by {run_id}'s backlog"
        _own_feature(backlog, LOOSE_EPIC, "Backlog", DEFERRED_FEATURE, "Deferred",
                     mvp=False, deferred=True)["stories"].append(story)
    backlog["unknowns"] = backlog.get("unknowns") or []
    known = {u["unknown_id"] for u in backlog["unknowns"]}
    backlog["unknowns"] += [u for u in fresh.get("unknowns") or () if u["unknown_id"] not in known]


def carry(old, fresh):
    """What a person changed on an older board survives into the project backlog: the
    MVP line and deferral per feature, story order within a feature, the bugs they
    added, the unknowns they answered, and the stories they closed."""
    old_features = {f["feature_id"]: f for e in old.get("epics") or () for f in e["features"]}
    old_stories = {s["story_id"]: s for f in old_features.values() for s in f["stories"]}
    for epic in fresh["epics"]:
        for feature in epic["features"]:
            before = old_features.get(feature["feature_id"])
            if before is None:
                continue
            feature["mvp"], feature["deferred"] = before["mvp"], before["deferred"]
            rank = {s["story_id"]: index for index, s in enumerate(before["stories"])}
            feature["stories"].sort(key=lambda s: rank.get(s["story_id"], len(rank)))
            for story in feature["stories"]:
                if old_stories.get(story["story_id"], {}).get("closed") and not story.get("closed"):
                    story["closed"] = old_stories[story["story_id"]]["closed"]
    bugs = next((e for e in old.get("epics") or () if e["epic_id"] == BUG_EPIC), None)
    if bugs is not None:
        home = _own_feature(fresh, BUG_EPIC, "Bugs", BUG_FEATURE, "Bugs")
        known = {s["story_id"] for s in home["stories"]}
        home["stories"] += [s for f in bugs["features"] for s in f["stories"] if s["story_id"] not in known]
    answered = {u["unknown_id"]: u for u in old.get("unknowns") or ()}
    fresh["unknowns"] = [answered.get(u["unknown_id"], u) for u in fresh.get("unknowns") or []]
    fresh["unknowns"] += [u for u in answered.values() if u["unknown_id"] not in {x["unknown_id"] for x in fresh["unknowns"]}]


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
