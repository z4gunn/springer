#!/usr/bin/env python3
"""Pin a set of run-retrospective artifacts by hash for one run.

Cross-run learnings are advisory and must be frozen at run start so a re-run
with the same pinned set is reproducible (ADR-004). This script reads one or
more run-retrospective artifacts and emits the learnings_pinned entries that go
into run-state at run start, each a retrospective_ref plus a content hash. It
makes no judgment about which learnings apply. It only freezes the set.

Usage:
    python3 pin-learnings.py <retrospective.json> [<retrospective.json> ...]

Prints a JSON array of {retrospective_ref, hash} to stdout. Exit 0 on success,
1 on a usage or read error.
"""

import hashlib
import json
import sys
from pathlib import Path


def pin(paths):
    entries = []
    for p in paths:
        raw = Path(p).read_bytes()
        artifact = json.loads(raw)
        if artifact.get("artifact_type") != "run-retrospective":
            raise ValueError(f"{p} is not a run-retrospective artifact")
        entries.append({
            "retrospective_ref": artifact.get("artifact_id"),
            "hash": "sha256:" + hashlib.sha256(raw).hexdigest(),
        })
    # Stable order so the pinned set is deterministic regardless of argv order.
    entries.sort(key=lambda e: e["retrospective_ref"] or "")
    return entries


def main(argv):
    if len(argv) < 2:
        sys.stderr.write(__doc__)
        return 1
    try:
        print(json.dumps(pin(argv[1:]), indent=2))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        sys.stderr.write(f"pin-learnings failed: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
