"""docs/brief.md: YAML frontmatter for the machine fields, prose sections for the
product. The daemon is its only writer while a client is connected, and each write
bumps brief_version, which a client echoes as base_version."""

import re
from pathlib import Path

import yaml

from ..common import write_text
from ..errors import InvalidArgs, NotFound, StaleVersion

REQUIRED = ("Problem", "Users", "Core flows", "Non-goals")
SECTION_ORDER = ("Idea", "Problem", "Users", "Core flows", "Non-goals", "Success criteria", "Constraints",
                 "Design preferences", "Inputs and references", "Glossary", "Open questions")
NOT_FACTS = {"brief_version", "name", "profile", "lane", "proposed", "recommendation"}
FACT_NAMES = {"surfaces", "backend", "accounts", "payments", "scale", "autonomy", "deploy", "staging", "reach",
              "frameworks", "variants", "reference", "pinned", "budget", "live"}


def derive(facts):
    """The profile table in the design notes, in its precedence, plus the sentence
    that names the fact a person would change to correct it."""
    surfaces = facts.get("surfaces") or []
    money = facts.get("payments", "none") not in ("none", None, False)
    tenants = facts.get("accounts") == "multi-org"
    has_backend = facts.get("backend") not in ("none", None, False)
    if facts.get("scale") == "personal":
        profile, why = "small", "A personal product takes the small ceremony on any surface"
    elif "mobile" in surfaces:
        profile, why = "mobile", "A product with a mobile surface"
    elif money or tenants:
        profile, why = "saas", "A product that charges money or serves many organizations"
    elif surfaces and set(surfaces) <= {"api", "cli"}:
        profile, why = "api", "A product with only an api or cli surface"
    elif has_backend:
        profile, why = "small", "A web product with a backend"
    else:
        profile, why = "brochure", "A web product with no backend"
    lane = "polish" if facts.get("live") else "build"
    return {"profile": profile, "lane": lane, "sentence": f"{why} runs as {profile}."}


def render(front, sections):
    body = "".join(f"## {name}\n\n{text.strip()}\n\n" for name, text in sections.items())
    return f"---\n{yaml.safe_dump(front, sort_keys=False)}---\n\n{body}".rstrip() + "\n"


def parse(text):
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not match:
        raise InvalidArgs("docs/brief.md has no frontmatter")
    front = yaml.safe_load(match.group(1)) or {}
    sections = {}
    current = None
    for line in match.group(2).splitlines():
        heading = re.match(r"^## (.+?)\s*$", line)
        if heading:
            current = heading.group(1)
            sections[current] = []
        elif current:
            sections[current].append(line)
    return front, {name: "\n".join(lines).strip() for name, lines in sections.items()}


class BriefStore:
    def __init__(self, project_path):
        self.path = Path(project_path) / "docs" / "brief.md"

    def exists(self):
        return self.path.exists()

    def create(self, name):
        front = {"brief_version": 1, "name": name, "surfaces": ["web"], "autonomy": "standard", "proposed": []}
        write_text(self.path, render(self._stamped(front), {}))

    def _stamped(self, front):
        """The derived fields the harness writes. The sentence is computed on read."""
        derived = derive(front)
        return {**front, "profile": derived["profile"], "lane": derived["lane"]}

    def load(self):
        if not self.path.exists():
            raise NotFound("the project has no docs/brief.md")
        return parse(self.path.read_text())

    def text(self):
        return self.path.read_text()

    def restore(self, text):
        write_text(self.path, text)

    def facts(self, front):
        return {k: v for k, v in front.items() if k not in NOT_FACTS}

    def view(self, started):
        front, sections = self.load()
        proposed = set(front.get("proposed") or [])
        # Every section is offered so a person can fill it. Idea is the entry point
        # from Discovery, so it shows until the product sections have text.
        started_writing = any(sections.get(n) for n in REQUIRED)
        names = [n for n in SECTION_ORDER if n != "Idea" or sections.get("Idea") or not started_writing] + \
                [n for n in sections if n not in SECTION_ORDER]
        return {"version": front.get("brief_version", 1), "started": started, "facts": self.facts(front),
                "derived": derive(front),
                "sections": [{"name": n, "required": n in REQUIRED,
                              "confidence": "proposed" if n in proposed else
                              ("confirmed" if sections.get(n) else "needs-human-input"),
                              "body": sections.get(n, "")} for n in names],
                "recommendation": front.get("recommendation")}

    def check_version(self, base_version):
        front, _ = self.load()
        current = front.get("brief_version", 1)
        if base_version != current:
            raise StaleVersion(f"The brief changed since version {base_version}.", {"current_version": current})

    def _write(self, front, sections):
        front["brief_version"] = front.get("brief_version", 1) + 1
        write_text(self.path, render(self._stamped(front), sections))
        return front["brief_version"]

    def update_section(self, section, body, base_version):
        self.check_version(base_version)
        front, sections = self.load()
        sections[section] = body
        front["proposed"] = [n for n in front.get("proposed") or [] if n != section]
        return self._write(front, sections)

    def update_facts(self, facts, base_version):
        self.check_version(base_version)
        unknown = set(facts) - FACT_NAMES
        if unknown:
            raise InvalidArgs(f"unknown brief facts: {sorted(unknown)}")
        front, sections = self.load()
        front.update(facts)
        return self._write(front, sections)

    def confirm_section(self, section, base_version):
        self.check_version(base_version)
        front, sections = self.load()
        front["proposed"] = [n for n in front.get("proposed") or [] if n != section]
        return self._write(front, sections)

    def dismiss_recommendation(self):
        front, sections = self.load()
        if front.get("recommendation"):
            front["recommendation"]["dismissed"] = True
        return self._write(front, sections)
