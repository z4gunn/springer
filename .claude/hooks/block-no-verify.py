#!/usr/bin/env python3
"""Block a git command that bypasses the hook chain.

git-workflow.md says the full pre-commit chain runs with no bypass and that
--no-verify is never passed. A rule in a reference is advice to a model. This
PreToolUse hook on Bash makes it mechanical: a command that carries
--no-verify, --no-gpg-sign, or -n as a commit flag is refused with exit 2,
which Claude Code reads as a block, and the reason is printed so the agent
fixes the failing hook instead of skipping it. Everything else passes.

Registered in templates/project-settings.json and .claude/settings.json under
PreToolUse with the Bash matcher. Reads the hook payload on stdin. Never
raises, and a malformed payload passes through, because a hook that fails
closed on its own bug would stop every shell command.
"""

import json
import re
import sys

BYPASS = re.compile(r"(^|\s)--no-verify(\s|$)|(^|\s)--no-gpg-sign(\s|$)|(^|\s)git\s+commit\b[^|;&]*\s-n(\s|$)")


def decide(command):
    """Return the refusal message, or None when the command passes."""
    if not command or "git" not in command:
        return None
    if BYPASS.search(command):
        return ("block-no-verify: this command bypasses the git hook chain (--no-verify or "
                "--no-gpg-sign). Fix the failing hook and rerun without the flag. "
                "See .claude/references/git-workflow.md, Commit discipline.")
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if payload.get("tool_name") not in (None, "Bash"):
        return 0
    command = (payload.get("tool_input") or {}).get("command", "")
    message = decide(command)
    if message:
        sys.stderr.write(message + "\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
