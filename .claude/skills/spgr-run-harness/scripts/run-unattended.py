#!/usr/bin/env python3
"""Drive a run unattended across fresh sessions, usage limits, and auto-merged PRs.

A run lost its wall clock to three waits, none of them work: a main session
that filled its context and stopped until someone opened a new one, a usage
limit that stopped every session until its reset and until someone noticed,
and a pr-merge gate nobody was there to answer. pr-risk.py removes the third
for every PR that is not high risk. This script removes the first two. It
runs spgr-run-harness in a loop of headless `claude -p` sessions from outside
any session, so each one starts with an empty context and rehydrates from the
run store, which is what start-equals-resume was built for. Stdlib only.

Each pass:
1. Read the readiness snapshot. Stop and notify when the run is complete, or
   when an open gate holds all remaining work, because only the human moves
   it. Wait while another live session holds the run lock.
2. Run one session with the unattended prompt: never ask, write a gate as a
   checkpoint, end at the clean Act after the context sensor's first warning.
   AskUserQuestion is disallowed and tools are allowed only by the project's
   own settings, with file edits accepted.
3. After it exits, mark any dispatch it left un-joined abandoned, because the
   session that owned it is gone, so the next session can plan.
4. A usage limit sleeps until the reset the message names, or 30 minutes when
   it names none, then continues. Any other failure retries with backoff.
   Three failures in a row, or two sessions in a row that add no cycle, stop
   the loop and notify, so a stuck run never burns a night.

Notifications go to the Slack incoming webhook in SPRINGER_SLACK_WEBHOOK_URL,
read from the environment or the project's .env, with a macOS notification
as the fallback, and every stop writes runs/<run-id>/unattended-status.md.

Usage:
    run-unattended.py <run-id> [--project <dir>] [--model <model>]
                      [--max-sessions 40] [--max-hours 16] [--claude <bin>]

Exit 0 when the run completed or reached a human gate, 1 when the loop
stopped on failures, no progress, or a cap, 2 on usage.
"""

import datetime
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
WEBHOOK_ENV = "SPRINGER_SLACK_WEBHOOK_URL"
SESSION_TIMEOUT = 6 * 3600
DEFAULT_LIMIT_WAIT = 30 * 60
LIMIT = re.compile(r"usage limit|limit reached|limit will reset|rate[_ ]limit|hit your limit|resets? (at )?\d", re.I)
EPOCH = re.compile(r"\|(\d{10})\b")
CLOCK = re.compile(r"resets?(?: at)?\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.I)

PROMPT = (
    "Resume spgr-run-harness for run-id {run_id} in run mode. This session is unattended: no human "
    "will read or answer anything in it. Never ask a question. A gate is written as a hil-checkpoint "
    "and notified per the harness, and the work it does not hold keeps running. Merge every PR that "
    "pr-risk.py scores low or medium once its merge bar holds. When the main-session context sensor "
    "gives its first warning, finish the current Act, release the run lock, and stop. A new session "
    "resumes the run."
)

sleep = time.sleep


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def load_drq():
    spec = importlib.util.spec_from_file_location("derive_ready_queue", HERE / "derive-ready-queue.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_env_value(project, key):
    if os.environ.get(key):
        return os.environ[key]
    env = Path(project) / ".env"
    try:
        for line in env.read_text().splitlines():
            if line.strip().startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        pass
    return None


def notify(project, run_dir, title, body):
    """Slack first, macOS second, and always the status file."""
    text = f"*Springer {title}*: {Path(run_dir).name}\n{body}"
    (Path(run_dir) / "unattended-status.md").write_text(
        f"# {title}\n\n{now().isoformat(timespec='seconds')}\n\n{body}\n")
    url = read_env_value(project, WEBHOOK_ENV)
    if url:
        try:
            req = urllib.request.Request(url, data=json.dumps({"text": text}).encode(),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=15).read()
            return "slack"
        except OSError as exc:
            sys.stderr.write(f"run-unattended: Slack notification failed: {exc}\n")
    if shutil.which("osascript"):
        safe = body.splitlines()[0].replace('"', "'")[:180] if body else ""
        subprocess.run(["osascript", "-e", f'display notification "{safe}" with title "Springer {title}"'],
                       capture_output=True)
        return "macos"
    return "file"


def log_event(run_dir, **fields):
    with open(Path(run_dir) / "events.jsonl", "a") as fh:
        fh.write(json.dumps(dict(fields, ts=now().isoformat(timespec="seconds"),
                                 event="unattended_session")) + "\n")


def cycle_count(run_dir):
    return len(list((Path(run_dir) / "artifacts").glob("CYCLE-*.json")))


def human_gates(snapshot):
    return [g for g in snapshot.get("open_gate_detail", []) if "all" in (g.get("holds") or ["all"])]


def limit_wait(text, current=None):
    """Seconds to sleep for a usage-limit message, or None when the text is
    not one. A Unix epoch after a pipe wins, then a clock time, then the
    default wait."""
    if not text or not LIMIT.search(text):
        return None
    current = current or now()
    m = EPOCH.search(text)
    if m:
        return max(60, int(m.group(1)) - int(current.timestamp()) + 120)
    m = CLOCK.search(text)
    if m:
        hour, minute, half = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
        if half == "pm" and hour < 12:
            hour += 12
        if half == "am" and hour == 12:
            hour = 0
        local = current.astimezone()
        target = local.replace(hour=hour % 24, minute=minute, second=0, microsecond=0)
        if target <= local:
            target += datetime.timedelta(days=1)
        return int((target - local).total_seconds()) + 120
    return DEFAULT_LIMIT_WAIT


def abandon_unjoined(run_dir, drq):
    ids = [u["tool_use_id"] for u in drq.unjoined_dispatches(run_dir) if u.get("tool_use_id")]
    with open(Path(run_dir) / "events.jsonl", "a") as fh:
        for tid in ids:
            fh.write(json.dumps({"ts": now().isoformat(timespec="seconds"), "event": "agent_abandoned",
                                 "tool_use_id": tid, "reason": "the unattended session that owned it exited"})
                     + "\n")
    return ids


def run_session(claude, project, run_id, model, log_path):
    cmd = [claude, "-p", PROMPT.format(run_id=run_id), "--output-format", "stream-json", "--verbose",
           "--permission-mode", "acceptEdits", "--disallowedTools", "AskUserQuestion"]
    if model:
        cmd += ["--model", model]
    env = dict(os.environ, SPRINGER_UNATTENDED="1")
    try:
        proc = subprocess.run(cmd, cwd=project, capture_output=True, text=True, timeout=SESSION_TIMEOUT, env=env)
        code, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        code, out, err = 124, exc.stdout or "", f"session timed out after {SESSION_TIMEOUT}s"
        out = out.decode(errors="replace") if isinstance(out, bytes) else out
    with open(log_path, "a") as fh:
        fh.write(out)
        if err:
            fh.write(json.dumps({"type": "driver_stderr", "text": err[-4000:]}) + "\n")
    final = []
    for line in out.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "result":
            final.append(str(event.get("result") or ""))
            if event.get("is_error"):
                final.append(str(event.get("subtype") or "error"))
    return code, "\n".join(final), err


def drive(run_id, project, model, max_sessions, max_hours, claude):
    project = Path(project).resolve()
    run_dir = project / "runs" / run_id
    if not run_dir.is_dir():
        sys.stderr.write(f"run-unattended: no run store at {run_dir}. Start the run interactively first.\n")
        return 2
    drq = load_drq()
    log_path = run_dir / "unattended.jsonl"
    started, sessions, failures, idle, lock_waits = time.monotonic(), 0, 0, 0, 0
    first_cycles = cycle_count(run_dir)
    while True:
        snapshot = drq.derive(run_dir)
        done = cycle_count(run_dir) - first_cycles
        if snapshot.get("complete"):
            notify(project, run_dir, "run complete", f"{done} cycles in {sessions} unattended sessions.")
            return 0
        gates = human_gates(snapshot)
        if gates:
            lines = [f"- {g['checkpoint_id']} {g.get('checkpoint_type')}" for g in gates]
            notify(project, run_dir, "needs you",
                   f"A high-risk gate holds all remaining work after {done} cycles:\n" + "\n".join(lines)
                   + f"\nAnswer it in runs/{run_id}/checkpoints/, then rerun run-unattended.py {run_id}.")
            return 0
        lock = snapshot.get("lock") or {}
        if lock.get("alive"):
            lock_waits += 1
            if lock_waits > 6:
                notify(project, run_dir, "stopped", f"Another session has held the run lock for 30 minutes "
                       f"(session {lock.get('session_id')}).")
                return 1
            sleep(300)
            continue
        lock_waits = 0
        if sessions >= max_sessions or (time.monotonic() - started) > max_hours * 3600:
            notify(project, run_dir, "stopped at its cap", f"{sessions} sessions, {done} cycles. Rerun to continue.")
            return 1
        before = cycle_count(run_dir)
        sessions += 1
        code, final, err = run_session(claude, project, run_id, model, log_path)
        abandoned = abandon_unjoined(run_dir, drq)
        added = cycle_count(run_dir) - before
        wait = limit_wait(final + "\n" + err)
        outcome = "usage-limit" if wait else ("ok" if code == 0 else "error")
        log_event(run_dir, session=sessions, exit_code=code, cycles_added=added, outcome=outcome,
                  abandoned=abandoned, wait_s=wait)
        if wait:
            failures = 0
            sleep(wait)
            continue
        if code != 0:
            failures += 1
            if failures >= 3:
                notify(project, run_dir, "stopped on errors",
                       f"Three sessions in a row failed. Last: exit {code}. {(err or final)[-600:]}")
                return 1
            sleep(60 * failures)
            continue
        failures = 0
        idle = idle + 1 if added == 0 else 0
        if idle >= 2:
            notify(project, run_dir, "stopped, no progress",
                   f"Two sessions in a row added no cycle. Last message: {final[-600:]}")
            return 1


def main(argv):
    args = argv[1:]
    if not args or args[0].startswith("-"):
        sys.stderr.write(next(b for b in __doc__.split("\n\n") if b.startswith("Usage:")) + "\n")
        return 2
    run_id, opts, i = args[0], {"project": ".", "model": None, "max_sessions": 40, "max_hours": 16.0,
                                "claude": "claude"}, 1
    while i < len(args):
        key = args[i][2:].replace("-", "_") if args[i].startswith("--") else None
        if key not in opts or i + 1 >= len(args):
            sys.stderr.write(f"run-unattended: unknown or incomplete option {args[i]}\n")
            return 2
        value = args[i + 1]
        opts[key] = int(value) if key == "max_sessions" else float(value) if key == "max_hours" else value
        i += 2
    if shutil.which(opts["claude"]) is None and not Path(opts["claude"]).is_file():
        sys.stderr.write(f"run-unattended: {opts['claude']} is not on PATH\n")
        return 2
    return drive(run_id, opts["project"], opts["model"], opts["max_sessions"], opts["max_hours"], opts["claude"])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
