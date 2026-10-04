#!/usr/bin/env python3
"""Dashboard event hook. Registered for PreToolUse and PostToolUse on the
subagent dispatch tool (Task/Agent) and for SubagentStop. Appends one JSON line per dispatch or
completion to the run's events.jsonl so the dashboard TUI can show live
agent activity and so derive-ready-queue.py can refuse to plan while a
dispatch is un-joined. Events that cannot be attributed to a run go to
runs/_dashboard/events.jsonl. Never blocks the tool call: always exits 0.

A foreground dispatch returns when the agent finishes, so its PostToolUse
event is a real completion. A background dispatch (run_in_background) returns
at once while the agent keeps running, so its PostToolUse is logged as
agent_backgrounded, which is not a join. SubagentStop fires when the subagent
itself finishes, foreground or background, and is logged as agent_stopped
carrying the agent_id and, when present, the tool_use_id. A background
dispatch is joined by agent_stopped through either id, or by the harness
appending agent_joined or agent_abandoned."""

import datetime
import json
import os
import re
import sys

RUN_REF = re.compile(r"runs/([A-Za-z0-9._-]+)/")
AGENT_ID = re.compile(r"agentId:\s*([A-Za-z0-9_-]+)")
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


def resolve_model(tool_input, project_dir):
    """The model a dispatch runs on: the per-dispatch override when the
    harness passed one (a mechanical unit sent to haiku), else the model the
    agent declares in its frontmatter, else None. The dashboard prices tokens
    by this value, so an unknown model is left unknown rather than guessed."""
    if tool_input.get("model"):
        return tool_input["model"]
    agent = tool_input.get("subagent_type")
    if not agent:
        return None
    path = os.path.join(project_dir, ".claude", "agents", f"{agent}.md")
    try:
        with open(path) as fh:
            lines = fh.read().split("\n", 40)
    except OSError:
        return None
    # Frontmatter is the block between the first two "---" lines.
    fences = 0
    for line in lines:
        if line.strip() == "---":
            fences += 1
            if fences == 2:
                break
            continue
        if fences == 1 and line.startswith("model:"):
            return line.split(":", 1)[1].strip()
    return None


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
    hook = payload.get("hook_event_name")

    background = bool(tool_input.get("run_in_background"))
    if hook == "SubagentStop":
        kind = "agent_stopped"
    elif hook == "PreToolUse":
        kind = "agent_dispatched"
    elif background:
        kind = "agent_backgrounded"
    else:
        kind = "agent_completed"
    event = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "event": kind,
        "session_id": payload.get("session_id"),
        "tool_use_id": payload.get("tool_use_id"),
        "agent": tool_input.get("subagent_type") or payload.get("agent_type") or "unknown",
        "description": tool_input.get("description") or "",
        "background": background,
    }
    if hook != "SubagentStop":
        event["model"] = resolve_model(tool_input, project_dir)
    if hook == "SubagentStop":
        event["agent_id"] = payload.get("agent_id")
        event["description"] = payload.get("agent_transcript_path") or ""
    elif kind == "agent_backgrounded":
        # The background Agent result text names the agent id. Keep it so a
        # later agent_stopped can be matched back to this dispatch.
        match = AGENT_ID.search(json.dumps(payload.get("tool_response") or ""))
        event["agent_id"] = match.group(1) if match else None

    run_id = detect_run_id(payload, project_dir)
    event["run_id"] = run_id

    if event["event"] == "agent_completed":
        metrics = {}
        find_metrics(payload.get("tool_response"), metrics)
        if metrics:
            event["metrics"] = metrics

    if not run_id and hook == "SubagentStop":
        run_id = detect_run_id({"tool_input": {}}, project_dir)
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
