---
name: spgr-resolve-merge-conflict
description: Resolve git merge conflicts by understanding the intent of both sides and producing a correct merged result, then land it as a `chore: resolve merge conflict` commit and re-run the test suite. Use when a backend, frontend, mobile, or DevOps developer agent hits conflicts during a merge or rebase and must reconcile two changes that touched the same code, rather than accepting one side wholesale.
---

# resolve-merge-conflict

## Purpose

Resolve every conflicted hunk by writing the merged version that achieves what both sides intended, never by accepting `ours` or `theirs` wholesale and never by discarding a change. A merge conflict means two changes touched the same code for different reasons, so resolution is a semantic task, not a mechanical one. Blindly picking a side is the most common way to silently lose behavior. When the correct resolution is ambiguous, escalate instead of guessing.

## Inputs

| Field | Description |
|-------|-------------|
| `conflicting_branch` | The branch being merged in |
| `base_branch` | The branch being merged into |
| `change_context` | What each side implements (the story, fix, or ADR behind each change), used to read intent, not just the diff |

## Outputs

| Artifact | Description |
|----------|-------------|
| Merged working tree | Conflict-free result that incorporates both sides' intended behavior |
| Resolution commit | One commit per conflict file in the form `chore: resolve merge conflict in <filename> - <both sides described>` |
| Conflict-frequency note | A line recording the file and the branch pair, so repeated conflicts in one file surface structural coupling for the Architect Agent |

## Procedure

1. Start the merge or rebase and let it stop on conflict. List every conflicted path with `git status` and `git diff --name-only --diff-filter=U`.
2. For each conflicted file, read the full surrounding context of both hunks with spgr-read-file, not only the region between the conflict markers. Pair each side with its `change_context` to establish what each change was trying to accomplish.
3. Write the merged version that satisfies both intents. Do not run `git checkout --ours` or `--theirs` to take a side wholesale, and do not delete either side's behavior. Remove all conflict markers. Save with spgr-write-file.
4. Stage each resolved file and verify no markers remain with `git diff --check`.
5. Re-run the full suite with spgr-run-tests on the merged result. Conflict resolution creates new code paths the existing tests may not cover, so treat a green suite as the gate. If the suite fails or a new path is untested, fix the resolution or add coverage before committing.
6. Commit per the message format above with spgr-git-commit. Log the resolution and its rationale with spgr-log-decision.
7. Record the conflict in the frequency note: increment the count for this file and this `base_branch` / `conflicting_branch` pair. When a file crosses a recurring-conflict threshold, raise it with spgr-tag-vertical-agent to the Architect Agent as a structural-coupling signal.
8. Escalate with spgr-escalate when both sides changed the same logic for different reasons and the correct merged behavior cannot be determined from context. Route to the Architect Agent or the authors of both changes, and do not commit a guessed resolution. Use spgr-notify-human if neither author nor the Architect can be resolved automatically.

## Notes

- Output type is SOURCE: the deliverable is merged source plus a git commit, verified by spgr-run-tests, not an envelope artifact. The conflict-frequency note is operational tracking, not a registered artifact.
- Never resolve by taking one side wholesale or by discarding a change. Ambiguity is an escalation trigger, not a tie broken by the resolver.
- The test re-run after resolution is mandatory. A merge is not complete until the suite passes on the merged tree.
