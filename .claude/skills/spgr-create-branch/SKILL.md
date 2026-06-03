---
name: spgr-create-branch
description: Create a feature, fix, hotfix, release, or chore branch with a convention-compliant name, cut from an up-to-date copy of the correct base, then push it to the remote. Use when a backend, frontend, mobile, or DevOps developer agent starts a development task and needs a named branch before any commit, or when a hotfix must be cut from a release branch rather than from main.
---

# create-branch

## Purpose

Branch naming and base selection are the first decision in every development task. Inconsistent names make CI harder to maintain, PRs harder to filter, and history harder to read. Cutting from the wrong base puts a hotfix on top of unreleased work. Enforce one naming convention and one base-selection rule so every branch in the repository is predictable. Hold one logical change per branch in keeping with XP small-release discipline, so the branch maps to exactly one story, issue, or chore.

## Inputs

| Field | Description |
|-------|-------------|
| `branch_type` | One of `feature`, `fix`, `hotfix`, `release`, `chore`. |
| `story_or_issue_id` | Story or issue ID for `feature` and `fix` branches (for example `SPGR-42`). Not used for `release` or `chore`. |
| `version` | Target version for `hotfix` and `release` branches (for example `v1.4.2`). |
| `description_slug` | Short description for the branch tail. Lowercased and hyphenated by this skill. |
| `base_branch` | Base to cut from. Defaults to `main`. For a `hotfix` the base is the matching `release/` branch. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Named branch | A convention-compliant branch created locally from the up-to-date base and pushed to the remote with upstream tracking set. |

## Procedure

1. Resolve the base branch. For `feature`, `fix`, `release`, and `chore`, use `base_branch` (default `main`). For `hotfix`, override to the matching `release/<version>` branch and reject the run if that release branch does not exist.
2. Build the branch name from `branch_type`:
   - `feature/<story-id>-<slug>` (for example `feature/SPGR-42-add-oauth-flow`)
   - `fix/<issue-id>-<slug>`
   - `hotfix/<version>-<slug>`
   - `release/<version>` (for example `release/v1.4.2`)
   - `chore/<slug>`
3. Normalize the name. Lowercase the slug, replace spaces and underscores with single hyphens, and strip every character that is not a lowercase letter, a digit, a hyphen, or the type prefix slash. The result must match `^(feature|fix|hotfix|release|chore)/[a-z0-9-]+$`.
4. Confirm the required fields for the type are present. A `feature` or `fix` needs `story_or_issue_id`. A `hotfix` or `release` needs `version`. If a required field is missing or the normalized name fails the pattern, stop and call spgr-escalate with the specific field and the failing value. Do not invent an ID or a slug.
5. Check out and refresh the base. Run `git fetch origin`, check out the base branch, and `git pull` so the branch is cut from an up-to-date local copy. If the working tree is dirty, stop and call spgr-escalate rather than discarding uncommitted work.
6. Reject a name collision. If the branch already exists locally or on the remote, stop and call spgr-escalate instead of force-creating over it.
7. Create the branch with `git checkout -b <name>` from the refreshed base, then push it with `git push -u origin <name>` to set upstream tracking.
8. Return the created branch name and its base so the calling agent can proceed to spgr-implement-feature or the first commit.

## Notes

- The output is a git branch, not an envelope artifact. There is no registered schema. The result is verified by the post-create checks in the procedure (pattern match, base freshness, no collision) and by the branch existing on the remote, not by spgr-validate-artifact.
- Branch names use only lowercase letters, digits, and hyphens. No underscores, no uppercase, no other special characters.
- The naming convention is also enforced server-side by a push-time hook or branch-protection rule that rejects non-conforming names. This skill makes the local name conform so the push is accepted on the first attempt.
- One branch carries one logical change. A task that spans two stories needs two branches.
- Use spgr-escalate for every stop condition in the procedure. Do not fill a missing ID, slug, or version with a guess, and do not overwrite an existing branch or a dirty tree.
