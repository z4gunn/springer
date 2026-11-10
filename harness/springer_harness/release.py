"""The production release: the project's own deploy command, run by the daemon only
after a person said go, in Slack or the TUI.

A deploy script that guards itself with a typed answer (read from a terminal) gets a
pseudo-terminal, and the harness types the configured word when the script stops at a
prompt: a partial line and then silence. The script's own guard stays in place for
anyone at a shell. The person's go is the gate the harness opened, or the Confirm tap
on /springer release.

The command runs in the project checkout, which must be on the default branch at its
head with no tracked change, so what ships is what merged."""

import os
import pty
import re
import select
import signal
import subprocess
import threading
import time
from pathlib import Path

from .common import read_json, write_json

RELEASE_TIMEOUT = 3600
PROMPT_SILENCE = 2.0
TAIL_CHARS = 1500
LOG_CAP = 2_000_000
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\r")


def _git(cwd, *args):
    done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=60)
    return done.returncode, done.stdout.strip()


def ready_to_ship(cwd, default_branch):
    """(sha, None) when the checkout can ship, else (None, why not). A change under runs/
    does not count: the harness writes the run store (the backlog closes, the gate answers)
    while the run is open and commits it only when the run completes, after the release."""
    rc, branch = _git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    if rc or branch != default_branch:
        return None, f"the project checkout is on {branch or 'no branch'}, not {default_branch}"
    rc, dirty = _git(cwd, "status", "--porcelain", "--untracked-files=no", "--", ".", ":(exclude)runs")
    if rc or dirty:
        return None, "the project checkout has uncommitted changes to tracked files"
    rc, sha = _git(cwd, "rev-parse", "HEAD")
    return (sha, None) if not rc else (None, "the project checkout has no commit")


def run_release(command, confirm, cwd, log_path, timeout=RELEASE_TIMEOUT):
    """Run command in a pseudo-terminal. Returns {exit_code, typed, tail}."""
    master, slave = pty.openpty()
    proc = subprocess.Popen(command, shell=True, cwd=str(cwd), stdin=slave, stdout=slave, stderr=slave,
                            start_new_session=True, close_fds=True)
    os.close(slave)
    chunks, size, typed = [], 0, False
    last_output, deadline = time.monotonic(), time.monotonic() + timeout
    try:
        while True:
            ready, _, _ = select.select([master], [], [], 0.2)
            if ready:
                try:
                    data = os.read(master, 65536)
                except OSError:
                    data = b""
                if not data and proc.poll() is not None:
                    break
                if data:
                    if size < LOG_CAP:
                        chunks.append(data)
                        size += len(data)
                    last_output = time.monotonic()
                    continue
            if proc.poll() is not None:
                break
            if time.monotonic() > deadline:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=30)
                break
            # A prompt is a partial line and then silence. Type the word once.
            text = b"".join(chunks[-4:])
            if confirm and not typed and text and not text.endswith(b"\n") \
                    and time.monotonic() - last_output >= PROMPT_SILENCE:
                os.write(master, (confirm + "\n").encode())
                typed = True
    finally:
        os.close(master)
    exit_code = proc.wait()
    output = ANSI.sub("", b"".join(chunks).decode(errors="replace"))
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    Path(log_path).write_text(output)
    return {"exit_code": exit_code, "typed": typed, "tail": output[-TAIL_CHARS:]}


class Releases:
    """One release at a time per project, on a thread, because a deploy takes minutes
    and the tick holds the daemon lock. The result lands in out_dir/result.json."""

    def __init__(self):
        self._threads = {}
        self._lock = threading.Lock()

    def running(self, slug):
        thread = self._threads.get(slug)
        return bool(thread and thread.is_alive())

    def start(self, slug, command, confirm, cwd, out_dir, sha, on_done=None):
        with self._lock:
            if self.running(slug):
                return False
            thread = threading.Thread(target=self._run, args=(command, confirm, cwd, Path(out_dir), sha, on_done),
                                      name=f"release-{slug}", daemon=True)
            self._threads[slug] = thread
            thread.start()
            return True

    @staticmethod
    def result(out_dir):
        return read_json(Path(out_dir) / "result.json")

    def _run(self, command, confirm, cwd, out_dir, sha, on_done):
        started = time.time()
        try:
            outcome = run_release(command, confirm, cwd, out_dir / "output.log")
        except Exception as exc:  # noqa: BLE001, a crashed release is a result, never a hang
            outcome = {"exit_code": None, "typed": False, "tail": f"the release could not run: {exc}"}
        result = {**outcome, "sha": sha, "command": command, "started": started, "finished": time.time()}
        write_json(out_dir / "result.json", result)
        if on_done:
            on_done(result)
