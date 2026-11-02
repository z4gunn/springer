"""Unit worktrees, one per in-flight unit under ~/.springer/worktrees/<project>/.

A removal git refuses is logged and left for the human, never forced.
"""

import subprocess
from pathlib import Path


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


class Worktrees:
    def __init__(self, home, project_slug, project_path):
        self.root = Path(home) / "worktrees" / project_slug
        self.project = Path(project_path)

    def path(self, unit_id):
        return self.root / unit_id

    def default_branch(self):
        return _git(self.project, "symbolic-ref", "--short", "HEAD").stdout.strip() or "main"

    def _intact(self, path):
        return path.is_dir() and _git(path, "rev-parse", "--is-inside-work-tree").returncode == 0

    def claim(self, unit_id, base):
        """Reuse the unit's worktree when the branch is intact, otherwise rebuild it."""
        path, branch = self.path(unit_id), f"unit/{unit_id}"
        if self._intact(path):
            # A retry reuses the worktree. When the unit has committed nothing yet, it
            # moves up to the base, so it reads what landed since (e.g. the brief).
            # Fast-forward only, so no work is ever lost.
            _git(path, "merge", "--ff-only", "--quiet", base)
            return path, branch
        _git(self.project, "worktree", "prune")
        path.parent.mkdir(parents=True, exist_ok=True)
        if _git(self.project, "rev-parse", "--verify", f"refs/heads/{branch}").returncode == 0:
            done = _git(self.project, "worktree", "add", str(path), branch)
        else:
            done = _git(self.project, "worktree", "add", "-b", branch, str(path), base)
        if done.returncode:
            raise OSError(f"git worktree add failed for {unit_id}: {done.stderr.strip()}")
        return path, branch

    def integrate(self, unit_id):
        """Merge the unit's branch into the default branch in the main checkout.
        Returns None, "nothing to integrate", or why it was refused. A checkout with
        a person's uncommitted work, or on another branch, is never touched."""
        branch, base = f"unit/{unit_id}", self.default_branch()
        ahead = _git(self.project, "rev-list", "--count", f"{base}..{branch}").stdout.strip()
        if not ahead or ahead == "0":
            return "nothing to integrate"
        dirty = [line for line in _git(self.project, "status", "--porcelain").stdout.splitlines()
                 if not line[3:].startswith(("runs/", ".worktrees/"))]
        if dirty:
            return "the main checkout has uncommitted changes"
        done = _git(self.project, "merge", "--no-edit", "--no-ff", "-m", f"chore: integrate {branch}", branch)
        if done.returncode:
            _git(self.project, "merge", "--abort")
            return done.stderr.strip() or done.stdout.strip() or "git merge failed"
        return None

    def release(self, unit_id):
        """Returns None on success, or git's reason for refusing."""
        path = self.path(unit_id)
        if not path.exists():
            return None
        done = _git(self.project, "worktree", "remove", str(path))
        return done.stderr.strip() or "git refused" if done.returncode else None

    def claimed(self):
        return sorted(p.name for p in self.root.iterdir() if p.is_dir()) if self.root.is_dir() else []
