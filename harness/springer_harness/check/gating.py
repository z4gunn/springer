"""The unit's gating commands, run off the tick.

A product check can take minutes (the reference run's measured Lighthouse five times),
and the tick holds the daemon lock, so a gating run inside it would stall every run and
every operation that takes the lock. The tick starts a run on a thread and leaves the
unit in checking. Later ticks ask again without waiting, and apply the verdict once it is
on disk.

A run writes into a private folder and moves it into place as the session's check folder
only when its verdict is written, so a half-written receipt is never evidence. After a
daemon restart no thread is running and no verdict is on disk, so the run starts again.
"""

import os
import shutil
import threading
import time
import uuid
from pathlib import Path

from ..common import read_json, write_json
from .mechanical import run_gating

VERDICT = "verdict.json"


class GatingRuns:
    def __init__(self):
        self._threads = {}
        self._lock = threading.Lock()

    def poll(self, key, commands, session_dir, cwd):
        """None while the run is going (starting it when nothing is), else the verdict:
        an empty string when every command passed, or the defect detail."""
        found = read_json(Path(session_dir) / "check" / VERDICT)
        if isinstance(found, dict) and "problem" in found:
            return found["problem"] or ""
        with self._lock:
            thread = self._threads.get(key)
            if thread and thread.is_alive():
                return None
            thread = threading.Thread(target=self._run, args=(list(commands), Path(session_dir), Path(cwd)),
                                      name=f"gating-{key}", daemon=True)
            self._threads[key] = thread
            thread.start()
        return None

    def running(self, key):
        thread = self._threads.get(key)
        return bool(thread and thread.is_alive())

    def _run(self, commands, session_dir, cwd):
        partial = session_dir / f".check-{uuid.uuid4().hex}"
        try:
            problem = run_gating(commands, partial, cwd)
        except Exception as exc:  # noqa: BLE001, a crashed run is a verdict, never a hang
            problem = f"the gating run failed: {exc}"
        write_json(partial / VERDICT, {"problem": problem, "at": time.time()})
        final = session_dir / "check"
        shutil.rmtree(final, ignore_errors=True)
        os.replace(partial, final)
