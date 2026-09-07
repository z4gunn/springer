#!/usr/bin/env python3
"""Claim or release the single-writer lock on a run.

Two Claude sessions driving one run in one working tree is the FI-024 defect
at the session level: one session switched branches under the other and
committed its in-progress writes. The harness claims the run on entry and
releases it on exit. derive-ready-queue.py reports the lock and sets blocked
when another live process holds it.

Usage:
    python3 claim-run.py <run-dir> claim <session-id>
    python3 claim-run.py <run-dir> release <session-id>
    python3 claim-run.py <run-dir> status

The lock is <run-dir>/.lock, JSON: session_id, claimed_at. Liveness is a
heartbeat, not a pid, because Claude Code runs every shell command in a fresh
process: the harness re-claims at every tick, and a lock not refreshed within
STALE_MINUTES is stale and is taken over silently. Exit 0 on success, 1 when
the run is held by another live session, 2 on usage error.
"""

import json
import sys
import time
from pathlib import Path

STALE_MINUTES = 30


def read_lock(run_dir):
    lp = Path(run_dir) / ".lock"
    if not lp.exists():
        return None
    try:
        return json.loads(lp.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def lock_alive(lock, now=None):
    """A lock is alive while its heartbeat is within STALE_MINUTES."""
    try:
        claimed = time.mktime(time.strptime(lock.get("claimed_at", ""), "%Y-%m-%dT%H:%M:%SZ")) - time.timezone
    except (ValueError, TypeError):
        return False
    now = now if now is not None else time.time()
    return (now - claimed) < STALE_MINUTES * 60


def lock_state(run_dir):
    """Return (lock, alive)."""
    lock = read_lock(run_dir)
    if not lock:
        return None, False
    return lock, lock_alive(lock)


def main(argv):
    if len(argv) < 3 or argv[2] not in ("claim", "release", "status"):
        sys.stderr.write(__doc__)
        return 2
    run_dir = Path(argv[1])
    lp = run_dir / ".lock"
    cmd = argv[2]
    lock, alive = lock_state(run_dir)
    if cmd == "status":
        print(json.dumps({"lock": lock, "holder_alive": alive}, indent=2))
        return 0
    if len(argv) != 4:
        sys.stderr.write(__doc__)
        return 2
    session_id = argv[3]
    if cmd == "claim":
        if lock and alive and lock.get("session_id") != session_id:
            print(f"held by session {lock.get('session_id')}, heartbeat {lock.get('claimed_at')}")
            return 1
        lp.write_text(json.dumps({
            "session_id": session_id,
            "claimed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }, indent=2) + "\n")
        print(f"claimed {run_dir} for session {session_id}")
        return 0
    if lock and lock.get("session_id") != session_id and alive:
        print(f"not released: held by another live session {lock.get('session_id')}")
        return 1
    if lp.exists():
        lp.unlink()
    print(f"released {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
