#!/usr/bin/env python3
"""Live terminal dashboard for a Springer run.

Polls the run store (run-state.json, cycle records, gate and escalation
artifacts) plus the events.jsonl feed written by the log-agent-events hook,
and redraws once per interval. Stdlib only.

Usage:
  python3 scripts/run-dashboard.py [run-id-or-path] [--interval N] [--once]

With no run argument, watches the run whose run-state.json changed most
recently. --once prints a single frame and exits, for piping or testing.
"""

import argparse
import datetime
import glob
import json
import os
import re
import shutil
import sys
import time

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
CYAN = "\x1b[36m"
YELLOW = "\x1b[33m"
GREEN = "\x1b[32m"
MAGENTA = "\x1b[35m"
RED = "\x1b[31m"

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def visible_len(s):
    return len(ANSI_RE.sub("", s))


def clip(s, width):
    """Truncate to a visible width, preserving ANSI codes and resetting."""
    if visible_len(s) <= width:
        return s
    out, vis, i = [], 0, 0
    while i < len(s) and vis < width - 1:
        m = ANSI_RE.match(s, i)
        if m:
            out.append(m.group(0))
            i = m.end()
        else:
            out.append(s[i])
            vis += 1
            i += 1
    return "".join(out) + "…" + RESET


def fmt_tokens(n):
    return f"{n:,}"


def fmt_elapsed(seconds):
    seconds = int(seconds)
    if seconds < 0:
        seconds = 0
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def parse_ts(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def resolve_run_dir(arg, repo_root):
    if arg:
        if os.path.isdir(arg):
            return arg
        candidate = os.path.join(repo_root, "runs", arg)
        if os.path.isdir(candidate):
            return candidate
        sys.exit(f"no run directory found for '{arg}'")
    runs_dir = os.path.join(repo_root, "runs")
    candidates = [
        (os.path.getmtime(p), os.path.dirname(p))
        for p in glob.glob(os.path.join(runs_dir, "*", "run-state.json"))
    ]
    if not candidates:
        sys.exit(f"no run with a run-state.json under {runs_dir}")
    candidates.sort(reverse=True)
    return candidates[0][1]


def load_json(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def find_artifact(run_dir, artifact_id):
    """A gate or escalation id resolves to <id>.json in artifacts/ or in its
    dedicated subdirectory, depending on harness version."""
    for sub in ("artifacts", "checkpoints", "escalations"):
        record = load_json(os.path.join(run_dir, sub, f"{artifact_id}.json"))
        if record:
            return record
    return None


def load_events(run_dir):
    events = []
    try:
        with open(os.path.join(run_dir, "events.jsonl")) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return events


def pair_events(events):
    """Match dispatch and completion events into agent activity rows.
    Pair on tool_use_id when present, else first unmatched dispatch with the
    same agent and description."""
    rows = []
    open_by_id = {}
    open_by_key = {}
    for ev in events:
        kind = ev.get("event")
        if kind == "agent_dispatched":
            row = {"start": ev, "end": None}
            rows.append(row)
            if ev.get("tool_use_id"):
                open_by_id[ev["tool_use_id"]] = row
            open_by_key.setdefault(
                (ev.get("agent"), ev.get("description")), []
            ).append(row)
        elif kind == "agent_completed":
            row = None
            if ev.get("tool_use_id") and ev["tool_use_id"] in open_by_id:
                row = open_by_id.pop(ev["tool_use_id"])
            else:
                queue = open_by_key.get((ev.get("agent"), ev.get("description")), [])
                row = next((r for r in queue if r["end"] is None), None)
            if row is None:
                row = {"start": None, "end": None}
                rows.append(row)
            row["end"] = ev
    return rows


def latest_cycle(run_dir):
    paths = sorted(glob.glob(os.path.join(run_dir, "artifacts", "CYCLE-*.json")))
    return load_json(paths[-1]) if paths else None


def hrule(width, char="─"):
    return DIM + char * width + RESET


def section(title, width):
    return f"{CYAN}{BOLD} {title}{RESET}"


def render(run_dir, width):
    lines = []
    state_doc = load_json(os.path.join(run_dir, "run-state.json"))
    content = (state_doc or {}).get("content", {})
    run_id = content.get("run_id") or os.path.basename(run_dir.rstrip("/"))
    clock = datetime.datetime.now().strftime("%H:%M:%S")

    header = (
        f"{BOLD} SPRINGER{RESET}  run {BOLD}{run_id}{RESET}"
        f"   phase {CYAN}{content.get('active_phase', '?')}{RESET}"
        f"   cycle {content.get('cycle_counter', '?')}"
    )
    pad = max(1, width - visible_len(header) - len(clock) - 1)
    lines.append(header + " " * pad + DIM + clock + RESET)
    lines.append(hrule(width))

    if state_doc is None:
        lines.append(f" {RED}run-state.json missing or unreadable{RESET}")
        return lines

    cycle = latest_cycle(run_dir)
    cycle_no = ((cycle or {}).get("content") or {}).get("cycle_number")
    if (
        cycle_no is not None
        and content.get("generated_from_cycle") is not None
        and cycle_no > content["generated_from_cycle"]
    ):
        lines.append(
            f" {YELLOW}⚠ projection stale: run-state reflects cycle "
            f"{content['generated_from_cycle']}, log has {cycle_no}{RESET}"
        )

    # Gates and escalations, the reasons a run is waiting, come first.
    gates = content.get("open_gates") or []
    escalations = content.get("open_escalations") or []
    if gates or escalations:
        lines.append(section("WAITING ON HUMAN", width))
        for gate_id in gates:
            record = find_artifact(run_dir, gate_id) or {}
            gc = record.get("content", {})
            opened = parse_ts(record.get("timestamp"))
            age = f" (waiting {fmt_elapsed((now_utc() - opened).total_seconds())})" if opened else ""
            lines.append(
                clip(
                    f"  {MAGENTA}⏸ {gate_id}{RESET} "
                    f"{gc.get('checkpoint_type', 'checkpoint')}{DIM}{age}{RESET}",
                    width,
                )
            )
            prompt = gc.get("decision_prompt")
            if prompt:
                lines.append(clip(f"    {DIM}{prompt}{RESET}", width))
        for esc_id in escalations:
            record = find_artifact(run_dir, esc_id) or {}
            ec = record.get("content", {})
            lines.append(
                clip(
                    f"  {RED}⚑ {esc_id}{RESET} {ec.get('escalation_type', '')}"
                    f" {DIM}{ec.get('description', '')}{RESET}",
                    width,
                )
            )
        lines.append(hrule(width))

    # WIP board.
    wip = content.get("wip_board") or {}
    lines.append(section("WIP BOARD", width))
    stages = ["backlog", "development", "review", "validation", "done"]
    caps = {"development": 2, "review": 2, "validation": 2}
    col_w = max(12, (width - 2) // len(stages))
    heads = []
    for stage in stages:
        items = wip.get(stage) or []
        cap = f"/{caps[stage]}" if stage in caps else ""
        label = f"{stage} {len(items)}{cap}"
        color = YELLOW if stage in caps and len(items) >= caps[stage] else CYAN
        heads.append(clip(f"{color}{label}{RESET}", col_w - 1).ljust(
            col_w - 1 + len(color) + len(RESET)
        ))
    lines.append("  " + "".join(heads))
    depth = max([len(wip.get(s) or []) for s in stages] + [0])
    for i in range(min(depth, 8)):
        row = []
        for stage in stages:
            items = wip.get(stage) or []
            cell = items[i] if i < len(items) else ""
            row.append(clip(cell, col_w - 1).ljust(col_w - 1))
        lines.append("  " + "".join(row))
    if depth > 8:
        lines.append(f"  {DIM}… {depth - 8} more rows{RESET}")
    if depth == 0:
        lines.append(f"  {DIM}board empty{RESET}")

    ready = content.get("ready_queue") or []
    if ready:
        units = ", ".join(u.get("agent", "?") for u in ready)
        lines.append(clip(f"  {DIM}ready queue: {units}{RESET}", width))
    lines.append(hrule(width))

    # Agent activity from the hook event feed.
    lines.append(section("AGENTS", width))
    rows = pair_events(load_events(run_dir))
    if not rows:
        lines.append(
            f"  {DIM}no events yet. The log-agent-events hook records dispatches"
            f" here as the harness runs.{RESET}"
        )
    in_flight = [r for r in rows if r["start"] and not r["end"]]
    finished = [r for r in rows if r["end"]]
    for row in in_flight:
        start = parse_ts(row["start"].get("ts"))
        elapsed = fmt_elapsed((now_utc() - start).total_seconds()) if start else "?"
        stale = start and (now_utc() - start).total_seconds() > 2 * 3600
        mark = f"{DIM}● stale?{RESET}" if stale else f"{YELLOW}●{RESET}"
        lines.append(
            clip(
                f"  {mark} {BOLD}{row['start'].get('agent', '?'):<32}{RESET}"
                f" {row['start'].get('description', '')}"
                f"  {YELLOW}{elapsed}{RESET}",
                width,
            )
        )
    for row in finished[-6:]:
        ev = row["end"]
        metrics = ev.get("metrics") or {}
        dur = (
            fmt_elapsed(metrics["duration_ms"] / 1000)
            if metrics.get("duration_ms")
            else ""
        )
        tok = (
            f"{fmt_tokens(metrics['total_tokens'])} tok"
            if metrics.get("total_tokens")
            else ""
        )
        lines.append(
            clip(
                f"  {GREEN}✓{RESET} {ev.get('agent', '?'):<32}"
                f" {ev.get('description', '')}"
                f"  {DIM}{dur}  {tok}{RESET}",
                width,
            )
        )
    hidden = len(finished) - 6
    if hidden > 0:
        lines.append(f"  {DIM}… {hidden} earlier completions{RESET}")
    lines.append(hrule(width))

    # Token rollup across all completions.
    totals = {}
    by_agent = {}
    for row in finished:
        metrics = (row["end"].get("metrics") or {})
        for key, value in metrics.items():
            if key != "duration_ms":
                totals[key] = totals.get(key, 0) + value
        if metrics.get("total_tokens"):
            agent = row["end"].get("agent", "?")
            by_agent[agent] = by_agent.get(agent, 0) + metrics["total_tokens"]
    lines.append(section("TOKENS", width))
    if totals:
        parts = [f"total {BOLD}{fmt_tokens(totals.get('total_tokens', 0))}{RESET}"]
        for key, label in (
            ("input_tokens", "in"),
            ("output_tokens", "out"),
            ("cache_read_tokens", "cache-read"),
        ):
            if key in totals:
                parts.append(f"{label} {fmt_tokens(totals[key])}")
        lines.append(clip("  " + "   ".join(parts), width))
        top = sorted(by_agent.items(), key=lambda kv: -kv[1])[:4]
        if top:
            breakdown = ", ".join(f"{a} {fmt_tokens(t)}" for a, t in top)
            lines.append(clip(f"  {DIM}by agent: {breakdown}{RESET}", width))
    else:
        lines.append(f"  {DIM}no token metrics recorded yet{RESET}")
    lines.append(hrule(width))

    # Last cycle summary.
    if cycle:
        cc = cycle.get("content", {})
        transition = (cc.get("act") or {}).get("transition", "?")
        verdict = (cc.get("check") or {}).get("verdict", "?")
        lines.append(section("LAST CYCLE", width))
        lines.append(
            clip(
                f"  {cc.get('cycle_id', '?')}  check {verdict} → act {transition}",
                width,
            )
        )
        rationale = (cc.get("plan") or {}).get("rationale")
        if rationale:
            lines.append(clip(f"  {DIM}{rationale}{RESET}", width))
    return lines


def main():
    parser = argparse.ArgumentParser(description="Springer run dashboard")
    parser.add_argument("run", nargs="?", help="run id or run directory path")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--once", action="store_true", help="print one frame and exit")
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    run_dir = resolve_run_dir(args.run, repo_root)

    if args.once:
        width = shutil.get_terminal_size((100, 40)).columns
        print("\n".join(render(run_dir, width)))
        return

    sys.stdout.write("\x1b[?1049h\x1b[?25l")
    try:
        while True:
            size = shutil.get_terminal_size((100, 40))
            frame = render(run_dir, size.columns)
            frame.append("")
            frame.append(f"{DIM} watching {run_dir}  ·  ctrl-c to exit{RESET}")
            sys.stdout.write("\x1b[H" + "\x1b[K\n".join(
                clip(line, size.columns) for line in frame[: size.lines - 1]
            ) + "\x1b[0J")
            sys.stdout.flush()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
