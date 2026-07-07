#!/usr/bin/env python3
"""Dashboard event hook. Registered for PreToolUse and PostToolUse on the
subagent dispatch tool (Task/Agent). Appends one JSON line per dispatch or
completion to the run's events.jsonl so the dashboard TUI can show live
agent activity. Events that cannot be attributed to a run go to
runs/_dashboard/events.jsonl. Never blocks the tool call: always exits 0."""

import datetime
import json
import os
import re
import sys

RUN_REF = re.compile(r"runs/([A-Za-z0-9._-]+)/")
RUN_ID_FIELD = re.compile(r"run[_-]id[\"'\s:=]+([A-Za-z0-9._-]+)")

TOKEN_KEYS = {
    "totalTokens": "total_tokens",
    "total_tokens": "total_tokens",
    "input_tokens": "input_tokens",
    "output_tokens": "output_tokens",
    "cache_read_input_tokens": "cache_read_tokens",
    "cache_creation_input_tokens": "cache_creation_tokens",
    "totalDurationMs": "duration_ms",
}


def find_metrics(node, out):
    """Walk an arbitrary tool_response shape and pull any token or duration
    counters it happens to carry. The response schema varies by version, so
    match by key name instead of position."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in TOKEN_KEYS and isinstance(value, (int, float)):
                out[TOKEN_KEYS[key]] = out.get(TOKEN_KEYS[key], 0) + value
            else:
                find_metrics(value, out)
    elif isinstance(node, list):
        for item in node:
            find_metrics(item, out)


def detect_run_id(payload, project_dir):
    """Best-effort run attribution: look for a runs/<id>/ path or a run_id
    field in the dispatch prompt, then fall back to the single most recently
    ticked run store."""
    tool_input = payload.get("tool_input") or {}
    haystack = " ".join(
        str(tool_input.get(k, "")) for k in ("prompt", "description")
    )
    match = RUN_REF.search(haystack) or RUN_ID_FIELD.search(haystack)
    if match:
        return match.group(1)
    runs_dir = os.path.join(project_dir, "runs")
    try:
        candidates = [
            (os.path.getmtime(os.path.join(runs_dir, d, "run-state.json")), d)
            for d in os.listdir(runs_dir)
            if os.path.isfile(os.path.join(runs_dir, d, "run-state.json"))
        ]
    except OSError:
        return None
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def main():
    payload = json.load(sys.stdin)
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or "."
    tool_input = payload.get("tool_input") or {}

    event = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "event": "agent_dispatched"
        if payload.get("hook_event_name") == "PreToolUse"
        else "agent_completed",
        "session_id": payload.get("session_id"),
        "tool_use_id": payload.get("tool_use_id"),
        "agent": tool_input.get("subagent_type") or "unknown",
        "description": tool_input.get("description") or "",
    }

    run_id = detect_run_id(payload, project_dir)
    event["run_id"] = run_id

    if event["event"] == "agent_completed":
        metrics = {}
        find_metrics(payload.get("tool_response"), metrics)
        if metrics:
            event["metrics"] = metrics

    if run_id and os.path.isdir(os.path.join(project_dir, "runs", run_id)):
        out_path = os.path.join(project_dir, "runs", run_id, "events.jsonl")
    else:
        out_path = os.path.join(project_dir, "runs", "_dashboard", "events.jsonl")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "a") as fh:
        fh.write(json.dumps(event) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
