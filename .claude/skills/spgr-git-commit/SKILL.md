---
name: spgr-git-commit
description: Stage explicitly named files and create one atomic Conventional Commits commit that passes pre-commit hooks (lint, format, test, commitlint) with no bypass. Use when a developer or DevOps agent has completed one logical change, or when any agent that modified files must commit them under Springer commit discipline.
---

# git-commit

## Purpose

Record one logical change as a single Conventional Commits commit so the history is readable by a person and parseable by changelog, version-bump, and release automation. A commit that mixes two concerns (a refactor and a feature) is two commits. The contract that matters here is atomicity, explicit staging, and a passing hook chain with no bypass, so the history stays trustworthy and every line traces to the commit that introduced it.

## Inputs

| Field | Description |
|-------|-------------|
| `files` | Explicit list of changed file paths to stage. Never a wildcard. |
| `type` | Commit type, one of feat, fix, chore, docs, test, refactor, perf, ci, build. |
| `scope` | Optional component or domain being changed, for example auth or api. |
| `description` | Short summary in imperative present tense, under 72 characters. |
| `body` | Optional explanation of why the change was made when not obvious from the description. |
| `breaking` | Optional breaking-change description, rendered as a footer. |
| `co_authors` | Optional list of Co-Authored-By trailers for pair or agent collaboration. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Git commit | One atomic commit on the working branch whose message follows the Conventional Commits format and that passed every pre-commit and commit-message hook. |

## Procedure

1. Read the candidate change set with spgr-read-file and confirm the staged files form one logical change. If the set spans two unrelated concerns, split it and run this skill once per concern. Each commit is one logical change.
2. Confirm no file in the list is a secret, an `.env` file, a debug scratch file, or a generated artifact that should not be tracked. Drop any such file from the set before staging.
3. Stage each file explicitly by path with `git add <path>`. Never run `git add -A` or `git add .`, so an untracked debug or env file cannot enter the commit by accident.
4. Run the project formatter and linter on the staged files first through spgr-format-code and spgr-lint-code, and run the affected tests through spgr-run-tests. Reach a clean result before composing the message, so the commit does not depend on the hook to find a problem the agent should have fixed.
5. Compose the message as `type(scope): description`, for example `feat(auth): add PKCE flow for OAuth callback`. Omit the parentheses when there is no scope. Add the body as a paragraph after a blank line when a why is needed. Add a `BREAKING CHANGE:` footer when `breaking` is set. Add each `Co-Authored-By:` trailer last.
6. Commit with `git commit`. Let the pre-commit hooks (format, lint, test) and the commitlint commit-message hook run. Never pass `--no-verify` and never pass `--amend` to rewrite a pushed commit.
7. If any hook fails, do not retry with a bypass. Read the hook output, fix the underlying issue (a lint violation, a failing test, a non-conventional message), and commit again. If the failure is outside this skill's scope to fix, for example a contradicting acceptance criterion or a broken shared config, stop and raise spgr-escalate with the exact hook output rather than forcing the commit through.

## Notes

- The output is source-control state, a commit, not an envelope artifact. It is verified by the pre-commit hook chain and CI rather than by a registered schema, so there is no spgr-validate-artifact call here.
- Commitlint enforces the Conventional Commits format in the pre-commit hook. When a repository has no commitlint hook yet, install it as part of this commit so later commits are checked, and treat that hook install as its own logical change committed separately.
- A pushed commit is immutable. To correct one already pushed, add a new follow-up commit rather than amending or force-pushing.
