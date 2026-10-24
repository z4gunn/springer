#!/usr/bin/env python3
"""Enforce the hard rules in CLAUDE.md on every skill, agent, and reference.

The per-artifact checklist in CLAUDE.md was a manual pass. This script is the
mechanical half of it: every rule a validator can check, checked the same way
every time, so a push that breaks one fails CI instead of being found by hand.
Stdlib only.

Usage:
    python3 scripts/validate-repo.py [repo-root]

Prints one line per violation, grouped by rule, and a summary. Exit 0 when
clean, 1 when any rule fails.

Rules checked (the guidance rules that need judgment are not here):
  skill frontmatter   `name` and `description`, then optionally
                      `disable-model-invocation: true` and nothing else, name
                      matches the dir
  skill description   present, at most 350 characters
  skill catalog       the skills the main session may invoke (those without
                      the flag) stay within a count and a character budget,
                      because each of their descriptions loads every session
  skill reachability  every skill is named by an agent, a shared reference,
                      the project CLAUDE.md template, a catalog skill, or a
                      skill those name, because a hidden skill nothing names
                      can never run
  skill body          under 500 lines after the frontmatter
  skill references    one level deep, a reference over 100 lines opens with
                      a Contents section
  skill extras        no README, CHANGELOG, or install or process document
  agent frontmatter   name, description, tools, model, name matches the file
  agent model         one of haiku, sonnet, opus
  agent skill path    the body states how a skill name resolves to its file
  voice               no em-dash in any authored markdown
  skill routing       no two skill descriptions closer than the overlap cap
                      (TF-IDF cosine), because the router picks by description
  references          a shared reference over 100 lines opens with a Contents
                      section
"""

import itertools
import math
import re
import sys
from pathlib import Path

DESCRIPTION_CAP = 350
OVERLAP_CAP = 0.75
STOP_WORDS = set("a an the and or of to for in on with by from as at is are be use when it its that this every each per into than then so not no any all one produce artifact agent report".split())
BODY_CAP = 500
TOC_THRESHOLD = 100
MODELS = {"haiku", "sonnet", "opus"}
EM_DASH = "—"
AUX_NAMES = re.compile(r"^(readme|changelog|install|installation|setup|contributing|process)(\..*)?$", re.I)
SKILL_PATH_SENTENCE = ".claude/skills/<name>/SKILL.md"
HIDDEN_KEY = "disable-model-invocation"
# The catalog is the set of skills whose descriptions load into every main
# session. Agents read their skills by path, so only the skills the main
# session invokes itself belong here. A new catalog skill fits under these
# caps or displaces one, the same rule the harness reference follows.
CATALOG_COUNT_CAP = 10
CATALOG_CHARS_CAP = 3000
SKILL_NAME = re.compile(r"\bspgr-[a-z0-9]+(?:-[a-z0-9]+)*\b")


def frontmatter(text):
    """Return (keys-in-order, dict, body) for a file starting with a YAML
    frontmatter block, or (None, None, text) when there is none. Values are
    taken as the raw single-line string after the colon."""
    if not text.startswith("---\n"):
        return None, None, text
    end = text.find("\n---", 4)
    if end < 0:
        return None, None, text
    block = text[4:end]
    keys, values = [], {}
    for line in block.splitlines():
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if m:
            keys.append(m.group(1))
            values[m.group(1)] = m.group(2).strip()
    body = text[end + 4:]
    body = body[1:] if body.startswith("\n") else body
    return keys, values, body


def has_contents(text):
    return re.search(r"^#{1,3}\s+Contents\s*$", text, re.M) is not None


class Report:
    def __init__(self):
        self.failures = {}

    def fail(self, rule, where, detail):
        self.failures.setdefault(rule, []).append(f"{where}: {detail}")

    def print(self, root):
        total = sum(len(v) for v in self.failures.values())
        for rule in sorted(self.failures):
            print(f"{rule} ({len(self.failures[rule])})")
            for line in self.failures[rule]:
                print(f"  {line}")
        if total:
            print(f"\nvalidate-repo: {total} violation(s) in {root}")
        else:
            print(f"validate-repo: clean ({root})")
        return 1 if total else 0


def check_skills(root, report, rel_dir=".claude/skills"):
    """The shape rules for every skill under rel_dir. The plugin's own
    skills under plugin/skills take the same rules and stay out of the
    catalog and reachability checks, which describe the runtime."""
    skills_dir = root / rel_dir
    if not skills_dir.is_dir():
        return
    for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        rel = f"{rel_dir}/{skill_dir.name}"
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            report.fail("skill-frontmatter", rel, "SKILL.md is missing")
            continue
        text = skill_md.read_text()
        keys, values, body = frontmatter(text)
        if keys is None:
            report.fail("skill-frontmatter", rel, "no frontmatter block")
        else:
            if keys not in (["name", "description"], ["name", "description", HIDDEN_KEY]):
                report.fail("skill-frontmatter", rel,
                            f"keys must be name, description, and optionally {HIDDEN_KEY} "
                            f"(found {', '.join(keys) or 'none'})")
            elif HIDDEN_KEY in keys and values.get(HIDDEN_KEY) != "true":
                report.fail("skill-frontmatter", rel,
                            f"{HIDDEN_KEY} must be true when present (found '{values.get(HIDDEN_KEY)}')")
            if values.get("name") != skill_dir.name:
                report.fail("skill-frontmatter", rel,
                            f"name '{values.get('name')}' does not match the directory")
            desc = values.get("description", "")
            if not desc:
                report.fail("skill-description", rel, "description is empty or multi-line")
            elif len(desc) > DESCRIPTION_CAP:
                report.fail("skill-description", rel,
                            f"description is {len(desc)} characters, cap is {DESCRIPTION_CAP}")
        body_lines = body.count("\n") + (1 if body and not body.endswith("\n") else 0)
        if body_lines >= BODY_CAP:
            report.fail("skill-body", rel, f"body is {body_lines} lines, must be under {BODY_CAP}")
        for extra in skill_dir.iterdir():
            if extra.is_file() and AUX_NAMES.match(extra.name) and extra.name != "SKILL.md":
                report.fail("skill-extras", rel, f"auxiliary file {extra.name} is not allowed")
        refs = skill_dir / "references"
        if refs.is_dir():
            for ref in sorted(refs.iterdir()):
                if ref.is_dir():
                    report.fail("skill-references", f"{rel}/references/{ref.name}",
                                "references must be one level deep")
                elif ref.suffix == ".md":
                    lines = ref.read_text().count("\n")
                    if lines > TOC_THRESHOLD and not has_contents(ref.read_text()):
                        report.fail("skill-references", f"{rel}/references/{ref.name}",
                                    f"{lines} lines without a Contents section")


def skill_frontmatters(root):
    """Map each skill directory name to (frontmatter values, body)."""
    out = {}
    for skill_dir in sorted(p for p in (root / ".claude" / "skills").iterdir() if p.is_dir()):
        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            _, values, body = frontmatter(skill_md.read_text())
            out[skill_dir.name] = (values or {}, body)
    return out


def is_catalog(values):
    return values.get(HIDDEN_KEY) != "true"


def check_catalog(root, report):
    """Every catalog description loads into every session, and the session
    listing truncates a long catalog without warning, so the catalog is
    budgeted as a whole and not only per description."""
    catalog = {name: values.get("description", "")
               for name, (values, _) in skill_frontmatters(root).items() if is_catalog(values)}
    chars = sum(len(d) for d in catalog.values())
    if len(catalog) > CATALOG_COUNT_CAP:
        report.fail("skill-catalog", ".claude/skills",
                    f"{len(catalog)} skills load into every session, cap is {CATALOG_COUNT_CAP}. "
                    f"Mark agent-only skills {HIDDEN_KEY}: true")
    if chars > CATALOG_CHARS_CAP:
        report.fail("skill-catalog", ".claude/skills",
                    f"catalog descriptions total {chars} characters, cap is {CATALOG_CHARS_CAP}")


def check_reachability(root, report):
    """A hidden skill is read by path from whoever names it. One that no
    agent, reference, template, or reachable skill names is dead weight that
    still claims a spec, so it fails. Catalog skills are roots because the
    main session can invoke them by description."""
    skills = skill_frontmatters(root)
    roots = {name for name, (values, _) in skills.items() if is_catalog(values)}
    sources = list((root / ".claude" / "agents").glob("*.md"))
    sources += list((root / ".claude" / "references").glob("*.md"))
    sources += [p for p in [root / "templates" / "project-CLAUDE.md"] if p.exists()]
    for path in sources:
        roots |= set(SKILL_NAME.findall(path.read_text())) & set(skills)
    reached, frontier = set(), list(roots)
    while frontier:
        name = frontier.pop()
        if name in reached or name not in skills:
            continue
        reached.add(name)
        skill_dir = root / ".claude" / "skills" / name
        text = "".join(p.read_text(errors="ignore") for p in skill_dir.rglob("*.md"))
        frontier.extend(set(SKILL_NAME.findall(text)) - reached)
    for name in sorted(set(skills) - reached):
        report.fail("skill-reachability", f".claude/skills/{name}",
                    "no agent, reference, template, or reachable skill names this skill")


def description_tokens(text):
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP_WORDS and len(w) > 2]


def check_routing(root, report):
    """Two skills whose descriptions read almost the same route the same
    request to either one. Cosine similarity over TF-IDF of the descriptions,
    failing a pair at OVERLAP_CAP or above. The IDF is smoothed so a corpus of
    two still scores identical text at one. The repo's closest pair sits well
    under the cap, so a new skill fails only when it restates an existing one."""
    docs = {}
    for skill_dir in sorted(p for p in (root / ".claude" / "skills").iterdir() if p.is_dir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        _, values, _ = frontmatter(skill_md.read_text())
        if values and values.get("description"):
            docs[skill_dir.name] = description_tokens(values["description"])
    if len(docs) < 2:
        return
    df = {}
    for toks in docs.values():
        for w in set(toks):
            df[w] = df.get(w, 0) + 1
    n = len(docs)
    vectors = {}
    for name, toks in docs.items():
        tf = {}
        for w in toks:
            tf[w] = tf.get(w, 0) + 1
        vec = {w: c * (math.log((n + 1) / (df[w] + 1)) + 1.0) for w, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in vec.values())) or 1.0
        vectors[name] = {w: x / norm for w, x in vec.items()}
    for a, b in itertools.combinations(sorted(vectors), 2):
        va, vb = vectors[a], vectors[b]
        score = sum(x * vb.get(w, 0.0) for w, x in va.items())
        if score >= OVERLAP_CAP:
            report.fail("skill-routing", f".claude/skills/{a}",
                        f"description overlaps {b} at {score:.2f}, cap is {OVERLAP_CAP:.2f}")


def check_agents(root, report):
    agents_dir = root / ".claude" / "agents"
    for agent_md in sorted(agents_dir.glob("*.md")):
        rel = f".claude/agents/{agent_md.name}"
        keys, values, body = frontmatter(agent_md.read_text())
        if keys is None:
            report.fail("agent-frontmatter", rel, "no frontmatter block")
            continue
        for required in ("name", "description", "tools", "model"):
            if required not in keys or not values.get(required):
                report.fail("agent-frontmatter", rel, f"missing {required}")
        if values.get("name") and values["name"] != agent_md.stem:
            report.fail("agent-frontmatter", rel,
                        f"name '{values['name']}' does not match the file")
        model = values.get("model")
        if model and model not in MODELS:
            report.fail("agent-model", rel, f"model '{model}' is not one of {', '.join(sorted(MODELS))}")
        if SKILL_PATH_SENTENCE not in body:
            report.fail("agent-skill-path", rel,
                        f"body must state that a skill name resolves to {SKILL_PATH_SENTENCE}")


def check_references(root, report):
    for ref in sorted((root / ".claude" / "references").glob("*.md")):
        text = ref.read_text()
        lines = text.count("\n")
        if lines > TOC_THRESHOLD and not has_contents(text):
            report.fail("references", f".claude/references/{ref.name}",
                        f"{lines} lines without a Contents section")


def check_voice(root, report):
    candidates = list((root / ".claude").rglob("*.md"))
    for name in ("README.md", "CLAUDE.md"):
        if (root / name).exists():
            candidates.append(root / name)
    candidates.extend((root / "templates").glob("*.md"))
    candidates.extend((root / "plugin").rglob("*.md"))
    for path in sorted(candidates):
        text = path.read_text()
        if EM_DASH in text:
            first = next(i for i, line in enumerate(text.splitlines(), 1) if EM_DASH in line)
            report.fail("voice", str(path.relative_to(root)), f"em-dash at line {first}")


def main(argv):
    root = Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parents[1]
    if not (root / ".claude" / "skills").is_dir():
        sys.stderr.write(f"no .claude/skills under {root}\n")
        return 1
    report = Report()
    check_skills(root, report)
    check_skills(root, report, "plugin/skills")
    check_routing(root, report)
    check_catalog(root, report)
    check_reachability(root, report)
    check_agents(root, report)
    check_references(root, report)
    check_voice(root, report)
    return report.print(root)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
