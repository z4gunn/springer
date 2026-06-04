#!/usr/bin/env python3
"""Check that a state diagram's state names match the entity's status enum in
the ERD, so the lifecycle diagram and the data model never drift.

The ERD is the source of truth for the status field (see generate-erd). This
check reads an ERD artifact JSON, validates it against the registered erd schema
through the shared registry validator at schemas/validate.py rather than
restating field requirements, then extracts the status enum for the named entity
and compares it to the states parsed from the diagram source.

Status-enum location in an erd artifact: the entity's attribute whose name
contains "status" (or "state"), with allowed values taken from, in order, its
`type` like enum(a,b,c), or any constraint string like enum(a,b,c) /
check(... in (...)) / one in a("a","b") list.

If the ERD has no such entity or no status enum, the check reports
"no ERD status enum found" and exits 0 rather than failing hard, because not
every entity carries an enumerated status.

Usage:
    check-status-consistency.py <diagram.mmd|diagram.puml> <erd-artifact.json> <entity-name>
Exit 0 = consistent, or no enum to check against. Exit 1 = drift found.
Exit 2 = usage/read error.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
VALIDATE_PY = REPO_ROOT / "schemas" / "validate.py"

INIT = "[*]"
TRANSITION = re.compile(
    r"^\s*([A-Za-z0-9_\[\]*]+)\s*-+>\s*([A-Za-z0-9_\[\]*]+)\s*(?::.*)?$"
)
PSEUDO = re.compile(r"^\s*state\s+([A-Za-z0-9_]+)\s*<<(?:choice|fork|join|history)>>")
ENUM_PAREN = re.compile(r"enum\s*\(([^)]*)\)", re.IGNORECASE)
IN_LIST = re.compile(r"in\s*\(([^)]*)\)", re.IGNORECASE)


def parse_states(text):
    states = set()
    pseudo = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("%%") or line.startswith("'"):
            continue
        ps = PSEUDO.match(line)
        if ps:
            pseudo.add(ps.group(1))
            continue
        m = TRANSITION.match(line)
        if not m:
            continue
        for node in (m.group(1), m.group(2)):
            node = re.sub(r"\[H\*?\]$", "", node)  # strip history marker
            if node != INIT:
                states.add(node)
    return states - pseudo


def split_values(raw):
    vals = []
    for tok in raw.split(","):
        tok = tok.strip().strip("'\"").strip()
        if tok:
            vals.append(tok)
    return vals


def extract_status_enum(erd, entity_name):
    """Return (attr_name, [values]) or None if no status enum is found."""
    content = erd.get("content", {})
    for ent in content.get("entities", []):
        if ent.get("name", "").lower() != entity_name.lower():
            continue
        for attr in ent.get("attributes", []):
            aname = attr.get("name", "")
            if "status" not in aname.lower() and "state" not in aname.lower():
                continue
            # values may live in the type or in a constraint string
            candidates = [attr.get("type", "")] + list(attr.get("constraints", []))
            for cand in candidates:
                m = ENUM_PAREN.search(cand) or IN_LIST.search(cand)
                if m:
                    return aname, split_values(m.group(1))
    return None


def validate_erd(erd_path):
    """Run the shared registry validator. Returns (ok, message)."""
    if not VALIDATE_PY.exists():
        return False, f"registry validator not found at {VALIDATE_PY}"
    proc = subprocess.run(
        [sys.executable, str(VALIDATE_PY), str(erd_path), "erd", "v1"],
        capture_output=True, text=True,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


def normalize(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def main(argv):
    if len(argv) != 4:
        sys.stderr.write(__doc__)
        return 2
    diagram_path, erd_path, entity = Path(argv[1]), Path(argv[2]), argv[3]
    try:
        diagram_text = diagram_path.read_text()
        erd = json.loads(erd_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read input: {exc}", file=sys.stderr)
        return 2

    ok, msg = validate_erd(erd_path)
    if not ok:
        print(f"ERD does not validate against the registered erd schema:\n{msg}", file=sys.stderr)
        return 2

    found = extract_status_enum(erd, entity)
    if found is None:
        print(f"no ERD status enum found for entity '{entity}' in {erd_path}")
        return 0

    attr_name, enum_values = found
    states = parse_states(diagram_text)
    enum_norm = {normalize(v): v for v in enum_values}
    state_norm = {normalize(s): s for s in states}

    missing_in_diagram = [enum_norm[k] for k in enum_norm if k not in state_norm]
    extra_in_diagram = [state_norm[k] for k in state_norm if k not in enum_norm]

    if not missing_in_diagram and not extra_in_diagram:
        print(f"CONSISTENT: {entity}.{attr_name} enum matches diagram states "
              f"({len(enum_values)} values)")
        return 0

    print(f"DRIFT: {entity}.{attr_name} enum and diagram states disagree")
    for v in sorted(missing_in_diagram):
        print(f"  - enum value '{v}' has no matching state in the diagram")
    for v in sorted(extra_in_diagram):
        print(f"  - diagram state '{v}' has no matching enum value in the ERD")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
