#!/usr/bin/env python3
"""Run the project's product checks and record what the product showed.

A product check runs the real product on real inputs and compares what a
human would see against what the story promised. Artifact validation and a
green test suite say the work matches its description. Only this says the
product does what the human asked. The harness runs it at Check for every
unit whose diff touches UI, a pipeline, or user-visible data, and such a
unit is not done until its check passes. The checks are the project's own,
listed in `runs/_product-check.json`, each a shell command that exits 0
when the product shows the expected outcome and prints what it saw.
Stdlib only.

Usage:
    python3 product-check.py <run-dir> [--touches <path>...] [--only <id>...]
                             [--cycle <cycle-id>] [--list] [--timeout <s>]

Config, `runs/_product-check.json` beside the run directories:
    {"checks": [{"id": "names-on-leaderboard",
                 "flow": "upload the fixture resumes, open the leaderboard",
                 "expect": "at least 12 of 14 rows show a name",
                 "command": "scripts/product-check/names.sh",
                 "touches": ["packages/web/", "packages/worker/"]}]}

`touches` lists path prefixes. With `--touches` the script runs only the
checks whose prefixes match a changed path, so a diff under docs/ runs
nothing and a diff under packages/worker/ runs the checks that watch it.
Without it every check runs. Each command runs from the project root with
PRODUCT_CHECK_ID and PRODUCT_CHECK_RUN_DIR in its environment.

Writes `runs/<run-id>/product-checks/<timestamp>.json` with every result and
the tail of each command's output, and appends one `product_check` event per
check to `runs/<run-id>/events.jsonl`, which is where the dashboard's outcome
figure comes from. Prints one line per check and a summary.

Exit 0 when every selected check passed, 1 when any failed or errored, 2 on
usage, a missing or malformed config, or no check selected when the diff
touched a watched path. Exit 3 when the project has no config at all, so the
harness records the unit as unverified rather than passed.
"""

import datetime
import json
import os
import subprocess
import sys
import time

CONFIG_NAME = "_product-check.json"
OUTPUT_TAIL = 2000
DEFAULT_TIMEOUT = 900


def usage():
    print(__doc__.strip().split("\n\n")[3])
    return 2


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def load_config(runs_root):
    path = os.path.join(runs_root, CONFIG_NAME)
    if not os.path.isfile(path):
        return None, path
    with open(path) as fh:
        data = json.load(fh)
    checks = data.get("checks")
    if not isinstance(checks, list):
        raise ValueError(f"{path}: 'checks' must be a list")
    seen = set()
    for check in checks:
        for key in ("id", "command", "expect"):
            if not isinstance(check.get(key), str) or not check[key].strip():
                raise ValueError(f"{path}: every check needs a non-empty '{key}'")
        if check["id"] in seen:
            raise ValueError(f"{path}: duplicate check id {check['id']}")
        seen.add(check["id"])
        touches = check.get("touches", [])
        if not isinstance(touches, list) or any(not isinstance(t, str) for t in touches):
            raise ValueError(f"{path}: 'touches' on {check['id']} must be a list of path prefixes")
    return checks, path


def select(checks, touches, only):
    """The checks to run: by id when --only is given, else by changed path
    when --touches is given, else all. A check with no `touches` list watches
    everything and runs on any change."""
    if only:
        wanted = set(only)
        return [c for c in checks if c["id"] in wanted]
    if touches is None:
        return list(checks)
    norm = [t.lstrip("./") for t in touches]
    picked = []
    for check in checks:
        prefixes = [p.lstrip("./") for p in check.get("touches", [])]
        if not prefixes or any(path.startswith(p) for p in prefixes for path in norm):
            picked.append(check)
    return picked


def run_check(check, project_root, run_dir, timeout):
    env = dict(os.environ, PRODUCT_CHECK_ID=check["id"], PRODUCT_CHECK_RUN_DIR=run_dir)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            check["command"], shell=True, cwd=project_root, env=env,
            capture_output=True, text=True, timeout=timeout,
        )
        result = "pass" if proc.returncode == 0 else "fail"
        output = (proc.stdout or "") + (proc.stderr or "")
        code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        result, code = "error", None
        output = f"timed out after {timeout}s\n" + ((exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""))
    except OSError as exc:
        result, code, output = "error", None, str(exc)
    return {
        "check_id": check["id"],
        "flow": check.get("flow", ""),
        "expect": check["expect"],
        "command": check["command"],
        "result": result,
        "exit_code": code,
        "duration_s": round(time.monotonic() - started, 1),
        "output_tail": output[-OUTPUT_TAIL:],
    }


def record(run_dir, cycle_id, results, selected_by):
    out_dir = os.path.join(run_dir, "product-checks")
    os.makedirs(out_dir, exist_ok=True)
    stamp = now_iso().replace(":", "").replace("+0000", "Z")
    path = os.path.join(out_dir, f"{stamp}.json")
    record_body = {
        "ran_at": now_iso(),
        "cycle_id": cycle_id,
        "selected_by": selected_by,
        "results": results,
    }
    with open(path, "w") as fh:
        json.dump(record_body, fh, indent=2)
        fh.write("\n")
    run_id = os.path.basename(os.path.normpath(run_dir))
    with open(os.path.join(run_dir, "events.jsonl"), "a") as fh:
        for r in results:
            fh.write(json.dumps({
                "ts": now_iso(),
                "event": "product_check",
                "run_id": run_id,
                "cycle_id": cycle_id,
                "check_id": r["check_id"],
                "result": r["result"],
                "duration_s": r["duration_s"],
                "results_ref": os.path.relpath(path, os.path.dirname(os.path.dirname(run_dir))),
            }) + "\n")
    return path


def main(argv):
    args = argv[1:]
    if not args or args[0].startswith("-"):
        return usage()
    run_dir = os.path.abspath(args[0])
    touches, only, cycle_id, list_only, timeout = None, [], None, False, DEFAULT_TIMEOUT
    i = 1
    while i < len(args):
        a = args[i]
        if a == "--list":
            list_only = True
        elif a == "--cycle" and i + 1 < len(args):
            i += 1
            cycle_id = args[i]
        elif a == "--timeout" and i + 1 < len(args):
            i += 1
            timeout = int(args[i])
        elif a in ("--touches", "--only"):
            values = []
            while i + 1 < len(args) and not args[i + 1].startswith("--"):
                i += 1
                values.append(args[i])
            if a == "--touches":
                touches = (touches or []) + values
            else:
                only += values
        else:
            return usage()
        i += 1

    runs_root = os.path.dirname(run_dir)
    project_root = os.path.dirname(runs_root)
    if not os.path.isdir(run_dir):
        print(f"no such run directory: {run_dir}")
        return 2
    try:
        checks, config_path = load_config(runs_root)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"product-check config invalid: {exc}")
        return 2
    if checks is None:
        print(f"no product checks: {config_path} does not exist. The unit is unverified, not passed.")
        return 3

    selected = select(checks, touches, only)
    if list_only:
        for c in checks:
            mark = "*" if c in selected else " "
            print(f"{mark} {c['id']}: {c.get('flow', '')} -> {c['expect']}  [{c['command']}]")
        return 0
    if not selected:
        if touches is not None:
            print("no product check watches the changed paths, nothing to run")
            return 0
        print("no product check selected")
        return 2

    results = [run_check(c, project_root, run_dir, timeout) for c in selected]
    selected_by = {"only": only} if only else {"touches": touches}
    path = record(run_dir, cycle_id, results, selected_by)
    for r in results:
        print(f"{r['result'].upper():5} {r['check_id']}  ({r['duration_s']}s)  expect: {r['expect']}")
        if r["result"] != "pass":
            tail = r["output_tail"].strip().splitlines()[-8:]
            for line in tail:
                print(f"      | {line}")
    passed = sum(1 for r in results if r["result"] == "pass")
    print(f"{passed}/{len(results)} product checks passed, recorded at {os.path.relpath(path, project_root)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
