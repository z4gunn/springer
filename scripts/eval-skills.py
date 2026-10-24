#!/usr/bin/env python3
"""Measure whether agents follow the procedures that hold Springer together.

A skill or agent body says what to do. Nothing measured whether a dispatched
agent did it, so a rule that a model ignored stayed in the reference looking
like a rule. A scenario in evals/ sets up a small workspace, sends one prompt
through headless Claude Code, and states what the transcript must show: a
tool call that must happen, one that must never happen, one that must come
before another, and what the final message must say. The checker is a pure
function of the stream-json transcript, so it is tested without a model, and
a live run repeats a scenario to report a pass rate rather than one anecdote.
Stdlib only.

Usage:
    python3 scripts/eval-skills.py list
    python3 scripts/eval-skills.py check <scenario> <transcript.jsonl>
    python3 scripts/eval-skills.py run [<scenario>...] [--runs N] [--model M] [--keep]

A scenario is evals/<id>.json:
    {"id": "...", "about": "what behavior this measures",
     "workspace": {"path": "file text", ...}, "adopt_profile": "small",
     "prompt": "...", "model": "sonnet", "max_turns": 40,
     "allowed_tools": ["Read", "Write", "Edit", "Bash", "Agent"],
     "expect": [<assertion>, ...]}

An assertion is one of:
    {"type": "called", "match": M}           some tool call matches M
    {"type": "never", "match": M}            no tool call matches M
    {"type": "before", "first": M, "then": M} the first match of `first`
                                              precedes the first match of `then`,
                                              and both occur
    {"type": "final", "pattern": "regex"}    the final result text matches
    {"type": "any_of", "of": [<assertion>, ...]}
Each may carry an "id" and a "why". A matcher M is {"tool": "regex on the
tool name", "path": "regex on the file_path or notebook_path", "command":
"regex on a Bash command", "input": "regex on the whole input JSON",
"scope": "any" | "main" | "subagent"}, or {"or": [M, ...]}. Prefer `path`
and `command`: `input` also matches text a tool merely writes, such as a
report that mentions a file.

run copies the scenario workspace into a temporary git repository, adopts
this checkout's runtime into it with update-project.py when adopt_profile is
set, runs `claude -p` with stream-json output, checks the transcript, and
writes the transcripts and a results file under runs/_evals/. It spends model
tokens, so CI runs only the checker tests. Exit 0 when every run of every
scenario passed, 1 when any failed, 2 on usage or a missing claude binary.
"""

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EVALS = REPO / "evals"
OUT = REPO / "runs" / "_evals"


def load_scenario(ref):
    path = Path(ref)
    if not path.exists():
        path = EVALS / f"{ref}.json"
    scenario = json.loads(path.read_text())
    for key in ("id", "prompt", "expect"):
        if key not in scenario:
            raise ValueError(f"{path}: scenario needs '{key}'")
    return scenario


def parse_transcript(lines):
    """Return (calls, final_text). calls is every tool_use in order as
    {name, input, scope}, where scope is main or subagent by whether the
    message carries a parent tool use."""
    calls, finals = [], []
    for line in lines:
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if event.get("type") == "assistant":
            content = (event.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            scope = "subagent" if event.get("parent_tool_use_id") else "main"
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    calls.append({"name": block.get("name", ""), "input": block.get("input") or {},
                                  "scope": scope})
        elif event.get("type") == "result" and isinstance(event.get("result"), str):
            finals.append(event["result"])
    return calls, "\n".join(finals)


def matches(call, matcher):
    if "or" in matcher:
        return any(matches(call, m) for m in matcher["or"])
    scope = matcher.get("scope", "any")
    if scope != "any" and call["scope"] != scope:
        return False
    if matcher.get("tool") and not re.search(matcher["tool"], call["name"]):
        return False
    if matcher.get("path"):
        path = call["input"].get("file_path") or call["input"].get("notebook_path") or ""
        if not re.search(matcher["path"], str(path)):
            return False
    if matcher.get("command"):
        if not re.search(matcher["command"], str(call["input"].get("command", "")), re.S):
            return False
    if matcher.get("input") and not re.search(matcher["input"], json.dumps(call["input"]), re.S):
        return False
    return True


def first_index(calls, matcher):
    return next((i for i, c in enumerate(calls) if matches(c, matcher)), None)


def evaluate(assertion, calls, final):
    """Return (passed, detail)."""
    kind = assertion.get("type")
    if kind == "called":
        i = first_index(calls, assertion["match"])
        return i is not None, f"first match at call {i}" if i is not None else "no matching call"
    if kind == "never":
        i = first_index(calls, assertion["match"])
        return i is None, "no matching call" if i is None else f"matched call {i}: {calls[i]['name']}"
    if kind == "before":
        a, b = first_index(calls, assertion["first"]), first_index(calls, assertion["then"])
        if a is None or b is None:
            return False, f"first at {a}, then at {b}, both must occur"
        return a < b, f"first at call {a}, then at call {b}"
    if kind == "final":
        ok = re.search(assertion["pattern"], final, re.S | re.I) is not None
        return ok, "final text matches" if ok else "final text does not match"
    if kind == "any_of":
        results = [evaluate(a, calls, final) for a in assertion["of"]]
        ok = any(r[0] for r in results)
        return ok, "; ".join(r[1] for r in results)
    return False, f"unknown assertion type {kind}"


def check(scenario, lines):
    calls, final = parse_transcript(lines)
    results = []
    for n, assertion in enumerate(scenario["expect"], 1):
        ok, detail = evaluate(assertion, calls, final)
        results.append({"id": assertion.get("id", f"A{n}"), "passed": ok, "detail": detail,
                        "why": assertion.get("why", "")})
    return {"scenario": scenario["id"], "passed": all(r["passed"] for r in results),
            "calls": len(calls), "assertions": results}


def print_check(result):
    print(f"{'PASS' if result['passed'] else 'FAIL'} {result['scenario']} ({result['calls']} tool calls)")
    for r in result["assertions"]:
        print(f"  {'ok ' if r['passed'] else 'BAD'} {r['id']}: {r['detail']}")


def build_workspace(scenario, root):
    for rel, text in (scenario.get("workspace") or {}).items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    env = dict(os.environ, GIT_AUTHOR_NAME="eval", GIT_AUTHOR_EMAIL="eval@local",
               GIT_COMMITTER_NAME="eval", GIT_COMMITTER_EMAIL="eval@local")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True, env=env)
    if scenario.get("adopt_profile"):
        subprocess.run([sys.executable, str(REPO / "scripts" / "update-project.py"), "adopt", str(root),
                        "--profile", scenario["adopt_profile"]], check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "eval workspace"], cwd=root, check=True, env=env)


def run_once(scenario, model, keep, transcript_path):
    with tempfile.TemporaryDirectory(prefix=f"spgr-eval-{scenario['id']}-") as tmp:
        root = Path(tmp)
        build_workspace(scenario, root)
        cmd = ["claude", "-p", scenario["prompt"], "--output-format", "stream-json", "--verbose",
               "--model", model or scenario.get("model", "sonnet"),
               "--max-turns", str(scenario.get("max_turns", 40)),
               "--permission-mode", "acceptEdits"]
        if scenario.get("allowed_tools"):
            cmd += ["--allowedTools", *scenario["allowed_tools"]]
        proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True,
                              timeout=scenario.get("timeout_s", 1800))
        transcript_path.write_text(proc.stdout)
        if keep:
            kept = transcript_path.with_suffix("")
            shutil.copytree(root, kept, ignore=shutil.ignore_patterns(".git"))
        return check(scenario, proc.stdout.splitlines())


def cmd_run(refs, runs, model, keep):
    if shutil.which("claude") is None:
        sys.stderr.write("eval-skills: the claude CLI is not on PATH\n")
        return 2
    refs = refs or sorted(p.stem for p in EVALS.glob("*.json"))
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = OUT / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    for ref in refs:
        scenario = load_scenario(ref)
        results = []
        for n in range(1, runs + 1):
            result = run_once(scenario, model, keep, out_dir / f"{scenario['id']}-{n}.jsonl")
            print_check(result)
            results.append(result)
        passed = sum(1 for r in results if r["passed"])
        summary.append({"scenario": scenario["id"], "passed": passed, "runs": runs, "results": results})
        print(f"{scenario['id']}: {passed}/{runs} runs passed")
    (out_dir / "results.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"results written to {out_dir.relative_to(REPO)}")
    return 0 if all(s["passed"] == s["runs"] for s in summary) else 1


def main(argv):
    args = argv[1:]
    if not args or args[0] not in ("list", "check", "run"):
        sys.stderr.write(next(b for b in __doc__.split("\n\n") if b.startswith("Usage:")) + "\n")
        return 2
    try:
        if args[0] == "list":
            for path in sorted(EVALS.glob("*.json")):
                s = load_scenario(path)
                print(f"{s['id']}: {s.get('about', '')}")
            return 0
        if args[0] == "check":
            if len(args) != 3:
                sys.stderr.write("usage: eval-skills.py check <scenario> <transcript.jsonl>\n")
                return 2
            result = check(load_scenario(args[1]), Path(args[2]).read_text().splitlines())
            print_check(result)
            return 0 if result["passed"] else 1
        refs, runs, model, keep, i = [], 1, None, False, 1
        while i < len(args):
            if args[i] == "--runs" and i + 1 < len(args):
                runs, i = int(args[i + 1]), i + 2
            elif args[i] == "--model" and i + 1 < len(args):
                model, i = args[i + 1], i + 2
            elif args[i] == "--keep":
                keep, i = True, i + 1
            elif args[i].startswith("--"):
                sys.stderr.write(f"unknown flag {args[i]}\n")
                return 2
            else:
                refs.append(args[i])
                i += 1
        return cmd_run(refs, runs, model, keep)
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"eval-skills: {exc}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
