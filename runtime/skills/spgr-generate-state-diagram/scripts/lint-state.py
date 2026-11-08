#!/usr/bin/env python3
"""Lint a state-diagram source for the four structural defects a renderer will
not catch:

  1. unreachable  - a state no transition can reach from the initial pseudostate.
  2. dead-end     - a non-final, non-pseudostate state with no outgoing transition.
  3. unhandled    - a trigger event that fires from some states but is named in a
                    comment directive `%% events: a, b, c` (or `' events: ...`)
                    yet handled by no state, so the lifecycle ignores it everywhere.
  4. choice-guard - a <<choice>> / <<fork>> branch point whose outgoing branches
                    are not guard-exhaustive: they lack an [else] or a bare
                    unguarded default, so some condition falls through unmodeled.

Parses both Mermaid stateDiagram-v2 and PlantUML state notation. The transition
grammar both share is  SRC --> DST : trigger[guard]/action  (label optional).

Usage: lint-state.py <src.mmd|src.puml>
Exit 0 = clean. Exit 1 = one or more findings. Exit 2 = usage/parse error.
"""
import re
import sys
from pathlib import Path

INIT = "[*]"

# SRC --> DST  with an optional ": label" (Mermaid uses ':', PlantUML uses ':' too).
TRANSITION = re.compile(
    r"^\s*([A-Za-z0-9_\[\]*]+)\s*-+>\s*([A-Za-z0-9_\[\]*]+)\s*(?::\s*(.*))?$"
)
# state Foo <<choice>>  or  state Foo <<fork>>  (pseudostate declarations).
PSEUDO = re.compile(r"^\s*state\s+([A-Za-z0-9_]+)\s*<<(choice|fork|join|history)>>")
# A trigger label: trigger[guard]/action. Trigger is the text before '[' or '/'.
LABEL = re.compile(r"^\s*([A-Za-z0-9_]+)?\s*(?:\[(.*?)\])?\s*(?:/(.*))?\s*$")
# Declared event vocabulary directive in a comment.
EVENTS_DIRECTIVE = re.compile(r"(?:%%|')\s*events\s*:\s*(.+)$", re.IGNORECASE)


def strip_history(name):
    """Mermaid uses [H]/[H*]; PlantUML uses State[H]. Normalize a transition
    target like Active[H] to its composite-state name for graph reachability."""
    m = re.match(r"^([A-Za-z0-9_]+)\[H\*?\]$", name)
    return m.group(1) if m else name


def parse(text):
    transitions = []  # (src, dst, trigger, guard)
    pseudostates = {}  # name -> kind
    declared_events = set()
    states = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        ev = EVENTS_DIRECTIVE.search(raw)
        if ev:
            for tok in ev.group(1).split(","):
                tok = tok.strip()
                if tok:
                    declared_events.add(tok)
            continue
        # comment-only lines past here are ignored
        if line.startswith("%%") or line.startswith("'"):
            continue
        ps = PSEUDO.match(line)
        if ps:
            pseudostates[ps.group(1)] = ps.group(2)
            states.add(ps.group(1))
            continue
        tr = TRANSITION.match(line)
        if not tr:
            continue
        src = strip_history(tr.group(1))
        dst = strip_history(tr.group(2))
        trigger, guard = None, None
        if tr.group(3):
            lm = LABEL.match(tr.group(3))
            if lm:
                trigger = (lm.group(1) or "").strip() or None
                guard = (lm.group(2) or "").strip() or None
        transitions.append((src, dst, trigger, guard))
        for node in (src, dst):
            if node != INIT:
                states.add(node)
    return transitions, pseudostates, declared_events, states


def reachable_from_init(transitions, states):
    adj = {}
    for src, dst, _, _ in transitions:
        adj.setdefault(src, set()).add(dst)
    seen = set()
    stack = list(adj.get(INIT, set()))
    while stack:
        n = stack.pop()
        if n in seen or n == INIT:
            continue
        seen.add(n)
        stack.extend(adj.get(n, set()))
    return seen


def lint(text):
    transitions, pseudostates, declared_events, states = parse(text)
    findings = []

    if not any(src == INIT for src, _, _, _ in transitions):
        findings.append("no initial pseudostate: every region needs exactly one [*] --> entry transition")

    # 1. unreachable states
    reachable = reachable_from_init(transitions, states)
    for s in sorted(states):
        if s not in reachable and s not in pseudostates:
            findings.append(f"unreachable state: {s} cannot be reached from the initial pseudostate")

    # 2. dead-end states (non-final real states with no outgoing transition)
    has_out = {src for src, _, _, _ in transitions}
    for s in sorted(states):
        if s in pseudostates:
            continue
        if s not in has_out:
            findings.append(f"dead-end state: {s} has no outgoing transition and is not a final state")

    # 3. unhandled events (declared in the vocabulary but no state handles them)
    if declared_events:
        handled = {t for _, _, t, _ in transitions if t}
        for e in sorted(declared_events - handled):
            findings.append(f"unhandled event: '{e}' is declared but no state has a transition triggered by it")

    # 4. non-exhaustive guards on <<choice>>/<<fork>> branch points
    for name, kind in pseudostates.items():
        if kind not in ("choice", "fork"):
            continue
        branches = [(g, dst) for src, dst, _, g in transitions if src == name]
        if not branches:
            continue
        has_default = any(
            g is None or g.strip().lower() == "else" for g, _ in branches
        )
        if not has_default:
            guards = ", ".join(g for g, _ in branches if g) or "(none)"
            findings.append(
                f"non-exhaustive choice: <<{kind}>> '{name}' branches [{guards}] "
                f"have no [else] or unguarded default, so some condition falls through"
            )

    return findings


def main(argv):
    if len(argv) != 2:
        sys.stderr.write(__doc__)
        return 2
    path = Path(argv[1])
    try:
        text = path.read_text()
    except OSError as exc:
        print(f"cannot read {path}: {exc}", file=sys.stderr)
        return 2
    findings = lint(text)
    if findings:
        print(f"LINT FAILED: {path}")
        for f in findings:
            print(f"  - {f}")
        return 1
    print(f"LINT OK: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
