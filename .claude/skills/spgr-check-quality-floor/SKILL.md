---
name: spgr-check-quality-floor
description: Produce a floor-guard report that scans a change's diff for a lowered quality bar (new lint or type suppressions, skipped or deleted tests, removed assertions, stubs in source, hook bypasses, loosened coverage thresholds), with a clean, violation, or unverified status. Use on every PR review and before a developer agent opens a PR.
---

# check-quality-floor

## Purpose

A review that reads a diff for correctness can miss the moves that make the bar easier to clear rather than clearing it: a linter silenced on one line, a test skipped or focused, a test file deleted, assertions removed, a stub left in production code, a hook bypass added to a script, or a coverage threshold nudged down. Each one passes CI and reads as progress. This skill runs a deterministic scan for exactly those moves over the lines a change added and the files it removed, so the Code Reviewer carries each as a finding with a file and line instead of hunting for it, and a developer agent catches its own before the review spends a retry on it. The scan is mechanical and runs with no model. Dispatch it at the Deterministic tier.

## Inputs

| Field | Description |
|-------|-------------|
| `base` | The branch the change will merge into. Defaults to `origin/main`, falling back to `main`. The scan covers `git merge-base HEAD <base>` to the working tree plus untracked files. |
| `repo` | The repository to scan. Defaults to the current directory. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `floor_report` | The script's output: the base and merge base used, a `violations` list (rule, file, line, matched text), a `kept` list (rule, file, line, the reason from the `floor: keep` annotation), and a status of `clean`, `violation`, or `unverified`. JSON with `--json`, a table otherwise. |

## Procedure

1. Run the scan from the repository root, with `--base` set to the PR's base branch when it is not `origin/main`:

   ```bash
   python3 .claude/skills/spgr-check-quality-floor/scripts/floor_guard.py --json
   ```

   The rules it applies are listed in the script's docstring: `suppression`, `test-skip`, `test-deleted`, `assertions`, `stub`, `hook-bypass`, and `threshold`. A threshold finding fires only when a floor was loosened. Tightening is silent.

2. Read the exit code before the output. Exit 0 is clean. Exit 1 carries violations. Exit 2 means the scan could not run, because the directory is not a git repository or no merge base with the base branch exists. Exit 2 is unverified, never clean. Record it as unverified in the review summary and say why.

3. Map every violation to a P1 finding on the `xp` axis in spgr-review-pr, with the rule, the file, the line, and the matched text as the evidence. Downgrade or drop a violation only when the ADR log carries an approved exception that names it, and cite the exception in the finding.

4. Carry every `kept` entry into the review summary as one line each. A `floor: keep <reason>` annotation suppresses the violation, not the reviewer's attention. A kept entry with no reason, or a reason that does not explain why the lower bar is correct here, is raised as a P1 on the `xp` axis.

5. When a developer agent runs the scan before spgr-create-pr, fix each violation or add the narrowest `floor: keep <reason>` on the same line, never a blanket one. A `TODO(DEF-<n>)` placeholder the defaults ledger owns is reported under `stub` so the PR description can list it, and it still blocks auto-merge per the defaults ledger.

## Notes

- The scan is deterministic and runs with no model. Dispatch it at the Deterministic tier in the dispatch-tier table in `.claude/references/pdca-harness.md`.
- The scan reads added lines and deleted files only. It does not judge the code that was already there, which is the Code Reviewer's collective-ownership job.
- A test file is one under `tests/`, `test/`, `__tests__/`, or `spec/`, named `test_*.py`, `*_test.go`, `*_test.py`, `*_test.rb`, `*.test.*`, `*.spec.*`, or `conftest.py`. The skip and assertion rules apply to those files, the stub rule to every other file.
- Prose files (`.md`, `.txt`, `.rst`) are exempt from the hook-bypass rule, because a standard that says never to pass `--no-verify` must be able to say so.
- The output is not an envelope artifact and has no registered schema. Its result enters the run store through the code-review artifact the reviewer writes.
- The design of the rule set follows the floor guard in addyosmani/agent-skills, rewritten for Springer's review contract.
- This skill has no Phase 1 vault spec. It was authored to the Springer build standards as a net-new capability.
