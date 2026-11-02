"""The Claude Code provider: one headless `claude -p` session per unit.

It runs on the subscription session the CLI is logged into on this machine, never an
API key, so ANTHROPIC_API_KEY is removed from every session's environment. A session
runs as the unit's agent (`--agent`) inside the unit's worktree, so it loads that
project's runtime, CLAUDE.md, hooks, and permission allowlist. Edits are accepted and
a question to a person is not a tool it has: a session that needs one writes
gate-request.json instead.

The stream is stream-json, read on a thread. Each rate_limit_event carries the
five-hour window's utilization and reset, which is the usage signal the scheduler
budgets against. Cost is the CLI's list-price figure, shown as information.
"""

import json
import os
import shutil
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .coding_agent import SessionExit, SpawnRequest, Usage

CONTEXT_TOKENS = 200_000
# Read-only commands a headless session reaches for in nearly every compound command.
# A person approves them in an interactive session, and a headless one has nobody to
# ask, so they are allowed outright. None of them writes.
READ_ONLY = ("Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)", "Bash(grep:*)",
             "Bash(rg:*)", "Bash(sort:*)", "Bash(uniq:*)", "Bash(diff:*)", "Bash(pwd)",
             "Bash(echo:*)", "Bash(test:*)", "Bash(stat:*)", "Bash(file:*)", "Bash(jq:*)", "Bash(which:*)",
             "Bash(git ls-files:*)", "Bash(git branch --show-current:*)")
TIERS = {"haiku": "haiku", "sonnet": "sonnet", "opus": "opus"}
PREAMBLE = Path(".claude/skills/spgr-run-harness/assets/dispatch-preamble.md")
# What every session leaves for Check, in the session directory the brief names.
OUTPUT_CONTRACT = """
## Where your result goes

The harness reads files, not your transcript. Before you stop, write these to the
session directory {session_dir}:

- result.json, one object:
  {{"status": "pass" or "fail", "outcome": "artifact" or "pr",
    "pr": {{"number": <int>, "branch": "<branch>", "base": "<base>"}} (only when outcome is pr),
    "touched_paths": ["<repo-relative path>", ...],
    "failure_class": "defect" | "blocked" | "environment" | "context" | "question" (only on fail),
    "detail": "<one line>"}}
- return.txt, your fifteen-line return.
- handoff.md only if you are stopping before the work is done, saying where to continue.

Your shell already starts in your worktree, which is the repository you work in. Run
commands from there with relative paths: do not cd first and do not use git -C, because
a headless session cannot ask anyone to approve a command outside its allowlist, and a
denied command is a failed unit. Validate with `python3 schemas/validate.py <path>`.

Use {session_dir} as the unit directory for receipt.py. Write run artifacts to
{run_dir}/artifacts/ by that absolute path, which is the run store the harness owns, and
do not commit copies of anything under runs/ in your worktree. Commit everything else
(docs/, source, tests) on the branch you are on ({branch}). When the
outcome is a pull request, push this branch and open the PR against {base} with
spgr-create-pr, then put its number in result.json.

If you need a person to decide something, do not ask in text: write gate-request.json
to the session directory as spgr-notify-human describes, set status "pass" with
detail "waiting on a person", and stop.
"""


def permissions(cwd):
    """The project's own allow and deny lists, passed as flags. Claude Code ignores a
    settings file's allowlist in a directory nobody marked trusted, and every unit
    worktree is a new directory, so the flags carry the allowlist instead."""
    try:
        settings = json.loads((Path(cwd) / ".claude" / "settings.json").read_text())
    except (OSError, ValueError):
        return [], []
    found = settings.get("permissions") or {}
    return expand_directories(cwd, found.get("allow") or []), list(found.get("deny") or [])


def expand_directories(cwd, rules):
    """A Bash prefix rule matches whole words, so `Bash(python3 dir/:*)` never matches
    `python3 dir/script.py`. Each such rule becomes one rule per file in the directory."""
    import re
    out = []
    for rule in rules:
        found = re.fullmatch(r"Bash\((\S+) (\S+/):\*\)", rule)
        folder = Path(cwd) / found.group(2) if found else None
        if folder and folder.is_dir():
            out += [f"Bash({found.group(1)} {found.group(2)}{p.name}:*)" for p in sorted(folder.iterdir())
                    if p.is_file() and not p.name.startswith(".")]
        else:
            out.append(rule)
    return out


def role_prompt(cwd, agent):
    """An agent file's body, for a call that needs tools its frontmatter leaves out."""
    path = Path(cwd) / ".claude" / "agents" / f"{agent}.md"
    if not path.exists():
        return ""
    text = path.read_text()
    return text.split("---", 2)[2].strip() if text.startswith("---") else text


def json_from_text(text):
    """The last JSON object in a reply, fenced or bare, or None."""
    import re
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text or "", re.S) or [text or ""]
    for block in reversed(blocks):
        try:
            found = json.loads(block)
            if isinstance(found, dict):
                return found
        except ValueError:
            continue
    return None


def _iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def signal_from(info):
    """{"used_fraction", "resets_at"} from a rate_limit_event, or None."""
    if not isinstance(info, dict):
        return None
    windows = info.get("unifiedWindows") or {}
    five = windows.get("five_hour") or {}
    used = five.get("utilization")
    resets = five.get("resetsAt") or info.get("resetsAt")
    if info.get("status") == "rejected" or five.get("status") == "rejected":
        used = 1.0
    if used is None and resets is None:
        return None
    return {"used_fraction": used, "resets_at": _iso(resets) if resets else None}


class ClaudeSession:
    def __init__(self, request: SpawnRequest, command, env, on_signal):
        self.request = request
        self.model = TIERS.get(request.model_tier, request.model_tier)
        self.provider_session_id = None
        self._events = []
        self._lock = threading.Lock()
        self._usage = Usage()
        self._final = None
        self._on_signal = on_signal
        out = Path(request.session_dir)
        out.mkdir(parents=True, exist_ok=True)
        self._stream = open(out / "stream.jsonl", "a")
        self._stderr = open(out / "stderr.txt", "a")
        self.proc = subprocess.Popen(command, cwd=str(request.cwd), env=env, stdout=subprocess.PIPE,
                                     stderr=self._stderr, stdin=subprocess.DEVNULL, text=True,
                                     start_new_session=True)
        self.pid = self.proc.pid
        self._reader = threading.Thread(target=self._read, name=f"claude-{request.unit_id}", daemon=True)
        self._reader.start()

    def _read(self):
        for line in self.proc.stdout:
            self._stream.write(line)
            self._stream.flush()
            try:
                event = json.loads(line)
            except ValueError:
                continue
            self._take(event)
        self.proc.wait()
        self._stream.close()
        self._stderr.close()

    def _take(self, event):
        kind = event.get("type")
        with self._lock:
            if kind == "system" and event.get("subtype") == "init":
                self.provider_session_id = event.get("session_id")
                self.model = event.get("model") or self.model
            elif kind == "rate_limit_event":
                found = signal_from(event.get("rate_limit_info"))
                if found:
                    self._on_signal(found)
            elif kind == "assistant":
                message = event.get("message") or {}
                usage = message.get("usage") or {}
                context = sum(usage.get(k, 0) for k in ("input_tokens", "cache_read_input_tokens",
                                                        "cache_creation_input_tokens"))
                if context:
                    self._usage.context_percent = round(100 * context / CONTEXT_TOKENS, 1)
                self._usage.input_tokens += usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)
                self._usage.output_tokens += usage.get("output_tokens", 0)
                for block in message.get("content") or []:
                    if block.get("type") == "tool_use":
                        self._events.append({"type": "tool_use", "name": block.get("name")})
                    elif block.get("type") == "text" and block.get("text", "").strip():
                        self._events.append({"type": "text", "text": block["text"][:2000]})
            elif kind == "result":
                self._final = event
                self._usage.cost_usd = round(event.get("total_cost_usd") or 0, 4)
                self._events.append({"type": "result", "subtype": event.get("subtype"),
                                     "is_error": event.get("is_error", False)})

    def poll(self):
        with self._lock:
            events, self._events = self._events, []
        return events

    def usage(self):
        with self._lock:
            return Usage(self._usage.input_tokens, self._usage.output_tokens, self._usage.context_percent,
                         self._usage.cost_usd)

    def alive(self):
        return self.proc.poll() is None or self._reader.is_alive()

    def exit(self):
        """The session ended on its own terms once the process exited and the stream
        is read. A session that wrote a handoff and no result is a handoff."""
        if self.proc.poll() is None or self._reader.is_alive():
            return None
        out = Path(self.request.session_dir)
        final_text = (self._final or {}).get("result") or ""
        if not (out / "return.txt").exists():
            (out / "return.txt").write_text(final_text or self._tail_stderr())
        if (out / "handoff.md").exists() and not (out / "result.json").exists():
            return SessionExit("handoff", self.proc.returncode)
        return SessionExit("return", self.proc.returncode)

    def _tail_stderr(self):
        path = Path(self.request.session_dir) / "stderr.txt"
        return path.read_text()[-4000:] if path.exists() else ""

    def kill(self):
        if self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass


class ClaudeCodeProvider:
    name = "claude-code"
    mechanical = True  # Check runs receipts, classification, and schema validation

    def __init__(self, binary="claude", extra_args=()):
        self.binary = shutil.which(binary) or binary
        self.extra_args = tuple(extra_args)
        self._signal = None
        self._signal_lock = threading.Lock()

    def _record(self, found):
        with self._signal_lock:
            self._signal = found

    def usage_signal(self):
        with self._signal_lock:
            return dict(self._signal) if self._signal else None

    def prompt(self, request):
        """The shared preamble, unchanged so repeat dispatches share a cached prefix,
        then the line naming this unit's brief."""
        brief_path = Path(request.session_dir) / "brief.md"
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        env = request.env
        contract = OUTPUT_CONTRACT.format(session_dir=request.session_dir,
                                          run_dir=Path(env.get("SPRINGER_PROJECT_DIR", ".")) / "runs" /
                                          env.get("SPRINGER_RUN_ID", ""),
                                          branch=env.get("SPRINGER_BRANCH", f"unit/{request.unit_id}"),
                                          base=env.get("SPRINGER_BASE", "main"))
        brief_path.write_text(request.brief.rstrip() + "\n" + contract)
        preamble_file = Path(request.cwd) / PREAMBLE
        preamble = preamble_file.read_text() if preamble_file.exists() else "Your brief:\n"
        return preamble.rstrip() + f"\n{brief_path}\n"

    def command(self, request):
        allow, deny = permissions(request.cwd)
        command = [self.binary, "-p", self.prompt(request), "--output-format", "stream-json", "--verbose",
                   "--agent", request.agent, "--model", TIERS.get(request.model_tier, request.model_tier),
                   "--permission-mode", "acceptEdits", "--disallowedTools", "AskUserQuestion", *deny]
        run_dir = request.env.get("SPRINGER_PROJECT_DIR") and request.env.get("SPRINGER_RUN_ID")
        if run_dir:
            # The brief, the session directory, and the run artifacts live in the run
            # store in the main checkout, outside the worktree the session works in.
            command += ["--add-dir", str(Path(request.env["SPRINGER_PROJECT_DIR"]) / "runs" / request.env["SPRINGER_RUN_ID"])]
        command += ["--allowedTools", *allow, *READ_ONLY]
        return command + list(self.extra_args)

    def environment(self, request):
        env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "CLAUDECODE")}
        env.update({k: str(v) for k, v in request.env.items()})
        return env

    def spawn(self, request):
        Path(request.session_dir).mkdir(parents=True, exist_ok=True)
        return ClaudeSession(request, self.command(request), self.environment(request), self._record)


def run_once(binary, cwd, prompt, agent=None, model="sonnet", schema=None, timeout=1800, log=None):
    """One blocking headless call that returns the final structured output or text.
    Used for the judgment steps the daemon asks for outside a unit (e.g. Plan)."""
    cmd = [shutil.which(binary) or binary, "-p", prompt, "--output-format", "json", "--model", model,
           "--permission-mode", "acceptEdits", "--disallowedTools", "AskUserQuestion"]
    # The role goes in as a system prompt, not --agent: an agent's tool list would
    # leave out the tool that returns structured output.
    role = role_prompt(cwd, agent) if agent else ""
    if role:
        cmd += ["--append-system-prompt", role]
    allow, _ = permissions(cwd)
    if allow:
        cmd += ["--allowedTools", *allow]
    if schema:
        cmd += ["--json-schema", json.dumps(schema)]
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "CLAUDECODE")}
    started = time.time()
    done = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=timeout)
    if log:
        Path(log).write_text(done.stdout + "\n--- stderr ---\n" + done.stderr)
    try:
        body = json.loads(done.stdout)
    except ValueError:
        raise RuntimeError(f"claude returned no JSON (exit {done.returncode}): {done.stderr[-500:]}")
    if body.get("is_error"):
        raise RuntimeError(body.get("result") or "claude reported an error")
    output = body.get("structured_output")
    if output is None and schema:
        output = json_from_text(body.get("result"))
    return {"output": output, "text": body.get("result"),
            "cost": body.get("total_cost_usd"), "seconds": round(time.time() - started)}
