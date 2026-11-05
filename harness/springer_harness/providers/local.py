"""The local source host, the default. A unit's branch is a numbered change the harness
opens itself, reviews from the local diff, and merges into the default branch with a
merge commit made in a scratch worktree, so the person's checkout never has to be clean
or on that branch. Nothing goes to a hosted service. When the project has an origin, the
default branch is pushed after each merge."""

import subprocess
import sys
import threading
from pathlib import Path

from ..common import read_json, write_json
from ..merge import merge_off_checkout


def _git(cwd, *args, timeout=120):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=timeout)


class LocalMergeError(RuntimeError):
    pass


class LocalSourceHost:
    name = "local"
    noun = "change"
    squashes = False

    def __init__(self, project_path_of, store_dir):
        self.project_path_of = project_path_of
        self.store_dir = Path(store_dir)
        self._lock = threading.Lock()

    def _path(self, project):
        return self.store_dir / f"{project}.json"

    def _load(self, project):
        return read_json(self._path(project), {"next": 1, "changes": {}})

    def _change(self, project, number):
        change = self._load(project)["changes"].get(str(number))
        if change is None:
            raise LocalMergeError(f"no local change {number} in {project}")
        return change

    def _update(self, project, number, **fields):
        with self._lock:
            data = self._load(project)
            data["changes"][str(number)] = {**data["changes"][str(number)], **fields}
            self.store_dir.mkdir(parents=True, exist_ok=True)
            write_json(self._path(project), data)

    def open(self, project, branch, base, title=""):
        """Record a change for a branch and return its number."""
        with self._lock:
            data = self._load(project)
            for number, change in data["changes"].items():
                if change["branch"] == branch and change["state"] == "open":
                    return int(number)
            number = data["next"]
            data["changes"][str(number)] = {"branch": branch, "base": base, "title": title, "state": "open"}
            data["next"] = number + 1
            self.store_dir.mkdir(parents=True, exist_ok=True)
            write_json(self._path(project), data)
            return number

    def pr_state(self, project, number):
        try:
            return self._change(project, number)["state"]
        except LocalMergeError:
            return "closed"

    def mergeable(self, project, number):
        change = self._change(project, number)
        probe = _git(self.project_path_of(project), "merge-tree", "--write-tree", change["base"], change["branch"])
        if probe.returncode == 0:
            return "mergeable"
        return "conflicting" if probe.returncode == 1 else "unknown"

    def merge(self, project, number):
        """A merge commit on the base, made off the person's checkout. Their uncommitted
        work is kept, and the merge is refused only when it would overwrite it."""
        change = self._change(project, number)
        message = f"Merge change {number}: {change['title'] or change['branch']}"
        sha, problem = merge_off_checkout(self.project_path_of(project), change["branch"], change["base"], message,
                                          self.store_dir / "scratch")
        if problem:
            raise LocalMergeError(problem)
        self._update(project, number, state="merged", sha=sha)
        problem = self.publish(project, change["base"])
        if problem:
            self._update(project, number, push_error=problem)
        return sha

    def retarget(self, project, number, base):
        self._update(project, number, base=base)

    def diff(self, project, number):
        change = self._change(project, number)
        return _git(self.project_path_of(project), "diff", f"{change['base']}...{change['branch']}").stdout

    def sync(self, project):
        """The merge moved the local default branch, so there is nothing to pull."""

    def publish(self, project, branch):
        """Push the branch when the project has an origin. A failed push leaves the
        merge in place and says why on stderr, because the work is already on the base."""
        path = self.project_path_of(project)
        if _git(path, "remote", "get-url", "origin").returncode:
            return None
        done = _git(path, "push", "--quiet", "origin", branch, timeout=300)
        if done.returncode:
            sys.stderr.write(f"could not push {branch} for {project}: {done.stderr.strip()[-300:]}\n")
            return done.stderr.strip()[-300:] or "git push failed"
        return None
