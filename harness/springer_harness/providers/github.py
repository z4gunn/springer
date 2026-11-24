"""The GitHub source host, through the gh CLI the person is logged into. The harness is
the only merger, so merge lives here, and after a merge the main checkout is moved
forward so the next worktree starts from what was merged."""

import json
import re
import subprocess
from pathlib import Path


def _run(args, cwd, timeout=120):
    return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)


def _push_rewritten(path, branch):
    """A harness unit branch that a rebase or restack rewrote after it was pushed is
    rejected as non-fast-forward. Origin's tip is pushed over only when this branch
    once held it (it is in the branch's reflog), so the rewrite is this checkout's own
    and no commit someone else pushed is lost. The lease names that tip, so a push that
    lands in between still wins. None when the push does not qualify."""
    if not branch.startswith("unit/"):
        return None
    listed = _run(["git", "ls-remote", "origin", f"refs/heads/{branch}"], path)
    tip = (listed.stdout.split() or [""])[0]
    if listed.returncode or not tip:
        return None
    held = _run(["git", "reflog", "show", "--format=%H", f"refs/heads/{branch}"], path)
    if tip not in held.stdout.split():
        return None
    return _run(["git", "push", "--quiet", "-u", f"--force-with-lease={branch}:{tip}", "origin", branch], path)


RUNNER_FAULT = "the job failed with every step green"


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

    def open_pr(self, project, branch, base, title, body):
        """Open a pull request the daemon made itself (e.g. a run prune). Returns its URL."""
        return self._gh(project, "pr", "create", "--base", base, "--head", branch, "--title", title,
                        "--body", body).strip().splitlines()[-1]

    def push(self, project, branch):
        """Send a unit branch's commits to its pull request. A retry commits its fix
        without pushing, and CI and the reviewer read only what the host has."""
        path = self.project_path_of(project)
        pushed = _run(["git", "push", "--quiet", "-u", "origin", branch], path)
        if pushed.returncode:
            pushed = _push_rewritten(path, branch) or pushed
        if pushed.returncode:
            raise GitHubError(f"git push {branch} failed: {pushed.stderr.strip()[-400:]}")

    def open(self, project, branch, base, title=""):
        """Push a branch and return the number of its open PR, opening one when the
        session reported a PR outcome without opening it. A PR the branch already has
        is reused, so a retry never opens a second."""
        self.push(project, branch)
        found = json.loads(self._gh(project, "pr", "list", "--head", branch, "--state", "open",
                                    "--json", "number") or "[]")
        if found:
            return int(found[0]["number"])
        self._gh(project, "pr", "create", "--base", base, "--head", branch, "--title", title or branch,
                 "--body", f"Opened by the Springer harness for {branch}: the session reported a pull "
                           "request without opening one. The unit's result.md in the run store carries "
                           "what changed and why.")
        return int(json.loads(self._gh(project, "pr", "view", branch, "--json", "number"))["number"])

    def merge(self, project, number):
        self._gh(project, "pr", "merge", str(number), "--squash")
        sha = json.loads(self._gh(project, "pr", "view", str(number), "--json", "mergeCommit"))["mergeCommit"]["oid"]
        self.sync(project)
        return sha

    def mergeable(self, project, number):
        """conflicting, mergeable, or unknown while GitHub is still computing it."""
        try:
            value = json.loads(self._gh(project, "pr", "view", str(number), "--json", "mergeable"))["mergeable"]
        except (GitHubError, ValueError, KeyError):
            return "unknown"
        return {"CONFLICTING": "conflicting", "MERGEABLE": "mergeable"}.get(value, "unknown")

    def checks(self, project, number):
        """("pass" | "pending" | "fail", detail) over every check on the PR. A PR with
        no checks at all is pending, because a configured CI signal that never reports
        is not green."""
        done = _run(["gh", "pr", "checks", str(number), "--json", "name,bucket"], self.project_path_of(project))
        try:
            checks = json.loads(done.stdout or "[]")
        except ValueError:
            return "pending", (done.stderr or "gh pr checks returned nothing").strip()[-300:]
        if not checks:
            return "pending", "no checks have reported yet"
        failed = [c["name"] for c in checks if c.get("bucket") in ("fail", "cancel")]
        pending = any(c.get("bucket") == "pending" for c in checks)
        if failed and pending:
            # GitHub serves a failed run's log, and reruns it, only once the whole run
            # is over, so a failure read mid-run reached the builder with no log and
            # could not be told from a runner fault.
            return "pending", "failed: " + ", ".join(failed) + ", waiting for the other checks to finish"
        if failed:
            return "fail", "failed: " + ", ".join(failed)
        if pending:
            return "pending", "checks still running"
        return "pass", f"{len(checks)} check(s) green"

    def _failed_runs(self, project, number):
        done = _run(["gh", "pr", "checks", str(number), "--json", "bucket,link"], self.project_path_of(project))
        try:
            checks = json.loads(done.stdout or "[]")
        except ValueError:
            return []
        runs = []
        for check in checks:
            match = re.search(r"/actions/runs/(\d+)", check.get("link") or "")
            if check.get("bucket") in ("fail", "cancel") and match and match.group(1) not in runs:
                runs.append(match.group(1))
        return runs

    def failure_log(self, project, number, limit=3000):
        """The tail of each failed Actions run's failed steps, so a builder reads the error
        instead of a session spent finding it, and the engine can tell a runner that ran
        out of memory from a test that failed."""
        tails = []
        path = self.project_path_of(project)
        for run_id in self._failed_runs(project, number):
            tails += self._green_step_failures(path, run_id)
            done = _run(["gh", "run", "view", run_id, "--log-failed"], path)
            lines = [line.split("\t", 2)[-1] for line in (done.stdout or "").splitlines() if line.strip()]
            tails.append("\n".join(lines)[-limit:])
        return "\n".join(t for t in tails if t)[-limit * 2:]

    def _green_step_failures(self, path, run_id):
        """A job that failed while every step passed failed on the runner, not in the
        change (a self-hosted runner did this on a PR whose build was green)."""
        done = _run(["gh", "run", "view", run_id, "--json", "jobs"], path)
        try:
            jobs = json.loads(done.stdout or "{}").get("jobs") or []
        except ValueError:
            return []
        return [f"{job.get('name')}: {RUNNER_FAULT}" for job in jobs
                if job.get("conclusion") == "failure"
                and not any(step.get("conclusion") == "failure" for step in job.get("steps") or [])]

    def rerun(self, project, number):
        """Rerun the failed jobs of the PR's failed Actions runs. Returns the runs rerun."""
        runs = self._failed_runs(project, number)
        for run_id in runs:
            _run(["gh", "run", "rerun", run_id, "--failed"], self.project_path_of(project))
        return runs

    def label(self, project, number, name):
        """Add a label to a PR, creating it in the repository when it is missing."""
        path = self.project_path_of(project)
        _run(["gh", "label", "create", name, "--color", "0e8a16", "--force",
              "--description", "Springer: this PR waits on hosted CI"], path)
        self._gh(project, "pr", "edit", str(number), "--add-label", name)

    def retarget(self, project, number, base):
        self._gh(project, "pr", "edit", str(number), "--base", base)

    def diff(self, project, number):
        return self._gh(project, "pr", "diff", str(number))

    def sync(self, project):
        """Bring the main checkout's default branch up to origin after a merge, replaying
        the daemon's own unpushed records, and leaving a dirty one alone."""
        from ..scheduler.worktrees import catch_up
        return catch_up(self.project_path_of(project))

    def publish(self, project, branch):
        """Push a branch the harness moved itself (e.g. an integrated artifact unit)."""
        path = self.project_path_of(project)
        if _run(["git", "remote", "get-url", "origin"], path).returncode == 0:
            if _run(["git", "push", "--quiet", "origin", branch], path).returncode and branch == "HEAD":
                # Origin moved under a record commit: replay it onto origin, which pushes.
                from ..scheduler.worktrees import catch_up
                catch_up(path)

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
