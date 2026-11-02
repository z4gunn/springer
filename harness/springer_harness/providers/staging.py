"""Staging: a host registered per project, deployed by one of two kinds.

static-dir copies a built directory to a path, on this machine or over ssh.
compose copies the repository to a directory on the host over ssh and runs
`docker compose up -d --build` there.

plan() returns the exact commands and runs nothing, so a dry run can show them and a
person can confirm them once per project before deploy() ever runs. A host's command
is built from its record alone, never from a string a session wrote.
"""

import shlex
import subprocess
from pathlib import Path

KINDS = ("static-dir", "compose")
EXCLUDES = (".git", "node_modules", "runs", ".worktrees", ".venv")


class StagingError(ValueError):
    pass


def validate(host):
    """The record a project stores, checked. Returns it normalized."""
    if not isinstance(host, dict) or host.get("kind") not in KINDS:
        raise StagingError(f"a staging host needs kind, one of {', '.join(KINDS)}")
    if not host.get("name"):
        raise StagingError("a staging host needs a name")
    if host["kind"] == "static-dir":
        if not host.get("source") or not host.get("path"):
            raise StagingError("static-dir needs source (the built directory in the repo) and path (where it goes)")
        if Path(host["source"]).is_absolute() or ".." in Path(host["source"]).parts:
            raise StagingError("source is a path inside the repository")
    else:
        if not host.get("ssh") or not host.get("dir"):
            raise StagingError("compose needs ssh (user@host) and dir (the directory on the host)")
    return {k: v for k, v in host.items() if v not in (None, "")}


def _remote(host, path):
    return f"{host['ssh']}:{path}" if host.get("ssh") else path


def plan(host, project_path):
    """The commands a deploy runs, as argument lists, in order."""
    host = validate(host)
    project = Path(project_path)
    excludes = [f"--exclude={e}" for e in EXCLUDES]
    if host["kind"] == "static-dir":
        source = str(project / host["source"]).rstrip("/") + "/"
        commands = [["rsync", "-a", "--delete", source, _remote(host, host["path"].rstrip("/") + "/")]]
    else:
        compose = host.get("compose_file", "compose.yml")
        commands = [["rsync", "-a", "--delete", *excludes, str(project).rstrip("/") + "/", _remote(host, host["dir"].rstrip("/") + "/")],
                    ["ssh", host["ssh"], f"cd {shlex.quote(host['dir'])} && docker compose -f {shlex.quote(compose)} up -d --build"]]
    if host.get("health_url"):
        commands.append(["curl", "-fsS", "--max-time", "20", "-o", "/dev/null", host["health_url"]])
    return commands


def describe(commands):
    return [" ".join(shlex.quote(part) for part in command) for command in commands]


def deploy(host, project_path, timeout=1800):
    """Run the plan. Returns (ok, log). Stops at the first command that fails."""
    log = []
    for command in plan(host, project_path):
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        log.append(f"$ {describe([command])[0]}\n{done.stdout[-2000:]}{done.stderr[-2000:]}")
        if done.returncode:
            return False, "\n".join(log)
    return True, "\n".join(log)
