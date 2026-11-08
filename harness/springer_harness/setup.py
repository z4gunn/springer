"""springer onboard and springer doctor.

onboard is one guided pass: the coding agent and its auth, the source host, then the
optional tools, and the answers go to ~/.springer/config.json. doctor runs the same
checks any time, repairs what is safe to repair, and names what it cannot. The daemon
reads the same checks at start, so a missing tool shows in the TUI as a degradation.
"""

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .common import read_json, write_json

DEFAULTS = {"provider": "claude-code", "source_host": "github", "claude": "claude", "max_sessions": 2,
            "private_repos": True}


@dataclass
class Finding:
    name: str
    ok: bool
    detail: str
    required: bool = True
    fix: str = ""


def config_path(home):
    return Path(home) / "config.json"


def load_config(home):
    """The onboarded config, or None before onboarding. With none, the daemon runs the
    mock provider, so springer works before onboarding and spends nothing."""
    found = read_json(config_path(home))
    return {**DEFAULTS, **found} if isinstance(found, dict) else None


def save_config(home, config):
    write_json(config_path(home), {k: config[k] for k in DEFAULTS if k in config})


def _run(args, env=None, timeout=30):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(args, 127, "", str(exc))


def subscription_env():
    return {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "CLAUDECODE")}


def check_claude(binary="claude"):
    path = shutil.which(binary)
    if not path:
        return [Finding("claude", False, "Claude Code is not on PATH.", fix="Install it: npm install -g @anthropic-ai/claude-code")]
    version = _run([path, "--version"]).stdout.strip()
    status = _run([path, "auth", "status"], env=subscription_env())
    try:
        auth = json.loads(status.stdout)
    except ValueError:
        auth = {}
    found = [Finding("claude", True, f"{version} at {path}")]
    if not auth.get("loggedIn"):
        found.append(Finding("claude login", False, "Claude Code is not logged in.", fix="Run: claude auth login"))
    elif auth.get("authMethod") != "claude.ai":
        found.append(Finding("claude login", False, f"Claude Code signs in with {auth.get('authMethod')}, not a "
                             "subscription. Sessions would bill an API key.", fix="Run: claude auth login"))
    else:
        found.append(Finding("claude login", True, f"subscription ({auth.get('subscriptionType', 'unknown plan')})"))
    if os.environ.get("ANTHROPIC_API_KEY"):
        found.append(Finding("api key", True, "ANTHROPIC_API_KEY is set in this shell. Sessions remove it, so they "
                             "still run on the subscription.", required=False))
    return found


def check_github():
    """Optional: only a project switched to the github source host needs gh."""
    if not shutil.which("gh"):
        return [Finding("gh", False, "The GitHub CLI is not on PATH. Only a project using GitHub pull requests "
                        "needs it.", fix="Install it: brew install gh", required=False)]
    status = _run(["gh", "auth", "status"])
    if status.returncode:
        return [Finding("gh login", False, "gh is not logged in. Only a project using GitHub pull requests needs it.",
                        fix="Run: gh auth login", required=False)]
    account = next((line.split("account", 1)[1].split()[0] for line in (status.stdout + status.stderr).splitlines()
                    if "Logged in to" in line and "account" in line), "an account")
    return [Finding("gh login", True, f"logged in as {account}")]


def check_basics():
    found = [Finding("python", sys.version_info >= (3, 12), sys.version.split()[0], fix="Use Python 3.12 or later.")]
    git = shutil.which("git")
    found.append(Finding("git", bool(git), git or "git is not on PATH.", fix="Install git."))
    return found


def check_optional():
    impeccable = Path.home() / ".claude/skills/impeccable/scripts/impeccable"
    tools = [("playwright-cli", shutil.which("playwright-cli"), "screenshots for design comps and review"),
             ("impeccable", str(impeccable) if impeccable.exists() else shutil.which("impeccable"),
              "the design slop detector"),
             ("markitdown", shutil.which("markitdown"), "reading supplied PDF and Office files")]
    return [Finding(name, bool(where), where or f"not found, so no {what}", required=False) for name, where, what in tools]


def checks(config):
    config = config or DEFAULTS
    found = check_basics()
    if config["provider"] == "claude-code":
        found += check_claude(config["claude"])
    if config["source_host"] == "github":
        found += check_github()
    return found + check_optional()


def degradations(config):
    """One line per check that failed, for GET /v1/daemon."""
    return [f"{f.name}: {f.detail}" for f in checks(config) if not f.ok or (not f.required and "not found" in f.detail)]


def repair(home, projects):
    """What doctor fixes on its own: a stale daemon record, and worktree entries git
    still lists for directories that are gone. Returns a line per repair."""
    done = []
    record = Path(home) / "daemon.json"
    if record.exists():
        from .cli import running
        if not running(home):
            record.unlink()
            done.append("removed a stale daemon record")
    for slug, project in projects.items():
        path = Path(project["path"])
        if (path / ".git").exists():
            pruned = _run(["git", "-C", str(path), "worktree", "prune", "--verbose"])
            if pruned.stdout.strip() or pruned.stderr.strip():
                done.append(f"{slug}: pruned worktree entries git listed for missing directories")
    return done


def report(found):
    lines = []
    for f in found:
        mark = "ok  " if f.ok else ("FAIL" if f.required else "warn")
        lines.append(f"  {mark}  {f.name:14} {f.detail}")
        if not f.ok and f.fix:
            lines.append(f"        {'':14} {f.fix}")
    return "\n".join(lines)


def check_notifications(home):
    """Optional: Slack is set up and both tokens are in the keychain."""
    from .notify.notifier import load_settings
    from .notify.slack import APP_TOKEN, BOT_TOKEN, SECRET_SCOPE
    from .providers.secrets import KeyringSecrets
    if load_settings(home) is None:
        return [Finding("slack", False, "not set up, so gates reach you only in the TUI", required=False,
                        fix="Run: springer notifications setup")]
    try:
        secrets = KeyringSecrets()
        stored = all(secrets.get(SECRET_SCOPE, name) for name in (BOT_TOKEN, APP_TOKEN))
    except Exception:  # noqa: BLE001, a locked or missing keychain is the finding
        stored = False
    if not stored:
        return [Finding("slack", False, "set up, but a token is missing from the keychain", required=False,
                        fix="Run: springer notifications setup")]
    return [Finding("slack", True, "gates go to your Slack direct messages", required=False)]


def doctor(home):
    from .registry import Home
    config = load_config(home)
    print("springer doctor")
    if config is None:
        print("  warn  config         not onboarded, so runs use the mock provider. Run: springer onboard")
    projects = Home(home).projects()
    found = checks(config) + check_notifications(home) + check_clones(home, projects)
    print(report(found))
    fixed = repair(home, projects)
    for line in fixed:
        print(f"  fixed {line}")
    failed = [f for f in found if f.required and not f.ok]
    print("All required checks pass." if not failed else f"{len(failed)} required check(s) fail.")
    return 1 if failed else 0


def check_clones(home, projects):
    """A hosted project works from the daemon's own clone. One without it yet gets it
    at the next run start, once the project has an origin to clone from."""
    found = []
    for slug, project in projects.items():
        if (project.get("settings") or {}).get("source_host") != "github":
            continue
        clone = project.get("clone")
        if clone and (Path(clone) / ".git").exists():
            found.append(Finding(f"clone {slug}", True, clone, required=False))
        else:
            found.append(Finding(f"clone {slug}", False, "no clone yet, the daemon makes one at the next run start",
                                 required=False, fix="Push the project to its origin first when it has none."))
    return found


def _ask(question, default, assume_yes):
    if assume_yes:
        return default
    answer = input(f"{question} [{default}]: ").strip()
    return answer or default


def onboard(home, assume_yes=False):
    """The guided pass. Each step checks before it asks, so a machine that is already
    set up is a run of confirmations."""
    print("springer onboard\n")
    config = load_config(home) or dict(DEFAULTS)
    print("1. Coding agent: Claude Code on your subscription session (no API key).")
    config["claude"] = _ask("   Claude Code binary", config["claude"], assume_yes)
    found = check_claude(config["claude"])
    print(report(found))
    print("\n2. Source host: GitHub through the gh CLI.")
    found += check_github()
    print(report(found[-1:]))
    private = _ask("   New project repositories are private (yes/no)", "yes" if config["private_repos"] else "no",
                   assume_yes)
    config["private_repos"] = private.lower().startswith("y")
    print("\n3. Sessions in parallel, drawn from one usage window.")
    config["max_sessions"] = int(_ask("   At most", str(config["max_sessions"]), assume_yes))
    print("\n4. Optional tools.")
    print(report(check_optional()))
    failed = [f for f in found if f.required and not f.ok]
    if failed:
        print("\nOnboarding stopped. Fix the FAIL lines above, then run springer onboard again.")
        return 1
    config["provider"], config["source_host"] = "claude-code", "github"
    save_config(home, config)
    print(f"\nSaved {config_path(home)}.")
    from .cli import ensure_daemon, stop_daemon
    stop_daemon(home)  # the running daemon read the old config
    record = ensure_daemon(home)
    print(f"The daemon is running on port {record['port']}. Run springer to open it.")
    return 0
