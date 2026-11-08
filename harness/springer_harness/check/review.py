"""The review a code PR gets before any merge, cut and checked by scripts.

The daemon cuts the review package, so the reviewer grades a fixed range with the
gate-integrity tags first, and checks afterwards that the code review gave every tag a
disposition. Both are the runtime's review-package.py, run in the project.
"""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(".claude/skills/spgr-run-harness/scripts/review-package.py")
REVIEWER = "spgr-agent-code-reviewer"
MAX_REVIEWS = 2  # one review and one re-review, then a person decides

BRIEF = """Review PR {number} for {unit_id}, branch {branch} into {base}.

What the unit was asked for: {expected}

The review package is {package}. Read it instead of the raw diff, gate-integrity tags first,
and give every tag a disposition with a reason in the code review's gate_tags list.

What the builder reported:
{report}

Your working directory is the PR head. Read and run what you need. Do not commit, push,
or edit any file outside the run store.

Write the code-review artifact to {artifacts}/. In result.json set "outcome": "review",
"verdict": "approve" or "request_changes", "findings" as a list of {{"severity", "file",
"detail"}}, and "code_review" as the artifact's path. Request changes only for a P0 or P1
finding. List every other finding, and it becomes a follow-up."""


def _python(project):
    venv = Path(project) / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def cut_package(project, base, head, out, touch_paths=()):
    """None when the package was written, else why not."""
    script = Path(project) / SCRIPT
    if not script.exists():
        return f"{SCRIPT} is not in the project"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    command = [_python(project), str(script), base, head, "--out", str(out), "--repo", str(project)]
    if touch_paths:
        command += ["--touch-paths", *touch_paths]
    done = subprocess.run(command, cwd=str(project), capture_output=True, text=True, timeout=300)
    return None if done.returncode == 0 else (done.stderr or done.stdout).strip()[-400:] or "review-package.py failed"


def dispositions(project, tags, code_review):
    """None when every tag has a disposition, else what the script said. No tags file
    means the package had nothing to tag."""
    if not Path(tags).exists():
        return None
    if not code_review or not Path(code_review).exists():
        return "the review named no code-review artifact, so its tag dispositions cannot be checked"
    done = subprocess.run([_python(project), str(Path(project) / SCRIPT), "dispositions", str(tags), str(code_review)],
                          cwd=str(project), capture_output=True, text=True, timeout=120)
    return None if done.returncode == 0 else (done.stdout or done.stderr).strip()[-400:] or "a tag has no disposition"
