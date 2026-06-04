#!/usr/bin/env python3
"""Decide whether a state model must escalate from Mermaid to PlantUML, and
record the reason in the output so the choice is traceable.

Mermaid stateDiagram-v2 silently drops four feature families: history
pseudostates, entry/exit/do behaviors, internal transitions, and orthogonal
(concurrent) regions. A model that uses any of them must be authored in
PlantUML, or its semantics vanish with a clean render. This check scans the
model text for those features and reports the decision.

Usage:
    select-renderer.py <model.txt|model.mmd|model.puml>
        Print  RENDERER: mermaid  or  RENDERER: plantuml  plus the trigger.
        Exit 0 always (decision is informational), exit 2 on a read error.

    select-renderer.py --stamp <src> [out]
        When escalation is required, write <src> with an escalation-reason
        header comment prepended (to <out> if given, else in place) so the
        recorded reason ships with the generated source. Exit 0.

The four feature detectors look for the syntax forms, not the rendered result,
so they work on a Mermaid draft before it is ever rendered.
"""
import re
import sys
from pathlib import Path

HEADER_PREFIX = "escalation-reason:"

# A transition line has the --> arrow. The feature detectors below distinguish a
# state-internal behavior line (no arrow) from a transition label (after the
# arrow), because both can carry a trigger/action of the form name/action.
ARROW = re.compile(r"-+>")
HISTORY = re.compile(r"\[H\*?\]")
REGION = re.compile(r"^\s*--\s*$")
# Mermaid `State : entry/x` or PlantUML `State : entry / x`.
BEHAVIOR = re.compile(r":\s*(?:entry|exit|do)\s*/", re.IGNORECASE)
# A state-internal transition: a colon-delimited trigger/action on a state line
# that is not a transition and not an entry/exit/do behavior.
INTERNAL = re.compile(r":\s*[A-Za-z0-9_]+\s*(?:\[[^\]]*\])?\s*/\s*\S")


def detect(text):
    """Return the list of feature triggers present in the model text, scanning
    line by line so a transition action is not mistaken for an internal one."""
    found = {}
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.lstrip()
        if stripped.startswith("%%") or stripped.startswith("'"):
            continue  # comment line, never a feature
        if HISTORY.search(line):
            found.setdefault("shallow or deep history pseudostate", True)
        if REGION.match(line):
            found.setdefault("orthogonal (concurrent) region", True)
        if ARROW.search(line):
            continue  # a transition line: its label is not a state-internal behavior
        if BEHAVIOR.search(line):
            found.setdefault("entry, exit, or do behavior", True)
        elif INTERNAL.search(line):
            found.setdefault("internal transition", True)
    order = [
        "shallow or deep history pseudostate",
        "entry, exit, or do behavior",
        "internal transition",
        "orthogonal (concurrent) region",
    ]
    return [label for label in order if label in found]


def comment_token(src_name, text):
    """Mermaid comments start with %%, PlantUML with a single quote."""
    if src_name.endswith(".puml") or text.lstrip().startswith("@startuml"):
        return "'"
    return "%%"


def main(argv):
    stamp = False
    args = argv[1:]
    if args and args[0] == "--stamp":
        stamp = True
        args = args[1:]
    if not args:
        sys.stderr.write(__doc__)
        return 2
    src = Path(args[0])
    try:
        text = src.read_text()
    except OSError as exc:
        print(f"cannot read {src}: {exc}", file=sys.stderr)
        return 2

    triggers = detect(text)
    if not triggers:
        print("RENDERER: mermaid (no PlantUML-only feature detected)")
        return 0

    reason = (
        "PlantUML required, Mermaid stateDiagram-v2 would silently drop: "
        + "; ".join(triggers)
    )
    print("RENDERER: plantuml")
    print(f"  {reason}")

    if stamp:
        tok = comment_token(src.name, text)
        header = f"{tok} {HEADER_PREFIX} {reason}\n"
        out = Path(args[1]) if len(args) > 1 else src
        if HEADER_PREFIX in text:
            # already stamped, replace the line
            new = re.sub(
                rf"^{re.escape(tok)} {re.escape(HEADER_PREFIX)}.*$",
                header.rstrip("\n"),
                text,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            new = header + text
        out.write_text(new)
        print(f"  recorded reason in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
