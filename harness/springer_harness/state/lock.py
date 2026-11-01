"""The run lock, in the file and format claim-run.py uses, so an in-session shim or
a stray Claude Code session sees a daemon-held run and refuses to write."""

import json
import os
import socket
import time
from pathlib import Path

from ..common import parse_iso, write_json

STALE_SECONDS = 30 * 60


def daemon_owner():
    return f"daemon:{socket.gethostname()}:{os.getpid()}"


class RunLock:
    def __init__(self, run_dir, owner, now):
        self.path = Path(run_dir) / ".lock"
        self.owner = owner
        self.now = now

    def read(self):
        try:
            return json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def _alive(self, lock):
        try:
            return self.now() - parse_iso(lock.get("claimed_at", "")) < STALE_SECONDS
        except (ValueError, TypeError):
            return False

    def externally_held(self):
        """The holder, when a live lock is held by anything that is not a daemon.
        A previous daemon's lock is taken over, because its children died with it."""
        lock = self.read()
        if lock and self._alive(lock) and lock.get("session_id") != self.owner \
                and not str(lock.get("session_id", "")).startswith("daemon:"):
            return lock["session_id"]
        return None

    def refresh(self):
        """Claim or refresh. Returns False when another live session holds the run."""
        if self.externally_held():
            return False
        write_json(self.path, {"session_id": self.owner,
                               "claimed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.now()))})
        return True
