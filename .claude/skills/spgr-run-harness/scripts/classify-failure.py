#!/usr/bin/env python3
"""Name why a unit failed, so a retry is spent only where a retry can help.

Every failed unit used to be one kind of failure: route a fix, spend one of
the two bounded retries. But a rate limit, a context overflow, a broken tool
install, an agent that stopped to ask, and a real defect want five different
responses, and only the last is a fix the implementer can make. Spending a
retry on the first three burns budget on a deterministic outcome. This script
reads what the unit left behind and names the class and its policy. Stdlib
only.

Classes, in the order they are tested:
  transient    the platform failed the dispatch (rate or usage limit, overload,
               a dropped connection). Redispatch unchanged after a pause. No
               retry is spent. Three in a row on one unit pause the run.
  context      the unit ran out of context. Split the unit or narrow the brief
               and redispatch. No retry is spent.
  blocked      the unit returned BLOCKED or NEEDS_CONTEXT. Route it as an
               escalation, never a retry.
  environment  a tool, interpreter, credential, or path the unit needed is
               missing or broken. Run preflight.py and fix the environment or
               ask the human. No retry is spent.
  defect       everything else, including a failed or zero-run receipt and a
               REQUEST_CHANGES review. The bounded fix loop, which spends a
               retry.

Usage:
    classify-failure.py <unit-dir> [--run-dir <run-dir>] [--unit-id <id>]

Reads <unit-dir>/return.txt (the dispatch's return text, which the harness
saves), <unit-dir>/result.md, and <unit-dir>/receipts/*.json, whichever
exist. Prints one JSON object with the class, the policy, whether a retry is
spent, and the line that decided it. With --run-dir it also appends a
`unit_failure` event to <run-dir>/events.jsonl for the dashboard. Exit 0
after classifying, 2 on usage or a missing unit directory.
"""

import datetime
import json
import re
import sys
from pathlib import Path

CLASSES = [
    ("transient", [
        r"rate[ -]?limit", r"\b429\b", r"\b529\b", r"overloaded", r"usage limit", r"session limit",
        r"\b503\b", r"ECONNRESET", r"ETIMEDOUT", r"socket hang up", r"connection (reset|refused|error)",
        r"API Error", r"try again later",
    ]),
    ("context", [
        r"prompt is too long", r"context (window|length)", r"maximum context", r"exceeds? .{0,30}tokens",
        r"too many tokens", r"compact(ion)? failed",
    ]),
    ("blocked", [
        r"^\s*(?i:status:\s*)?(BLOCKED|NEEDS_CONTEXT)\b",
    ]),
    ("environment", [
        r"command not found", r"No module named", r"ModuleNotFoundError", r"not logged in",
        r"gh auth login", r"authentication (failed|required)", r"EACCES", r"Permission denied",
        r"executable file not found", r"cannot find (the )?(browser|chrom)", r"npx: .*not found",
        r"ENOENT: no such file or directory, (spawn|open) .*/(bin|node_modules)/",
    ]),
]
POLICY = {
    "transient": ("redispatch the unit unchanged after a pause, three in a row pause the run", False),
    "context": ("split the unit or narrow the brief, then redispatch", False),
    "blocked": ("route the return as an escalation", False),
    "environment": ("run preflight.py, then fix the environment or ask the human", False),
    "defect": ("bounded fix loop: a fresh agent with the finding or failing receipt", True),
}


def read(path):
    try:
        return Path(path).read_text(errors="replace")
    except OSError:
        return ""


def receipt_lines(unit_dir):
    out = []
    for path in sorted((Path(unit_dir) / "receipts").glob("*.json")):
        try:
            r = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if r.get("result") != "pass":
            out.append(f"receipt {r.get('name')}: {r.get('result')}\n{r.get('output_tail', '')}")
    return out


def classify(unit_dir):
    """Return (class, evidence line). The return text is read first because
    a platform failure there means the unit never finished its own report."""
    unit_dir = Path(unit_dir)
    sources = [read(unit_dir / "return.txt"), read(unit_dir / "result.md"), *receipt_lines(unit_dir)]
    for name, patterns in CLASSES:
        for text in sources:
            for line in text.splitlines():
                if any(re.search(p, line, re.I if name != "blocked" else 0) for p in patterns):
                    return name, line.strip()[:240]
    failed = [r.splitlines()[0] for r in receipt_lines(unit_dir)]
    return "defect", failed[0] if failed else "no platform, context, block, or environment signal"


def main(argv):
    args = argv[1:]
    if not args or args[0].startswith("-"):
        sys.stderr.write(next(b for b in __doc__.split("\n\n") if b.startswith("Usage:")) + "\n")
        return 2
    unit_dir = Path(args[0])
    run_dir, unit_id = None, unit_dir.name
    i = 1
    while i < len(args):
        if args[i] == "--run-dir" and i + 1 < len(args):
            run_dir, i = Path(args[i + 1]), i + 2
        elif args[i] == "--unit-id" and i + 1 < len(args):
            unit_id, i = args[i + 1], i + 2
        else:
            sys.stderr.write(f"unknown argument {args[i]}\n")
            return 2
    if not unit_dir.is_dir():
        sys.stderr.write(f"no such unit directory: {unit_dir}\n")
        return 2
    cls, evidence = classify(unit_dir)
    policy, spends = POLICY[cls]
    result = {"unit_id": unit_id, "class": cls, "policy": policy, "spends_retry": spends, "evidence": evidence}
    print(json.dumps(result))
    if run_dir is not None:
        event = dict(result, ts=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                     event="unit_failure", run_id=run_dir.name)
        with open(run_dir / "events.jsonl", "a") as fh:
            fh.write(json.dumps(event) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
