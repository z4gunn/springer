"""Unit worktrees, one per in-flight unit under ~/.springer/worktrees/<project>/.

A removal git refuses is logged and left for the human, never forced.
"""

DOCS_INDEX = "docs/README.md"

import subprocess
import sys
from pathlib import Path


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


class Worktrees:
    def __init__(self, home, project_slug, project_path):
        self.root = Path(home) / "worktrees" / project_slug
        self.project = Path(project_path)

    def path(self, unit_id):
        return self.root / unit_id

    def ensure_venv(self):
        """schemas/validate.py looks for a .venv in the repo root or its parent, and a
        worktree's parent is this folder, so one venv with jsonschema serves every unit
        of the project. None when ready, else why it could not be made."""
        python = self.root / ".venv" / "bin" / "python"
        if python.exists() and subprocess.run([str(python), "-c", "import jsonschema"],
                                              capture_output=True).returncode == 0:
            return None
        self.root.mkdir(parents=True, exist_ok=True)
        for step in ([sys.executable, "-m", "venv", str(self.root / ".venv")],
                     [str(python), "-m", "pip", "install", "--quiet", "jsonschema"]):
            done = subprocess.run(step, capture_output=True, text=True, timeout=600)
            if done.returncode:
                return (done.stderr or done.stdout).strip()[-300:]
        return None

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
        message = f"chore: integrate {branch}"
        # The harness authors this commit, as it does the brief and profile commits, so
        # a machine with no git identity configured can still integrate.
        merge = ("-c", "user.name=Springer", "-c", "user.email=springer@local", "merge", "--no-edit", "--no-ff",
                 "-m", message, branch)
        done = _git(self.project, *merge)
        if done.returncode and self._clear_identical_copies(branch, done.stderr):
            done = _git(self.project, *merge)
        if done.returncode and self._resolve_docs_index():
            done = _git(self.project, "-c", "user.name=Springer", "-c", "user.email=springer@local",
                        "commit", "--no-edit", "--quiet")
        if done.returncode:
            _git(self.project, "merge", "--abort")
            return done.stderr.strip() or done.stdout.strip() or "git merge failed"
        return None

    def _resolve_docs_index(self):
        """Parallel units each rebuild the docs index from what their branch has, so two
        of them collide on it. The index only ever gains links, so the two sides merge
        by heading. True when that was the only conflict and it is now resolved."""
        conflicted = _git(self.project, "diff", "--name-only", "--diff-filter=U").stdout.split()
        if conflicted != [DOCS_INDEX]:
            return False
        ours, theirs = (_git(self.project, "show", f":{stage}:{DOCS_INDEX}") for stage in (2, 3))
        if ours.returncode or theirs.returncode:
            return False
        (self.project / DOCS_INDEX).write_text(merge_index(ours.stdout, theirs.stdout))
        return _git(self.project, "add", DOCS_INDEX).returncode == 0

    def _clear_identical_copies(self, branch, error):
        """git refuses a merge that would overwrite untracked files. A session that
        wrote the run store and also committed a copy leaves exactly that, and when
        each file is byte for byte the branch's copy, removing it loses nothing.
        Returns True when it cleared every blocking file."""
        if "untracked working tree files would be overwritten" not in error:
            return False
        paths = [line.strip() for line in error.splitlines() if line.startswith(("\t", "        "))]
        if not paths:
            return False
        for rel in paths:
            ours = (self.project / rel)
            theirs = subprocess.run(["git", "-C", str(self.project), "show", f"{branch}:{rel}"], capture_output=True)
            if theirs.returncode or not ours.is_file() or ours.read_bytes() != theirs.stdout:
                return False
        for rel in paths:
            (self.project / rel).unlink()
        return True

    def release(self, unit_id):
        """Returns None on success, or git's reason for refusing."""
        path = self.path(unit_id)
        if not path.exists():
            return None
        done = _git(self.project, "worktree", "remove", str(path))
        return done.stderr.strip() or "git refused" if done.returncode else None

    def claimed(self):
        return sorted(p.name for p in self.root.iterdir() if p.is_dir()) if self.root.is_dir() else []


def merge_index(ours, theirs):
    """Both versions of a Markdown index, merged: every section either side has, in
    the order first seen, each with the union of its lines and no line twice."""
    order, sections = [], {}
    for text in (ours, theirs):
        heading = ""
        for line in text.splitlines():
            if line.startswith("#"):
                heading = line
            if heading not in sections:
                order.append(heading)
                sections[heading] = []
            if line == heading or (line.strip() and line in sections[heading]):
                continue
            sections[heading].append(line)
    out = []
    for heading in order:
        body = sections[heading]
        while body and not body[-1].strip():
            body.pop()
        while body and not body[0].strip():
            body.pop(0)
        if out:
            out.append("")
        if heading:
            out.extend([heading, ""] if body else [heading])
        out.extend(body)
    return "\n".join(out) + "\n"
