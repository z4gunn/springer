"""Adopt an existing Springer instance: one built before the daemon, with its own run
store, rulings, and runtime copy.

plan(target) reads and writes nothing. apply(...) writes only what Springer owns:
runtime files the instance never edited, .claude/springer-manifest.json, new template
renderings under .claude/springer-update/ for a hand merge, docs/brief.md and DESIGN.md
when the instance has none, and the daemon's own index under ~/.springer. Everything
else in the repository, the run store included, is the project's and is only read.
"""

import importlib.util
import json
import re
from pathlib import Path

from .common import iso, read_json, write_json
from .state.brief import BriefStore, derive

SOURCE = Path(__file__).resolve().parents[2]
UPDATE_DIR = ".claude/springer-update"
# Folders a repository commonly holds beside its product that a run must never touch.
PROJECT_OWNED_HINTS = ("Claude outputs", "dist-deploy", "verification", "node_modules", "dist", "build")
WEB = ("react", "vite", "next", "svelte", "vue", "astro", "@remix-run/react")
MOBILE = ("expo", "react-native")
BACKEND = ("express", "fastify", "hono", "@supabase/supabase-js", "koa", "@nestjs/core", "pg", "drizzle-orm", "prisma")


def _updater():
    spec = importlib.util.spec_from_file_location("springer_update_project", SOURCE / "scripts" / "update-project.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _content(doc):
    return doc.get("content", doc) if isinstance(doc, dict) else {}


def _stamp(doc):
    return (doc or {}).get("timestamp") or ""


# --- reading the run store ---

def run_briefs(target):
    """Every run brief written before the daemon, oldest first. A daemon run carries
    `kind` and is not history."""
    found = []
    for path in sorted((target / "runs").glob("*/run-brief.json")):
        doc = read_json(path)
        if not isinstance(doc, dict) or _content(doc).get("kind"):
            continue
        found.append((path.parent.name, doc))
    return sorted(found, key=lambda item: (_stamp(item[1]), (target / "runs" / item[0]).stat().st_mtime))


def artifacts(target, artifact_type):
    """Every artifact of a type across runs, oldest first."""
    found = []
    for path in (target / "runs").glob("*/artifacts/*.json"):
        doc = read_json(path)
        if isinstance(doc, dict) and doc.get("artifact_type") == artifact_type:
            found.append((path, doc))
    return sorted(found, key=lambda item: (_stamp(item[1]), item[0].stat().st_mtime))


def latest_confirmed(target, artifact_type):
    docs = artifacts(target, artifact_type)
    confirmed = [d for d in docs if _content(d[1]).get("status") == "confirmed" or d[1].get("status") == "confirmed"]
    return (confirmed or docs or [(None, None)])[-1]


# --- facts ---

def _deps(target):
    names = set()
    for path in [target / "package.json", *target.glob("packages/*/package.json"), *target.glob("apps/*/package.json")]:
        data = read_json(path) or {}
        for key in ("dependencies", "devDependencies"):
            names |= set((data.get(key) or {}).keys())
    return names


def detect_facts(target):
    """What the tree shows, each with how it was found."""
    deps = _deps(target)
    facts, sources = {}, {}
    surfaces = []
    if deps & set(MOBILE):
        surfaces.append("mobile")
    if deps & set(WEB) or any((target / p).exists() for p in ("index.html", "site/index.html", "public/index.html")):
        surfaces.append("web")
    if surfaces:
        facts["surfaces"], sources["surfaces"] = surfaces, "detected"
    backend = bool(deps & set(BACKEND)) or (target / "supabase").is_dir()
    facts["backend"], sources["backend"] = ("yes" if backend else "none"), "detected"
    if "stripe" in deps:
        facts["payments"], sources["payments"] = "subscription", "detected"
    return facts, sources


def reconcile(facts, sources, profile):
    """Adjust the fewest facts so the brief derives the profile the runs used, and say
    which ones were inferred from it."""
    facts = dict(facts)
    if not profile or derive(facts)["profile"] == profile:
        return facts
    fixes = {"saas": {"accounts": "multi-org"}, "small": {"backend": "yes"}, "brochure": {"backend": "none"},
             "mobile": {"surfaces": sorted(set(facts.get("surfaces") or []) | {"mobile"})},
             "api": {"surfaces": ["api"]}}
    for key, value in fixes.get(profile, {}).items():
        facts[key], sources[key] = value, f"from the {profile} profile the runs used"
    if profile == "saas" and derive(facts)["profile"] != "saas":
        facts["payments"] = facts.get("payments") or "subscription"
    return facts


def resolve_reference(target, value):
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute() and not re.match(r"^[a-z]+://", value):
        path = (target / path).resolve()
    return str(path) if not re.match(r"^[a-z]+://", value) else value


def derive_facts(target):
    briefs = run_briefs(target)
    latest = _content(briefs[-1][1]) if briefs else {}
    flags = latest.get("flags") or {}
    facts, sources = detect_facts(target)
    profile = latest.get("profile")
    facts = reconcile(facts, sources, profile)
    facts["live"], sources["live"] = True, "an adopted product already exists"
    if flags.get("autonomy"):
        facts["autonomy"], sources["autonomy"] = flags["autonomy"], "the latest run brief"
    reference = next((_content(d).get("flags", {}).get("reference") for _, d in reversed(briefs)
                      if (_content(d).get("flags") or {}).get("reference")), None)
    facts["reference"] = resolve_reference(target, reference) if reference else str(target)
    sources["reference"] = "a run brief, resolved from the project path" if reference else "the repository itself"
    rulings, seen = [], set()
    for _, doc in briefs:
        for ruling in _content(doc).get("pinned_rulings") or []:
            text = ruling if isinstance(ruling, str) else json.dumps(ruling)
            if text not in seen:
                seen.add(text)
                rulings.append(text)
    facts["pinned_rulings"], sources["pinned_rulings"] = rulings, f"{len(briefs)} run brief(s)"
    return facts, sources, profile


# --- sections ---

def _text(value):
    if isinstance(value, dict):
        return value.get("text") or value.get("summary") or value.get("statement") or ""
    return value if isinstance(value, str) else ""


def _first_sentence(text, limit=90):
    text = " ".join((text or "").split())
    cut = re.split(r"(?<=[.!?])\s", text, 1)[0]
    return cut if len(cut) <= limit else cut[:limit - 1].rstrip() + "…"


def persona_name(persona, icp):
    """A person's name for the Users list: a name field, else the name a use case opens
    with ("Ola the shop owner (primary): ..."), else the ICP audience a reference points
    at, else the id."""
    use = " ".join((persona.get("primary_use_case") or "").split())
    use = re.sub(r"^Unchanged from [\w-]+\.\s*", "", use)
    if persona.get("name") or persona.get("persona_name"):
        return str(persona.get("name") or persona.get("persona_name")), _first_sentence(use, 160)
    opening = re.match(r"^([A-Z][^:(.]{2,60}?)\s*[(:]", use)
    if opening:
        rest = use[opening.end():]
        if use[opening.end() - 1] == "(" and ")" in rest:
            rest = rest.split(")", 1)[1]
        return opening.group(1).strip(), _first_sentence(rest.lstrip(" :"), 160)
    ref = str(persona.get("persona_id") or "")
    if "#" in ref:
        audience = icp.get(ref.split("#", 1)[1].replace("-", "_")) or {}
        if audience.get("label"):
            return audience["label"].split(",")[0], _first_sentence(audience.get("definition") or use, 160)
    return ref, _first_sentence(use, 160)


def _goal_name(text):
    """A goal's words without its id ("G10. A visitor sees ..." reads "A visitor sees ...")."""
    return _first_sentence(re.sub(r"^[A-Z]+-?\d+[.:)]?\s+", "", " ".join((text or "").split())))


def derive_sections(target):
    """Brief sections from the latest confirmed PRD, its personas, the ICP, and epics."""
    from .tui import items  # the one writer of the brief's section format

    _, prd = latest_confirmed(target, "prd")
    _, icp = latest_confirmed(target, "icp")
    prd_c, icp_c = _content(prd), _content(icp)
    sections, origin = {}, {}
    problem = _text(prd_c.get("problem_statement"))
    if problem:
        sections["Problem"] = items.write_form("Problem", "", {"hard": problem})
        origin["Problem"] = "the latest confirmed PRD"
    users = []
    persona = icp_c.get("persona") or {}
    if persona.get("name"):
        users.append({"name": persona["name"], "about": persona.get("archetype_label") or ""})
    for p in prd_c.get("personas") or []:
        if persona.get("persona_id") and p.get("persona_id") == persona.get("persona_id"):
            continue
        name, about = persona_name(p, icp_c)
        if name and not any(u["name"].lower() == name.lower() for u in users):
            users.append({"name": name, "about": about})
    if users:
        sections["Users"] = items.write_users("", users)
        origin["Users"] = "the ICP and the PRD personas"
    who = users[0]["name"] if users else ""
    flows = []
    epics = []
    for _, doc in artifacts(target, "prioritized-backlog") + artifacts(target, "user-story"):
        epics = _content(doc).get("epics") or epics
    for n, epic in enumerate(epics[:12]):
        stories = [s.get("title") or s.get("story_id") for s in epic.get("stories") or [] if isinstance(s, dict)]
        flows.append({**items.blank_flow(), "name": epic.get("title") or epic.get("name") or f"Epic {n + 1}",
                      "who": who, "steps": [s for s in stories if s][:12],
                      "outcome": _text(epic.get("outcome") or epic.get("goal") or epic.get("description")),
                      "critical": bool(epic.get("critical") or epic.get("mvp") or n == 0)})
    if not flows:
        for n, goal in enumerate(prd_c.get("goals") or []):
            if isinstance(goal, dict):
                flows.append({**items.blank_flow(), "name": _goal_name(goal.get("goal") or ""), "who": who,
                              "outcome": goal.get("success_metric") or "", "critical": n == 0})
    if flows:
        sections["Core flows"] = items.write_flows("", flows)
        origin["Core flows"] = "the backlog's epics" if epics else "the PRD goals (no epics in the run store)"
    non_goals = [{"text": _first_sentence(o.get("item") or o.get("feature") or "", 140)}
                 for o in prd_c.get("out_of_scope") or [] if isinstance(o, dict)]
    if non_goals:
        sections["Non-goals"] = items.write_list("Non-goals", "", non_goals)
        origin["Non-goals"] = "the PRD out-of-scope list"
    metrics = [{"measure": m.get("metric") or "", "target": m.get("target") or ""}
               for m in prd_c.get("success_metrics") or [] if isinstance(m, dict) and m.get("metric")]
    if metrics:
        sections["Success criteria"] = items.write_list("Success criteria", "", metrics)
        origin["Success criteria"] = "the PRD success metrics"
    return sections, origin


# --- DESIGN.md ---

def extract_design(target):
    """DESIGN.md from the latest design-system artifact, a mechanical transcription."""
    path, doc = latest_confirmed(target, "design-system")
    if doc is None:
        return None
    content = _content(doc)
    lines = ["# Design", "", f"Extracted by springer adopt from `{path.relative_to(target)}`. The run store stays the "
             "source of truth, so regenerate this rather than editing it.", ""]
    for key, value in content.items():
        if key in ("status", "run_id") or value in (None, "", [], {}):
            continue
        lines += [f"## {key.replace('_', ' ').capitalize()}", ""]
        if isinstance(value, (dict, list)):
            lines += ["```json", json.dumps(value, indent=2, ensure_ascii=False)[:6000], "```", ""]
        else:
            lines += [str(value), ""]
    if (target / "docs/design/index.html").exists():
        lines += ["## Mockups", "", "The design directions are served from `docs/design/index.html`.", ""]
    return "\n".join(lines)


# --- history ---

def history(target):
    """Each pre-daemon run as the daemon index keeps it: its cycles, its defaults
    ledger, and, for the latest retrospective, its learnings. A v1 cycle record has no
    unit_id, so a cycle is indexed by its routed agents instead."""
    runs = []
    briefs = dict(run_briefs(target))
    with_cycles = {p.parent.parent.name for p in (target / "runs").glob("*/artifacts/pdca-cycle-*.json")}
    order = [r for r in briefs] + sorted(with_cycles - set(briefs),
                                         key=lambda r: (target / "runs" / r).stat().st_mtime)
    for run_id in order:
        content = _content(briefs.get(run_id) or {})
        cycles = []
        for path in sorted((target / "runs" / run_id / "artifacts").glob("pdca-cycle-*.json")):
            c = _content(read_json(path) or {})
            routed = (c.get("plan") or {}).get("routed_batch") or []
            cycles.append({"cycle_id": c.get("cycle_id"), "phase": c.get("phase"),
                           "agents": sorted({r.get("agent") for r in routed if isinstance(r, dict) and r.get("agent")}),
                           "unit_ids": sorted({r["unit_id"] for r in routed if isinstance(r, dict) and r.get("unit_id")}),
                           "verdict": (c.get("check") or {}).get("verdict"),
                           "transition": (c.get("act") or {}).get("transition")})
        ledger = target / "runs" / run_id / "pending-defaults.md"
        defaults = [l[2:].strip() for l in ledger.read_text().splitlines() if l.startswith("- ")] if ledger.exists() else []
        runs.append({"run_id": run_id, "imported": True, "profile": content.get("profile"),
                     "lane": content.get("lane") or (content.get("flags") or {}).get("lane"),
                     "complete": bool(cycles) and cycles[-1]["transition"] == "complete",
                     "cycles": cycles, "defaults": defaults})
    retros = artifacts(target, "run-retrospective")
    learnings = []
    if retros:
        path, doc = retros[-1]
        learnings = [{"id": l.get("learning_id"), "category": l.get("category"), "observation": l.get("observation"),
                      "run_id": _content(doc).get("run_id")} for l in _content(doc).get("learnings") or []]
    return {"runs": runs, "learnings": learnings}


# --- the plan and its application ---

def plan(target):
    target = Path(target).expanduser().resolve()
    manifest = read_json(target / ".claude" / "springer-manifest.json")
    result = {"path": str(target), "instance": manifest is not None,
              "project_owned": [p for p in PROJECT_OWNED_HINTS if (target / p).exists()]}
    if manifest is None:
        return result
    updater = _updater()
    update = updater.plan_update(target, SOURCE, manifest)
    result["runtime"] = {"add": update["add"], "replace": update["replace"], "remove": update["remove"],
                         "unchanged": len(update["unchanged"]), "edited": update["keep_modified"] +
                         update["keep_modified_removed"], "instance_only": update["keep_instance_only"]}
    result["templates"] = {rel: "unchanged" for rel in update["template_unchanged"]}
    result["templates"].update({rel: f"new rendering in {UPDATE_DIR}/ for a hand merge"
                                for rel in update["template_replace"] + update["template_merge"]})
    facts, sources, profile = derive_facts(target)
    sections, origin = derive_sections(target)
    store = BriefStore(target)
    result.update(facts=facts, fact_sources=sources, profile=profile, derived=derive(facts),
                  brief="exists, kept" if store.exists() else "derived from the run store",
                  sections=sections, section_sources=origin,
                  design_md="exists, kept" if (target / "DESIGN.md").exists() else
                  ("extracted from the design system" if extract_design(target) else "none to extract"),
                  history=history(target))
    result["_update"] = update
    return result


def apply(target, adopt_plan, name, home_root, slug):
    """Write what the plan names and nothing else. Returns the files written."""
    target = Path(target).expanduser().resolve()
    updater = _updater()
    locks = updater.live_locks(target)
    if locks:
        raise RuntimeError("a harness holds a live lock on " + ", ".join(locks) + ". Adopt when it releases.")
    manifest = read_json(target / ".claude" / "springer-manifest.json")
    update = adopt_plan["_update"]
    sources = updater.source_runtime_files(SOURCE)
    written = []
    for rel in update["add"] + update["replace"]:
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(sources[rel].read_bytes())
        dest.chmod(sources[rel].stat().st_mode & 0o777)
        written.append(rel)
    for rel in update["remove"]:
        (target / rel).unlink()
        written.append(rel)
    renders = updater.renders_for(SOURCE, manifest)
    for rel in update["template_replace"] + update["template_merge"]:
        out = target / UPDATE_DIR / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(renders[rel][1])
        written.append(f"{UPDATE_DIR}/{rel}")
    new_manifest = updater.keep_ownership(
        updater.build_manifest(target, SOURCE, manifest.get("profile") or adopt_plan.get("profile") or "small",
                               previous=manifest), manifest, update)
    updater.write_manifest(target, new_manifest)
    written.append(".claude/springer-manifest.json")
    store = BriefStore(target)
    if not store.exists():
        store.create(name)
        version = store.load()[0]["brief_version"]
        for section, body in adopt_plan["sections"].items():
            version = store.update_section(section, body, version)
        store.update_facts({k: v for k, v in adopt_plan["facts"].items() if v is not None}, version)
        written.append("docs/brief.md")
    if not (target / "DESIGN.md").exists():
        design = extract_design(target)
        if design:
            (target / "DESIGN.md").write_text(design)
            written.append("DESIGN.md")
    write_json(Path(home_root) / "index" / f"{slug}.json",
               {"project": slug, "imported_at": iso(__import__("time").time()), **adopt_plan["history"]})
    return written


def public(adopt_plan):
    """The plan without the updater's internals, for the API."""
    return {k: v for k, v in adopt_plan.items() if not k.startswith("_")}
