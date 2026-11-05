"""Merges that never need the person's checkout to be clean or on the default branch.

The merge commit is made in a detached scratch worktree the harness owns, so a person's
uncommitted edits, or a checkout on another branch, never refuse it. The default branch
then moves to the new commit. When the person's checkout has that branch out, it is
fast-forwarded there, where git keeps their uncommitted work and refuses only when the
merge would overwrite it. Otherwise the ref moves on its own, which touches no files.
"""

import subprocess
from pathlib import Path

IDENTITY = ("-c", "user.name=Springer", "-c", "user.email=springer@local")


def _git(cwd, *args, timeout=120):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=timeout)


def _said(done):
    lines = [line for line in (done.stdout + done.stderr).splitlines() if line and not line.startswith("hint:")]
    return " ".join(lines)[-300:]


def merge_off_checkout(project, branch, base, message, scratch_root, resolve=None, clear=None):
    """Merge branch into base with a merge commit. Returns (sha, None) or (None, why).
    resolve(scratch) may settle a conflict in the scratch tree and return True. clear(error)
    may remove untracked files in the person's checkout that block the fast-forward, and
    returns True when it removed all of them."""
    project, scratch_root = Path(project), Path(scratch_root)
    old = _git(project, "rev-parse", "--verify", f"refs/heads/{base}").stdout.strip()
    if not old:
        return None, f"there is no branch {base}"
    scratch = scratch_root / f"_merge-{branch.replace('/', '-')}"
    _git(project, "worktree", "remove", "--force", str(scratch))
    scratch_root.mkdir(parents=True, exist_ok=True)
    if _git(project, "worktree", "add", "--detach", str(scratch), old).returncode:
        return None, "could not make a scratch worktree"
    try:
        done = _git(scratch, *IDENTITY, "merge", "--no-ff", "--no-edit", "-m", message, branch)
        if done.returncode and resolve and resolve(scratch):
            done = _git(scratch, *IDENTITY, "commit", "--no-edit", "--quiet")
        if done.returncode:
            _git(scratch, "merge", "--abort")
            return None, _said(done) or "git merge failed"
        new = _git(scratch, "rev-parse", "HEAD").stdout.strip()
    finally:
        _git(project, "worktree", "remove", "--force", str(scratch))
    problem = advance(project, base, old, new, clear)
    return (None, problem) if problem else (new, None)


def advance(project, base, old, new, clear=None):
    """Move base from old to new. Returns None, or why it did not move."""
    head = _git(project, "symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip()
    if head != base:
        moved = _git(project, "update-ref", f"refs/heads/{base}", new, old)
        return None if moved.returncode == 0 else f"{base} moved during the merge"
    if _git(project, "rev-parse", "HEAD").stdout.strip() != old:
        return f"{base} moved during the merge"
    done = _git(project, "merge", "--ff-only", "--quiet", new)
    if done.returncode and clear and clear(done.stderr):
        done = _git(project, "merge", "--ff-only", "--quiet", new)
    if done.returncode:
        return f"the merge would overwrite uncommitted work in the project checkout: {_said(done)}"
    return None
