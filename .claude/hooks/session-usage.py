#!/usr/bin/env python3
"""Main-session usage sensor. Registered for PostToolUse on every tool and for
Stop. Reads the session transcript incrementally from the byte offset it
reached last time, sums the usage record on each new assistant message, and
writes runs/_dashboard/sessions/<session-id>.json so the dashboard can show
the main session's context size, cumulative tokens, and cost next to the
subagent figures the event hook records.

The reference run's main session spent more output tokens than all of its
subagents combined and nothing could see it while it happened. This hook is
the sensor. It changes nothing by itself: when the context passes a threshold
it returns additionalContext naming the main-session budget rule, once per
tier per session, so the harness ends the loop at a clean Act instead of
dying mid-cycle. Never blocks a tool call: always exits 0.

Context size is the last assistant message's input plus cache-read plus
cache-creation tokens, which is what the next request will carry. The window
comes from the model name: 200k for haiku, 1M otherwise."""

import datetime
import json
import os
import sys

TIERS = [
    (0.6, "advisory",
     "Main-session context is past 60 percent of the window. Per the "
     "main-session budget in .claude/references/pdca-harness.md, plan to end "
     "the loop at the next clean Act: write the cycle record, refresh the run "
     "brief, release the run lock, and resume in a fresh session. Do not open "
     "artifacts the story brief already summarizes."),
    (0.8, "critical",
     "Main-session context is past 80 percent of the window. Finish the "
     "current Act now, write the cycle record, release the run lock with "
     "claim-run.py, and stop. Resume spgr-run-harness in a fresh session. "
     "Dispatch nothing new from this session."),
]


def window_for(model):
    return 200_000 if model and "haiku" in model else 1_000_000


def state_path(project_dir, session_id):
    return os.path.join(project_dir, "runs", "_dashboard", "sessions", f"{session_id}.json")


def load_state(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def scan(transcript_path, state):
    """Read assistant messages appended since state['offset'] and fold their
    usage into the running sums. Returns True when anything new was read."""
    offset = state.get("offset", 0)
    try:
        size = os.path.getsize(transcript_path)
    except OSError:
        return False
    if size < offset:
        # The transcript was rewritten (a compaction or a resume). Start over.
        offset = 0
        for key in ("input_tokens", "output_tokens", "cache_read_tokens",
                    "cache_creation_tokens", "turns"):
            state[key] = 0
    if size == offset:
        return False
    with open(transcript_path, "rb") as fh:
        fh.seek(offset)
        chunk = fh.read()
    # Only consume complete lines, so a line still being written is read
    # next time rather than parsed half-finished.
    last_newline = chunk.rfind(b"\n")
    if last_newline < 0:
        return False
    chunk = chunk[: last_newline + 1]
    state["offset"] = offset + len(chunk)
    for raw in chunk.splitlines():
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "assistant" or entry.get("isSidechain"):
            continue
        message = entry.get("message") or {}
        usage = message.get("usage") or {}
        if not usage:
            continue
        inp = usage.get("input_tokens", 0) or 0
        read = usage.get("cache_read_input_tokens", 0) or 0
        write = usage.get("cache_creation_input_tokens", 0) or 0
        out = usage.get("output_tokens", 0) or 0
        state["input_tokens"] = state.get("input_tokens", 0) + inp
        state["cache_read_tokens"] = state.get("cache_read_tokens", 0) + read
        state["cache_creation_tokens"] = state.get("cache_creation_tokens", 0) + write
        state["output_tokens"] = state.get("output_tokens", 0) + out
        state["turns"] = state.get("turns", 0) + 1
        state["context_tokens"] = inp + read + write
        if message.get("model"):
            state["model"] = message["model"]
    return True


def main():
    payload = json.load(sys.stdin)
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or "."
    session_id = payload.get("session_id") or "unknown"
    transcript = payload.get("transcript_path")
    if not transcript or not os.path.isfile(transcript):
        return
    path = state_path(project_dir, session_id)
    state = load_state(path) or {"session_id": session_id, "offset": 0, "warned": []}
    if not scan(transcript, state):
        return
    state["cwd"] = payload.get("cwd")
    state["window"] = window_for(state.get("model"))
    state["updated_at"] = datetime.datetime.now(
        datetime.timezone.utc).isoformat(timespec="seconds")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(state, fh, indent=2)

    if payload.get("hook_event_name") != "PostToolUse":
        return
    fraction = state.get("context_tokens", 0) / state["window"]
    warned = set(state.get("warned") or [])
    for threshold, tier, text in reversed(TIERS):
        if fraction >= threshold and tier not in warned:
            warned.add(tier)
            state["warned"] = sorted(warned)
            with open(path, "w") as fh:
                json.dump(state, fh, indent=2)
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": (
                        f"[session-usage] {text} Context "
                        f"{state['context_tokens']:,} of {state['window']:,} tokens."
                    ),
                }
            }))
            break


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
