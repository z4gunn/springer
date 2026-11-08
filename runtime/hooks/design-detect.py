#!/usr/bin/env python3
"""Pass a Claude Code hook event to the impeccable design detector when it is
installed, so every Springer instance gets the live slop check without a
per-project `npx impeccable install`.

Registered in the instance settings for PostToolUse on Edit|Write and for
Stop. The detector reads the event from stdin, scans the edited UI file (or
the whole tree on Stop), and answers with a hookSpecificOutput JSON whose
additionalContext carries the findings. This script forwards stdin, stdout,
stderr, and the exit code unchanged. When no launcher is found it exits 0
with no output, so an instance on a machine without impeccable is unaffected.

The launcher is looked up in this order: the IMPECCABLE_BIN environment
variable, `impeccable` on PATH, the project-local skill install, the global
skill install under ~/.claude, then ~/.impeccable/bin. A global
`npx impeccable install` puts the launcher inside the skill folder and not on
PATH, which is why the lookup exists. The same order is used by
spgr-render-design-comps/scripts/capture-comps.py and by preflight.py.
"""

import os
import shutil
import subprocess
import sys


def find_impeccable():
    env = os.environ.get("IMPECCABLE_BIN")
    project = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    candidates = [
        env,
        shutil.which("impeccable"),
        os.path.join(project, ".claude", "skills", "impeccable", "scripts", "impeccable"),
        os.path.expanduser("~/.claude/skills/impeccable/scripts/impeccable"),
        os.path.expanduser("~/.impeccable/bin/impeccable"),
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def main():
    launcher = find_impeccable()
    if not launcher:
        return 0
    payload = sys.stdin.read()
    env = dict(os.environ)
    env.setdefault("CLAUDE_PROJECT_DIR", os.getcwd())
    try:
        proc = subprocess.run([launcher, "hook"], input=payload, capture_output=True,
                              text=True, timeout=28, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return 0
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
