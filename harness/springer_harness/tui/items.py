"""Core flows and Users as items with fields. The brief stores both as Markdown in the
format the critique parses, and this module reads that format leniently and writes it
exactly, so a person fills in fields and never types the format. A test holds the
written text to the API's parser."""

import re

FLOW_FIELDS = ("who", "trigger", "outcome", "critical", "surface")
_FIELD = re.compile(r"^(Who|Trigger|Outcome|Critical|Surface)\s*:\s*(.*)$", re.IGNORECASE)
_STEP = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+(.*)$")
_USER = re.compile(r"^- ([^:\n]+?)\s*(?::\s*(.*))?$")
YES = ("yes", "y", "true")


def blank_flow():
    return {"name": "", "who": "", "trigger": "", "steps": [], "outcome": "", "critical": False, "surface": "",
            "extra": []}


def parse_flows(text):
    """Returns (preamble, flows). Text before the first ### heading is kept as the
    preamble, and a line inside a flow that is not a field or a step is kept as extra."""
    parts = re.split(r"(?m)^###[ \t]+", text or "")
    preamble, flows = parts[0].strip(), []
    for block in parts[1:]:
        name, _, rest = block.partition("\n")
        flow = {**blank_flow(), "name": name.strip(), "steps": [], "extra": []}
        for line in rest.splitlines():
            if not line.strip():
                continue
            field, step = _FIELD.match(line.strip()), _STEP.match(line)
            if field:
                key, value = field.group(1).lower(), field.group(2).strip()
                flow[key] = value.lower() in YES if key == "critical" else value
            elif step:
                flow["steps"].append(step.group(1).strip())
            else:
                flow["extra"].append(line.rstrip())
        flows.append(flow)
    return preamble, flows


def write_flows(preamble, flows):
    blocks = [preamble] if preamble else []
    for flow in flows:
        lines = [f"### {flow['name'].strip()}"]
        for key in ("who", "trigger"):
            if flow.get(key, "").strip():
                lines.append(f"{key.capitalize()}: {flow[key].strip()}")
        steps = [s.strip() for s in flow["steps"] if s.strip()]
        lines += [f"{n}. {step}" for n, step in enumerate(steps, 1)]
        if flow.get("outcome", "").strip():
            lines.append(f"Outcome: {flow['outcome'].strip()}")
        lines.append(f"Critical: {'yes' if flow.get('critical') else 'no'}")
        if flow.get("surface", "").strip():
            lines.append(f"Surface: {flow['surface'].strip()}")
        lines += flow.get("extra", [])
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n" if blocks else ""


def missing(flow):
    """What a flow still needs before the run can start, in the words a person reads."""
    gaps = [label for key, label in (("who", "who"), ("trigger", "a trigger"), ("outcome", "an outcome"))
            if not flow.get(key, "").strip()]
    if not any(s.strip() for s in flow["steps"]):
        gaps.insert(2, "steps")
    return gaps


def parse_users(text):
    """Returns (preamble, users). A user is a `- Name: about` line or a ### heading with
    text under it. Every other line is kept as the preamble."""
    preamble, users = [], []
    current = None
    for line in (text or "").splitlines():
        bullet = _USER.match(line)
        if line.startswith("### "):
            current = {"name": line[4:].strip(), "about": ""}
            users.append(current)
        elif bullet:
            current = None
            users.append({"name": bullet.group(1).strip(), "about": (bullet.group(2) or "").strip()})
        elif current is not None and line.strip():
            current["about"] = " ".join(x for x in (current["about"], line.strip()) if x)
        elif line.strip() or preamble:
            current = None
            preamble.append(line)
    return "\n".join(preamble).strip(), users


def write_users(preamble, users):
    lines = [f"- {u['name'].strip()}: {u['about'].strip()}" if u["about"].strip() else f"- {u['name'].strip()}"
             for u in users]
    blocks = [b for b in (preamble, "\n".join(lines)) if b]
    return "\n\n".join(blocks) + "\n" if blocks else ""


# --- every other section, as a form or a list of items ---
# A spec is (key, label, kind), kind being line (one line) or text (a paragraph). The
# label is what the file carries, so an agent reading the brief reads the question.

FORMS = {
    "Idea": (("idea", "The idea", "text"), ("for", "Who it might be for", "line")),
    "Problem": (("hard", "What is hard today", "text"), ("who", "Who has it", "line"),
                ("now", "What they do now", "line"), ("why", "Why it matters now", "line")),
    "Design preferences": (("feel", "The feel", "line"), ("like", "Sites or apps you like", "line"),
                           ("avoid", "What to avoid", "line")),
}
LISTS = {
    "Non-goals": (("text", "Not in the first version", "line"),),
    "Success criteria": (("measure", "What you measure", "line"), ("target", "The target", "line")),
    "Constraints": (("limit", "The limit", "line"), ("kind", "Kind", "line")),
    "Inputs and references": (("source", "Path or link", "line"), ("use", "What it is for", "line")),
    "Glossary": (("term", "Term", "line"), ("meaning", "Meaning", "line")),
    "Open questions": (("question", "Question", "line"), ("who", "Who can answer", "line")),
}
NOUNS = {"Users": "user", "Core flows": "flow", "Non-goals": "non-goal", "Success criteria": "measure",
         "Constraints": "constraint", "Inputs and references": "input", "Glossary": "term",
         "Open questions": "question"}


def parse_form(section, text):
    """Returns ("", values). A line opening with a label starts that field, and text
    before any label (a paragraph written before the form existed) goes to the first."""
    specs = FORMS[section]
    labels = {label.lower(): key for key, label, _ in specs}
    values = {key: [] for key, _, _ in specs}
    current = specs[0][0]
    for line in (text or "").splitlines():
        head, colon, rest = line.partition(":")
        if colon and head.strip().lower() in labels:
            current = labels[head.strip().lower()]
            line = rest.strip()
        values[current].append(line)
    return "", {key: "\n".join(lines).strip() for key, lines in values.items()}


def write_form(section, preamble, values):
    lines = []
    for key, label, kind in FORMS[section]:
        value = values.get(key, "").strip()
        if value:
            lines.append(f"{label}: {value}")
    return "\n\n".join(lines) + "\n" if lines else ""


def parse_list(section, text):
    """Returns (preamble, items). An item is a `- ` line holding the first field, with
    `  Label: value` lines under it for the rest. A `- a: b` line from before the form
    splits at the colon when the list has a second field."""
    specs = LISTS[section]
    labels = {label.lower(): key for key, label, _ in specs[1:]}
    preamble, found, current = [], [], None
    for line in (text or "").splitlines():
        if line.startswith(("- ", "* ")):
            current = {key: "" for key, _, _ in specs}
            current[specs[0][0]] = line[2:].strip()
            found.append(current)
            continue
        head, colon, rest = line.strip().partition(":")
        if current is not None and line[:1].isspace() and colon and head.strip().lower() in labels:
            current[labels[head.strip().lower()]] = rest.strip()
        elif current is not None and line[:1].isspace() and line.strip():
            first = specs[0][0]
            current[first] = f"{current[first]} {line.strip()}".strip()
        elif line.strip() or preamble:
            current = None
            preamble.append(line)
    if len(specs) > 1:
        for item in found:
            first, second = specs[0][0], specs[1][0]
            if not any(item[k] for k, _, _ in specs[1:]) and ": " in item[first]:
                item[first], item[second] = (part.strip() for part in item[first].split(": ", 1))
    return "\n".join(preamble).strip(), found


def write_list(section, preamble, found):
    specs = LISTS[section]
    blocks = []
    for item in found:
        lines = [f"- {item[specs[0][0]].strip()}"]
        lines += [f"  {label}: {item[key].strip()}" for key, label, _ in specs[1:] if item.get(key, "").strip()]
        blocks.append("\n".join(lines))
    parts = [b for b in (preamble, "\n".join(blocks)) if b]
    return "\n\n".join(parts) + "\n" if parts else ""


def codec(section):
    """(parse, write) for a section, each taking and giving (preamble, content)."""
    if section == "Core flows":
        return parse_flows, write_flows
    if section == "Users":
        return parse_users, write_users
    if section in FORMS:
        return (lambda text: parse_form(section, text)), (lambda pre, values: write_form(section, pre, values))
    if section in LISTS:
        return (lambda text: parse_list(section, text)), (lambda pre, found: write_list(section, pre, found))
    return None


def prose_of(section, content):
    """The text a person wrote, keyed by field, for proofreading. A name a person picked
    from a list (who) and a path or link are not prose."""
    if section == "Core flows":
        texts = {"name": content["name"], "trigger": content["trigger"], "outcome": content["outcome"]}
        texts.update({f"step-{n}": s for n, s in enumerate(content["steps"])})
    elif section == "Inputs and references":
        texts = {"use": content.get("use", "")}
    else:
        texts = dict(content)
    return {k: v for k, v in texts.items() if isinstance(v, str) and v.strip()}


def with_prose(section, content, texts):
    """content with the proofread texts put back where prose_of took them."""
    content = {**content, **{k: v for k, v in texts.items() if not k.startswith("step-")}}
    if section == "Core flows":
        content["steps"] = [texts.get(f"step-{n}", s) for n, s in enumerate(content["steps"])]
    return content


def apply_fixes(text, fixes):
    """fixes is a list of (offset, length, replacement). Applied from the end, so an
    earlier offset still points where it did."""
    for offset, length, replacement in sorted(fixes, reverse=True):
        text = text[:offset] + replacement + text[offset + length:]
    return text
