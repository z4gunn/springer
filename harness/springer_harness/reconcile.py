"""Reconcile: the daemon is the record truth, and it learns about changes it did not make.

Once a minute per project the daemon compares the default branch tip to the last one it
reconciled, kept as the last line of runs/_reconcile.jsonl. A commit that is not its own,
by identity, by subject, or by a pull request a run opened, is an external change: a
person's merge, a Claude Code edit, a hand fix. For each one the daemon records the paths
and the author, closes a story a Closes trailer names, hints a not-done story whose units'
paths the change overlaps, runs the product checks those paths touch, tells an in-flight
unit its files moved, validates a hand-edited artifact, notes a hand-edited doc, and posts
one Slack line per batch. A change the risk scorer rates high asks in Slack, and the
answer is recorded here. Reconcile never reviews a person's change. See Modes in
pdca-harness."""

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

from .check import mechanical
from .common import iso, read_json
from .errors import IllegalTransition, InvalidArgs, NotFound
from .state.backlog import BacklogStore, story_units

FILE = "runs/_reconcile.jsonl"
CHECK_DIR = "runs/_reconcile"
SOURCE = Path(__file__).resolve().parents[2]
SCRIPTS = Path(".claude/skills/spgr-run-harness/scripts")
OWN_EMAIL = "springer@local"
OWN_SUBJECTS = re.compile(r"^(chore\(runs\): (record|prune|reconcile)|docs: the brief for)")
TRAILER = re.compile(r"\b(?:Closes|Fixes|Resolves):?\s+((?:STORY|TASK|BUG)-\d{4}-\d+)", re.I)
PR_NUMBER = re.compile(r"\(#(\d+)\)\s*$|^Merge pull request #(\d+)")
OPTIONS = ("decision", "not-architecture", "review")
INTERVAL = 60
CHECK_TIMEOUT = 300


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def _script(project, name):
    """The instance's copy of a harness script, else this repository's."""
    local = Path(project) / SCRIPTS / name
    return local if local.exists() else SOURCE / "runtime" / "skills" / "spgr-run-harness" / "scripts" / name


def _risk(project, sha):
    """pr-risk.py's verdict on one commit against its first parent, imported so a project
    without the skill installed is scored the same way a pull request is."""
    spec = importlib.util.spec_from_file_location("spgr_pr_risk", _script(project, "pr-risk.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        return module.assess(str(project), f"{sha}^1", sha, config=read_json(Path(project) / "runs" / "_risk.json"))
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        return {"risk": "unknown", "categories": [], "reasons": [str(exc)[:200]]}


def _under(path, declared):
    return any(path == d or path.startswith(d if d.endswith("/") else d + "/") for d in declared)


def _plural(count, noun):
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


class Reconciler:
    def __init__(self, daemon):
        self.daemon = daemon
        self.last = {}

    def due(self, slug, now):
        return now - self.last.get(slug, 0) >= INTERVAL

    def records(self, slug):
        path = self.daemon.project_path(slug) / FILE
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def _append(self, slug, record):
        path = self.daemon.project_path(slug) / FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as fh:
            fh.write(json.dumps(record) + "\n")

    # --- the look ---

    def tick(self, slug, now):
        """One look at the project. Returns the record written, or None when the tip has
        not moved. The first look seeds at the tip and records nothing else."""
        self.last[slug] = now
        project = self.daemon.project_path(slug)
        if not (project / ".git").exists():
            return None
        branch = _git(project, "symbolic-ref", "--short", "HEAD").stdout.strip() or "main"
        ref = branch
        if _git(project, "remote", "get-url", "origin").returncode == 0:
            if _git(project, "fetch", "--quiet", "origin", branch).returncode:
                return None
            ref = f"origin/{branch}"
        tip = _git(project, "rev-parse", "--verify", ref).stdout.strip()
        if not tip:
            return None
        records = self.records(slug)
        seen = next((r["to"] for r in reversed(records) if r.get("to")), None)
        at = iso(now)
        if seen is None:
            record = {"at": at, "to": tip, "seed": True}
            self._append(slug, record)
            return record
        if seen == tip:
            return None
        if _git(project, "merge-base", "--is-ancestor", seen, tip).returncode:
            record = {"at": at, "from": seen, "to": tip, "rewritten": True}
            self._append(slug, record)
            self.daemon.announce(f"{slug}: {branch} was rewritten, so reconcile starts again from {tip[:7]}.")
            return record
        own_prs = self._own_prs(slug)
        number = sum(len(r.get("changes") or ()) for r in records)
        changes = []
        for commit in self._commits(project, seen, tip):
            if commit["email"] == OWN_EMAIL or OWN_SUBJECTS.match(commit["subject"]) or commit["pr"] in own_prs:
                continue
            number += 1
            changes.append(self._handle(slug, project, branch, commit, f"R-{number}", at))
        record = {"at": at, "from": seen, "to": tip, "changes": changes}
        self._append(slug, record)
        if changes:
            self.daemon.announce(self._digest(slug, branch, changes))
            for change in changes:
                if change["question"]:
                    self.daemon.announce(self._question(slug, change))
        return record

    def _commits(self, project, seen, tip):
        """The first-parent commits from seen to tip, oldest first: one per merged pull
        request, squash or merge commit, and one per direct commit."""
        out = _git(project, "log", "--first-parent", "--reverse", "--format=%H%x1f%an%x1f%ae%x1f%s%x1f%b%x1e",
                   f"{seen}..{tip}").stdout
        commits = []
        for chunk in out.split("\x1e"):
            parts = chunk.strip("\n").split("\x1f")
            if len(parts) < 5 or not parts[0].strip():
                continue
            match = PR_NUMBER.search(parts[3])
            commits.append({"sha": parts[0].strip(), "author": parts[1], "email": parts[2], "subject": parts[3],
                            "body": parts[4], "pr": int(next(g for g in match.groups() if g)) if match else None})
        return commits

    def _units(self, slug):
        for run_id in self.daemon.run_ids(slug):
            try:
                yield run_id, self.daemon.engine(slug, run_id)
            except Exception:  # noqa: BLE001, a run that will not load is not this change's concern
                continue

    def _own_prs(self, slug):
        numbers = set()
        for _, engine in self._units(slug):
            for unit_id in engine.units.ids():
                pr = engine.units.state(unit_id).get("pr") or {}
                if pr.get("number"):
                    numbers.add(int(pr["number"]))
        return numbers

    # --- one external change ---

    def _handle(self, slug, project, branch, commit, change_id, at):
        sha = commit["sha"]
        paths = [p for p in _git(project, "diff", "--name-only", f"{sha}^1", sha).stdout.splitlines() if p]
        if not paths:
            paths = [p for p in _git(project, "show", "--name-only", "--format=", sha).stdout.splitlines() if p]
        change = {"id": change_id, "commit": sha, "pr": commit["pr"], "author": commit["author"],
                  "subject": commit["subject"][:120], "paths": paths, "closed": [], "unknown_stories": [], "hints": [],
                  "overlap": [], "artifact_problems": [], "docs": [p for p in paths if p.startswith("docs/")]}
        backlog = BacklogStore(project)
        for story_id in dict.fromkeys(TRAILER.findall(commit["subject"] + "\n" + commit["body"])):
            try:
                backlog.close_story(story_id, "external", at, pr=commit["pr"], commit=sha, by=commit["author"])
                change["closed"].append(story_id)
            except (NotFound, IllegalTransition):
                change["unknown_stories"].append(story_id)
        change["hints"] = self._hints(slug, backlog, paths, change, at)
        change["checks"] = self._checks(project, paths)
        if change["closed"] and change["checks"].get("ran"):
            backlog.verify(change["closed"], change["checks"]["passed"])
        change["overlap"] = self._overlap(slug, branch, paths, commit)
        artifacts = [project / p for p in paths
                     if re.match(r"runs/[^/]+/artifacts/.*\.json$", p) and (project / p).exists()]
        if artifacts:
            change["artifact_problems"] = mechanical.validate_artifacts(artifacts, project)
        risk = _risk(project, sha)
        change["risk"] = {"level": risk["risk"], "categories": list(risk.get("categories") or ()),
                          "reasons": list(risk.get("reasons") or ())[:5]}
        change["question"] = risk["risk"] == "high"
        return change

    def _hints(self, slug, backlog, paths, change, at):
        """A not-done story whose units' declared paths the change touches gets a hint,
        never a close, because only a trailer or a person says a change finished it."""
        doc = backlog.sync() if paths else None
        if not doc:
            return []
        done = {s["story_id"] for f in backlog.features(doc) for s in f["stories"] if s.get("closed")}
        hinted = []
        for _, engine in self._units(slug):
            for story_id, unit_ids in story_units(engine.units).items():
                if story_id in done or story_id in hinted:
                    continue
                declared = {d for u in unit_ids for d in (engine.units.spec(u).get("declared_paths") or ())}
                overlap = sorted(p for p in paths if _under(p, declared))
                if not overlap:
                    continue
                try:
                    backlog.add_hint(story_id, {"change": change["id"], "pr": change["pr"], "commit": change["commit"][:12],
                                                "paths": overlap[:10], "at": at})
                    hinted.append(story_id)
                except NotFound:
                    continue
        return hinted

    def _checks(self, project, paths):
        """The project's product checks for the paths, once per change. A path under the
        run store, the docs, or the runtime is not the product."""
        watched = [p for p in paths if not p.startswith(("runs/", "docs/", ".claude/", ".github/"))]
        if not watched:
            return {"ran": False, "reason": "no product-facing path"}
        run_dir = project / CHECK_DIR
        run_dir.mkdir(parents=True, exist_ok=True)
        try:
            done = subprocess.run([sys.executable, str(_script(project, "product-check.py")), str(run_dir),
                                   "--touches", *watched], cwd=str(project), capture_output=True, text=True,
                                  timeout=CHECK_TIMEOUT)
        except subprocess.TimeoutExpired:
            return {"ran": True, "passed": False, "reason": f"the checks ran past {CHECK_TIMEOUT} seconds"}
        tail = (done.stdout + done.stderr).strip().splitlines()[-3:]
        if done.returncode == 3:
            return {"ran": False, "reason": "the project has no product checks"}
        if done.returncode == 0 and "nothing to run" in done.stdout:
            return {"ran": False, "reason": "no check watches the changed paths"}
        return {"ran": done.returncode in (0, 1), "passed": done.returncode == 0, "exit": done.returncode, "tail": tail}

    def _overlap(self, slug, branch, paths, commit):
        """An in-flight unit whose declared paths the change touches is told, so its next
        session rebases before it pushes, and the run's ledger says so."""
        told = []
        for run_id, engine in self._units(slug):
            if engine.cycles.is_complete():
                continue
            for state in engine.units.by_state("running", "ready", "retry", "redispatch", "returned", "checking", "gated"):
                unit_id = state["unit_id"]
                overlap = [p for p in paths if _under(p, engine.units.spec(unit_id).get("declared_paths") or ())]
                if not overlap:
                    continue
                who = f"#{commit['pr']}" if commit["pr"] else commit["sha"][:7]
                engine._append_note(unit_id, f"{branch} moved on {', '.join(overlap[:5])} ({commit['author']}, {who}). "
                                             f"Rebase your branch onto {branch} before you push.")
                engine.ledger.append("external_overlap", unit_id=unit_id, commit=commit["sha"], pr=commit["pr"],
                                     paths=overlap[:10])
                told.append({"run_id": run_id, "unit_id": unit_id, "paths": overlap[:10]})
        return told

    # --- what the person hears ---

    def _digest(self, slug, branch, changes):
        lines = [f"{slug}: {branch} moved by {_plural(len(changes), 'external change')}."]
        for c in changes:
            who = f"#{c['pr']}" if c["pr"] else c["commit"][:7]
            bits = [_plural(len(c["paths"]), "path")]
            if c["closed"]:
                bits.append("closed " + ", ".join(c["closed"]))
            if c["hints"]:
                bits.append("hinted " + ", ".join(c["hints"]))
            if c["checks"].get("ran"):
                bits.append("product checks " + ("passed" if c["checks"].get("passed") else "failed"))
            if c["overlap"]:
                bits.append(_plural(len(c["overlap"]), "in-flight unit") + " told")
            if c["artifact_problems"]:
                bits.append(_plural(len(c["artifact_problems"]), "artifact") + " failing validation")
            if c["docs"]:
                bits.append("docs edited by hand")
            lines.append(f"{c['id']} {who} by {c['author']}: {c['subject'][:60]} ({', '.join(bits)})")
        return "\n".join(lines)

    def _question(self, slug, change):
        reasons = "\n".join(f"  {r}" for r in change["risk"]["reasons"][:3])
        areas = ", ".join(change["risk"]["categories"]) or "a gate-list area"
        return (f"{slug}: {change['id']} touches {areas}.\n{reasons}\n"
                f"Answer with /springer reconcile {slug} {change['id']} decision \"<the decision-log line>\", "
                f"/springer reconcile {slug} {change['id']} not-architecture, or "
                f"/springer reconcile {slug} {change['id']} review, which opens a polish run that reviews it.")

    def answer(self, slug, change_id, option, text, by, now):
        """The person's answer to a question on one change, recorded once. A review opens
        a polish run on the change."""
        if option not in OPTIONS:
            raise InvalidArgs(f"the answer is one of {', '.join(OPTIONS)}")
        records = self.records(slug)
        change = next((c for r in records for c in r.get("changes") or () if c["id"] == change_id), None)
        if change is None:
            raise NotFound(f"no change {change_id} in {slug}")
        if not change.get("question"):
            raise IllegalTransition(f"{change_id} asked no question")
        if any((r.get("answer") or {}).get("change") == change_id for r in records):
            raise IllegalTransition(f"{change_id} is answered")
        if option == "decision" and not (text or "").strip():
            raise InvalidArgs("A decision needs the line to record.")
        answer = {"change": change_id, "option": option, "text": (text or "").strip() or None, "by": by}
        if option == "review":
            who = f"#{change['pr']}" if change.get("pr") else change["commit"][:7]
            answer["run_id"] = self.daemon.start_run(
                slug, "build", lane="polish",
                issue=f"Review the external change {who} by {change['author']}: {change['subject']}")
        self._append(slug, {"at": iso(now), "answer": answer})
        return answer
