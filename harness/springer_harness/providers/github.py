"""The GitHub source host, through the gh CLI the person is logged into. The harness is
the only merger, so merge lives here, and after a merge the main checkout is moved
forward so the next worktree starts from what was merged."""

import json
import subprocess
from pathlib import Path


def _run(args, cwd, timeout=120):
    return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)


class GitHubError(RuntimeError):
    pass


class GitHubSourceHost:
    name = "github"

    def __init__(self, project_path_of):
        self.project_path_of = project_path_of

    def _gh(self, project, *args):
        done = _run(["gh", *args], self.project_path_of(project))
        if done.returncode:
            raise GitHubError(f"gh {' '.join(args[:3])} failed: {done.stderr.strip()[-400:]}")
        return done.stdout

    def pr_state(self, project, number):
        state = json.loads(self._gh(project, "pr", "view", str(number), "--json", "state"))["state"]
        return {"OPEN": "open", "MERGED": "merged", "CLOSED": "closed"}.get(state, "open")

    def merge(self, project, number):
        self._gh(project, "pr", "merge", str(number), "--squash")
        sha = json.loads(self._gh(project, "pr", "view", str(number), "--json", "mergeCommit"))["mergeCommit"]["oid"]
        self.sync(project)
        return sha

    def retarget(self, project, number, base):
        self._gh(project, "pr", "edit", str(number), "--base", base)

    def diff(self, project, number):
        return self._gh(project, "pr", "diff", str(number))

    def sync(self, project):
        """Fast-forward the main checkout's default branch, leaving a dirty one alone."""
        path = self.project_path_of(project)
        dirty = [l for l in _run(["git", "status", "--porcelain"], path).stdout.splitlines()
                 if not l[3:].startswith(("runs/", ".worktrees/"))]
        if not dirty:
            _run(["git", "pull", "--ff-only", "--quiet"], path)

    def publish(self, project, branch):
        """Push a branch the harness moved itself (e.g. an integrated artifact unit)."""
        path = self.project_path_of(project)
        if _run(["git", "remote", "get-url", "origin"], path).returncode == 0:
            _run(["git", "push", "--quiet", "origin", branch], path)

    def ensure_remote(self, project, private=True):
        """A project with no origin gets a GitHub repository of its own name. Returns
        the URL, or None when one was already there."""
        path = Path(self.project_path_of(project))
        if _run(["git", "remote", "get-url", "origin"], path).returncode == 0:
            return None
        done = _run(["gh", "repo", "create", path.name, "--private" if private else "--public", "--source", str(path),
                     "--remote", "origin", "--push"], path, timeout=300)
        if done.returncode:
            raise GitHubError(f"gh repo create failed: {done.stderr.strip()[-400:]}")
        return done.stdout.strip()
