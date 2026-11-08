"""Archiving and pruning a project's old runs.

Archive hides a finished run from the runs list and deletes nothing. Prune removes an
archived run's folder: the files git tracks leave in one change (a pull request on a
GitHub project, a commit on a local one), except a file another part of the repository
cites by path, and the working state git ignores moves to the daemon's home, so nothing
is lost that cannot be put back.
"""

import shutil
import subprocess
from pathlib import Path

from .errors import IllegalTransition, NotFound

IDENTITY = ["-c", "user.name=Springer", "-c", "user.email=springer@local"]


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def run_folder(path, run_id):
    folder = Path(path) / "runs" / run_id
    if run_id.startswith(("_", ".")) or "/" in run_id or not folder.is_dir():
        raise NotFound(f"no run folder runs/{run_id}")
    return folder


def plan(path, run_id):
    """(remove, keep): the tracked files of the run, split by whether a tracked file
    outside the run names them by path. A file a later run or a doc cites stays."""
    prefix = f"runs/{run_id}/"
    tracked = [f for f in _git(path, "ls-files", "-z", "--", prefix).stdout.split("\0") if f]
    citing = [f for f in _git(path, "grep", "-l", "-z", "-F", prefix, "--", ".", f":!{prefix}").stdout.split("\0") if f]
    text = "\n".join((Path(path) / f).read_text(errors="replace") for f in citing if (Path(path) / f).is_file())
    keep = [f for f in tracked if f in text]
    return [f for f in tracked if f not in keep], keep


def move_ignored(path, run_id, tracked, target):
    """A run's untracked files, see move_untracked. Zero when git rm took the last file,
    and the folder with it."""
    return move_untracked(path, Path(path) / "runs" / run_id, tracked, target)


def tracked_under(path, prefix):
    """The files git tracks under prefix, as repository-relative paths."""
    out = _git(path, "ls-files", "-z", "--", prefix).stdout
    return [f for f in out.split("\0") if f]


def move_untracked(path, folder, tracked, target):
    """Move every file under folder that git does not track to target, keeping its
    place under the folder, and drop the directories that empties. Returns how many
    moved."""
    folder, tracked = Path(folder), set(tracked)
    if not folder.is_dir():
        return 0
    moved = 0
    for file in sorted(p for p in folder.rglob("*") if p.is_file() or p.is_symlink()):
        rel = file.relative_to(path).as_posix()
        if rel in tracked:
            continue
        destination = Path(target) / file.relative_to(folder)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(file), str(destination))
        moved += 1
    for directory in sorted((p for p in folder.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(directory.iterdir()):
            directory.rmdir()
    if folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()
    return moved


def default_branch(path):
    return _git(path, "symbolic-ref", "--short", "HEAD").stdout.strip() or "main"


def commit_removal(path, remove, message):
    """A local project: the removal is one commit on the checkout's branch."""
    if not remove:
        return None
    done = _git(path, "rm", "-q", "--", *remove)
    if done.returncode:
        raise IllegalTransition(f"git rm failed: {done.stderr.strip()[-300:]}")
    done = _git(path, *IDENTITY, "commit", "-q", "-m", message, "--", *remove)
    if done.returncode:
        raise IllegalTransition(f"git commit failed: {(done.stderr or done.stdout).strip()[-300:]}")
    return _git(path, "rev-parse", "HEAD").stdout.strip()


def branch_removal(path, remove, branch, message, scratch):
    """A GitHub project: the removal is a branch cut from origin's default branch in a
    scratch worktree, pushed, so the person's checkout is never touched."""
    base = default_branch(path)
    if _git(path, "fetch", "--quiet", "origin", base).returncode:
        raise IllegalTransition(f"could not fetch {base} from origin")
    _git(path, "worktree", "remove", "--force", str(scratch))
    if _git(path, "worktree", "add", "--quiet", "--detach", str(scratch), f"origin/{base}").returncode:
        raise IllegalTransition("could not make a scratch worktree")
    try:
        present = [f for f in remove if (Path(scratch) / f).exists()]
        if not present:
            return None, base
        for args in (["rm", "-q", "--", *present], [*IDENTITY, "commit", "-q", "-m", message],
                     ["push", "--quiet", "origin", f"HEAD:refs/heads/{branch}"]):
            done = _git(scratch, *args)
            if done.returncode:
                raise IllegalTransition(f"git {args[0] if args[0] != '-c' else 'commit'} failed: "
                                        f"{(done.stderr or done.stdout).strip()[-300:]}")
        return branch, base
    finally:
        _git(path, "worktree", "remove", "--force", str(scratch))
