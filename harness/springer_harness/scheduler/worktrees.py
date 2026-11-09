"""Unit worktrees, one per in-flight unit under ~/.springer/worktrees/<project>/.

A removal git refuses is logged and left for the human, never forced.
"""

DOCS_INDEX = "docs/README.md"
RULINGS = "runs/_config-unlock.json"
# What an artifact unit may land with no PR: the run store, rendered docs, and design
# variants. Anything else is code, and code reaches the default branch only through a gate.
ARTIFACT_PATHS = ("runs/", "docs/", "design/")

import shutil
import subprocess
import sys
from pathlib import Path

from ..merge import merge_off_checkout


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


class Worktrees:
    def __init__(self, home, project_slug, project_path, run_id=None):
        # Unit ids restart at U-0001 in every run, so a run's branches and worktrees are
        # named for the run. Without it a later run's U-0001 could pick up the branch an
        # earlier run's U-0001 left behind.
        self.base = Path(home) / "worktrees" / project_slug
        self.root = self.base / run_id if run_id else self.base
        self.project = Path(project_path)
        self.run_id = run_id

    def path(self, unit_id):
        return self.root / unit_id

    def branch(self, unit_id):
        return f"unit/{self.run_id}/{unit_id}" if self.run_id else f"unit/{unit_id}"

    def ensure_venv(self):
        """schemas/validate.py looks for a .venv in the repo root or its parent, and a
        worktree's parent is this folder, so one venv with jsonschema serves every unit
        of the project. None when ready, else why it could not be made."""
        python = self.base / ".venv" / "bin" / "python"
        if not (python.exists() and subprocess.run([str(python), "-c", "import jsonschema"],
                                                   capture_output=True).returncode == 0):
            self.base.mkdir(parents=True, exist_ok=True)
            for step in ([sys.executable, "-m", "venv", str(self.base / ".venv")],
                         [str(python), "-m", "pip", "install", "--quiet", "jsonschema"]):
                done = subprocess.run(step, capture_output=True, text=True, timeout=600)
                if done.returncode:
                    return (done.stderr or done.stdout).strip()[-300:]
        if self.root != self.base and not (self.root / ".venv").exists():
            # A run's worktrees sit one folder deeper, so the run folder links the one venv.
            self.root.mkdir(parents=True, exist_ok=True)
            (self.root / ".venv").symlink_to(self.base / ".venv")
        return None

    def default_branch(self):
        return _git(self.project, "symbolic-ref", "--short", "HEAD").stdout.strip() or "main"

    def _intact(self, path):
        return path.is_dir() and _git(path, "rev-parse", "--is-inside-work-tree").returncode == 0

    def claim(self, unit_id, base):
        """Reuse the unit's worktree when the branch is intact, otherwise rebuild it."""
        path, branch = self.path(unit_id), self.branch(unit_id)
        if self._intact(path):
            # A retry reuses the worktree. When the unit has committed nothing yet, it
            # moves up to the base, so it reads what landed since (e.g. the brief).
            # Fast-forward only, so no work is ever lost.
            _git(path, "merge", "--ff-only", "--quiet", base)
            self._carry_rulings(path)
            self._provide_node_modules(path)
            return path, branch
        _git(self.project, "worktree", "prune")
        path.parent.mkdir(parents=True, exist_ok=True)
        if _git(self.project, "rev-parse", "--verify", f"refs/heads/{branch}").returncode == 0:
            done = _git(self.project, "worktree", "add", str(path), branch)
        else:
            done = _git(self.project, "worktree", "add", "-b", branch, str(path), base)
        if done.returncode:
            raise OSError(f"git worktree add failed for {unit_id}: {done.stderr.strip()}")
        self._carry_rulings(path)
        self._provide_node_modules(path)
        return path, branch

    def _provide_node_modules(self, path):
        """git carries no node_modules, so a fresh worktree cannot build, test, or run a
        product check, and each session either installed them or failed on it. When the
        worktree's lockfile is the project's and the project has them installed, they
        are cloned in (a copy-on-write clone on APFS, a few seconds for hundreds of MB).
        A different lockfile, or a failed clone, leaves the install to the session.
        Returns True when the worktree has them."""
        target, source = Path(path) / "node_modules", self.project / "node_modules"
        if target.exists():
            return True
        lock, project_lock = Path(path) / "package-lock.json", self.project / "package-lock.json"
        if not (source.is_dir() and lock.is_file() and project_lock.is_file()) \
                or lock.read_bytes() != project_lock.read_bytes():
            return False
        clone = ["cp", "-cR"] if sys.platform == "darwin" else ["cp", "-R", "--reflink=auto"]
        done = subprocess.run([*clone, str(source), str(target)], capture_output=True, text=True)
        if done.returncode:
            shutil.rmtree(target, ignore_errors=True)
            sys.stderr.write(f"could not clone node_modules into {path}: {done.stderr.strip()[:300]}\n")
            return False
        return True

    def scratch_at(self, sha):
        """A detached worktree at sha with the project's node_modules, for running a
        gating command on a unit's base. None when git refuses it."""
        path = self.root / f"_base-{sha[:12]}"
        if not self._intact(path):
            _git(self.project, "worktree", "prune")
            path.parent.mkdir(parents=True, exist_ok=True)
            if _git(self.project, "worktree", "add", "--quiet", "--detach", str(path), sha).returncode:
                return None
        self._provide_node_modules(path)
        return path

    def drop_scratch(self, path):
        """A scratch tree holds only the base's code and what a command built in it."""
        _git(self.project, "worktree", "remove", "--force", str(path))
        shutil.rmtree(path, ignore_errors=True)

    def _carry_rulings(self, path):
        """The config-unlock rulings live in the project's run store, which git does not
        carry, and the protection hook reads them from the session's own tree. Without
        this copy a ruling the human made reaches no unit. A withdrawn ruling is removed."""
        source, target = self.project / RULINGS, Path(path) / RULINGS
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        elif target.exists():
            target.unlink()

    def code_paths(self, unit_id):
        """The paths the unit's branch changes against the default branch that are not
        artifacts. A branch stacked on an unmerged parent carries the parent's code too,
        so this is not empty for it either."""
        changed = _git(self.project, "diff", "--name-only", f"{self.default_branch()}...{self.branch(unit_id)}").stdout
        return [p for p in changed.splitlines() if p and not p.startswith(ARTIFACT_PATHS)]

    def own_commits(self, unit_id, base):
        """The commits the unit's branch has past the base it was cut from. A unit stacked
        on an open change to read it, such as an audit, has none of its own."""
        count = _git(self.project, "rev-list", "--count", f"{base}..{self.branch(unit_id)}").stdout.strip()
        return int(count) if count.isdigit() else 0

    def integrate(self, unit_id):
        """Merge the unit's branch into the default branch, off the person's checkout.
        Returns None, "nothing to integrate", or why it was refused. Their uncommitted
        work is kept, and the merge is refused only when it would overwrite it."""
        branch, base = self.branch(unit_id), self.default_branch()
        ahead = _git(self.project, "rev-list", "--count", f"{base}..{branch}").stdout.strip()
        if not ahead or ahead == "0":
            return "nothing to integrate"
        _, problem = merge_off_checkout(self.project, branch, base, f"chore: integrate {branch}", self.root,
                                        resolve=self._resolve_docs_index,
                                        clear=lambda error: self._clear_identical_copies(branch, error))
        return problem

    def _resolve_docs_index(self, tree):
        """Parallel units each rebuild the docs index from what their branch has, so two
        of them collide on it. The index only ever gains links, so the two sides merge
        by heading. True when that was the only conflict and it is now resolved."""
        conflicted = _git(tree, "diff", "--name-only", "--diff-filter=U").stdout.split()
        if conflicted != [DOCS_INDEX]:
            return False
        ours, theirs = (_git(tree, "show", f":{stage}:{DOCS_INDEX}") for stage in (2, 3))
        if ours.returncode or theirs.returncode:
            return False
        (Path(tree) / DOCS_INDEX).write_text(merge_index(ours.stdout, theirs.stdout))
        return _git(tree, "add", DOCS_INDEX).returncode == 0

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

    def restack(self, branch, upstream, onto):
        """Replay the commits a stacked branch added on top of upstream onto the base,
        after upstream was squash-merged there and its own commits would otherwise
        conflict with the squash. The rebase runs in a detached scratch worktree, so a
        unit worktree is never touched, and the push is leased to the old head, so work
        pushed since is never overwritten. Returns None, or why it did nothing."""
        old = _git(self.project, "rev-parse", "--verify", f"refs/heads/{branch}").stdout.strip()
        tip = _git(self.project, "rev-parse", "--verify", f"refs/heads/{upstream}").stdout.strip()
        if not old or not tip:
            return "a branch is missing"
        if _git(self.project, "merge-base", "--is-ancestor", tip, old).returncode:
            return "nothing to restack"
        remote = _git(self.project, "remote", "get-url", "origin").returncode == 0
        if remote:
            _git(self.project, "fetch", "--quiet", "origin", onto)
        target = f"origin/{onto}" if remote else onto
        scratch = self.root / f"_restack-{branch.replace('/', '-')}"
        _git(self.project, "worktree", "remove", "--force", str(scratch))
        self.root.mkdir(parents=True, exist_ok=True)
        if _git(self.project, "worktree", "add", "--detach", str(scratch), old).returncode:
            return "could not make a scratch worktree"
        try:
            done = _git(scratch, "-c", "user.name=Springer", "-c", "user.email=springer@local",
                        "rebase", "--onto", target, tip)
            if done.returncode:
                _git(scratch, "rebase", "--abort")
                said = [line for line in (done.stdout + done.stderr).splitlines() if line and not line.startswith("hint:")]
                return " ".join(said)[-300:] or "git rebase failed"
            new = _git(scratch, "rev-parse", "HEAD").stdout.strip()
            if _git(self.project, "update-ref", f"refs/heads/{branch}", new, old).returncode:
                return "the branch moved during the restack"
            if remote:
                pushed = _git(self.project, "push", "--quiet", f"--force-with-lease={branch}:{old}", "origin", branch)
                if pushed.returncode:
                    _git(self.project, "update-ref", f"refs/heads/{branch}", old, new)
                    return pushed.stderr.strip()[-300:] or "git push failed"
            return None
        finally:
            _git(self.project, "worktree", "remove", "--force", str(scratch))

    def release(self, unit_id):
        """Returns None on success, or git's reason for refusing. The rulings copy the
        harness carried in is its own, so it never keeps a worktree. Anything else left
        uncommitted is a session's, and git keeps the worktree for a person."""
        path = self.path(unit_id)
        if not path.exists():
            return None
        loose = [line[3:] for line in _git(path, "status", "--porcelain", "-uall").stdout.splitlines()]
        force = ["--force"] if loose and all(p == RULINGS for p in loose) else []
        done = _git(self.project, "worktree", "remove", *force, str(path))
        return done.stderr.strip() or "git refused" if done.returncode else None

    def delete_branch(self, branch):
        """Delete a merged unit's branch here and on origin. Returns what was deleted."""
        deleted = []
        if _git(self.project, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}").returncode == 0:
            if _git(self.project, "branch", "-D", branch).returncode == 0:
                deleted.append(branch)
        if _git(self.project, "remote", "get-url", "origin").returncode == 0 and \
                _git(self.project, "ls-remote", "--exit-code", "--heads", "origin", branch).returncode == 0:
            if _git(self.project, "push", "--quiet", "origin", "--delete", branch).returncode == 0:
                deleted.append(f"origin/{branch}")
        return deleted

    def sync_default(self):
        """Fast-forward the checkout's default branch from origin, so a run never starts
        on a stale base. A checkout with changes outside the run store, or one that has
        diverged, is left alone and the reason returned."""
        if _git(self.project, "remote", "get-url", "origin").returncode:
            return None
        branch = self.default_branch()
        if _git(self.project, "fetch", "--quiet", "origin", branch).returncode:
            return f"could not fetch {branch} from origin"
        dirty = [l for l in _git(self.project, "status", "--porcelain").stdout.splitlines()
                 if not l[3:].startswith(("runs/", ".worktrees/"))]
        if dirty:
            return f"the checkout has uncommitted changes, so {branch} was not updated"
        done = _git(self.project, "merge", "--ff-only", "--quiet", f"origin/{branch}")
        return None if done.returncode == 0 else f"{branch} has diverged from origin, so it was not updated"

    def claimed(self):
        """Unit worktrees only. The shared .venv and a restack scratch tree live here too."""
        if not self.root.is_dir():
            return []
        return sorted(p.name for p in self.root.iterdir() if p.is_dir() and p.name.startswith("U-"))


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
