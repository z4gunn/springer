#!/usr/bin/env python3
"""Block an agent edit that lowers the bar a check measures against.

The fastest way to turn a red check green is to change what it checks: relax
tsconfig strictness, turn off a lint rule, drop a coverage threshold, edit
the real fixture the product check runs on, or disable a harness hook. The
review package tags such a change after the fact. This PreToolUse hook on the
file-editing tools stops it before it lands: an edit to an existing file of
that kind is refused with exit 2, and the reason tells the agent to report
the need instead.

Protected, when the file already exists (creating one, as a scaffold does,
passes): lint, format, type, test-runner, coverage, and pre-commit
configuration, the instance's `.claude/settings.json` and `.claude/hooks/`,
and the inputs under `tests/fixtures/real/`. CI workflows and
`runs/_product-check.json` are not protected here, because the DevOps agent
and the implementing units edit them as part of their work, and the review
package tags every change to them for a disposition.

A change the story really needs is a ruling. The harness records it and lists
the path with its reason in `runs/_config-unlock.json`:

    {"paths": [{"path": "tsconfig.json", "reason": "ADR-004 adds a path alias"}]}

That file is itself refused to the editing tools, so an agent cannot unlock
its own edit. Registered in templates/project-settings.json behind a
file-exists guard. A malformed payload or any internal error passes, because
a hook that fails closed on its own bug would stop every edit.
"""

import json
import os
import re
import sys

UNLOCK_REL = "runs/_config-unlock.json"
PROTECTED = re.compile(
    r"(^|/)(tsconfig[^/]*\.json|\.eslintrc[^/]*|eslint\.config\.[^/]+|\.prettierrc[^/]*|prettier\.config\.[^/]+"
    r"|biome\.jsonc?|\.golangci\.ya?ml|ruff\.toml|\.flake8|mypy\.ini|\.pylintrc|\.pre-commit-config\.ya?ml"
    r"|(jest|vitest|playwright)\.config\.[^/]+|\.nycrc[^/]*|\.c8rc[^/]*|codecov\.ya?ml|lefthook\.ya?ml"
    r"|\.gts\.[^/]+)$"
    r"|(^|/)\.husky/|^\.claude/settings\.json$|^\.claude/hooks/|^tests/fixtures/real/")
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def unlocked(project, rel):
    try:
        with open(os.path.join(project, UNLOCK_REL)) as fh:
            entries = json.load(fh).get("paths", [])
    except (OSError, ValueError, AttributeError):
        return False
    return any(isinstance(e, dict) and e.get("path") == rel and str(e.get("reason", "")).strip()
               for e in entries)


def decide(project, file_path):
    """Return the refusal message, or None when the edit passes."""
    if not file_path:
        return None
    absolute = os.path.normpath(os.path.join(project, file_path))
    rel = os.path.relpath(absolute, project).replace(os.sep, "/")
    if rel.startswith("../"):
        return None
    if rel == UNLOCK_REL:
        return ("protect-check-config: runs/_config-unlock.json records the harness's rulings and is not "
                "edited by an agent. Report the change you need as a concern in your unit report.")
    if not PROTECTED.search(rel) or not os.path.exists(absolute) or unlocked(project, rel):
        return None
    return (f"protect-check-config: {rel} sets the bar a check measures against, and editing it can turn a "
            "failing check green without fixing anything. Fix the code instead. If the story really needs "
            "this change, stop and report it as a concern naming the file and the reason. The harness "
            f"records a ruling and unlocks the path in {UNLOCK_REL}.")


def main():
    try:
        payload = json.load(sys.stdin)
        if payload.get("tool_name") not in EDIT_TOOLS:
            return 0
        tool_input = payload.get("tool_input") or {}
        project = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
        message = decide(project, tool_input.get("file_path") or tool_input.get("notebook_path"))
    except Exception:  # noqa: BLE001  never block an edit on the hook's own failure
        return 0
    if message:
        sys.stderr.write(message + "\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
