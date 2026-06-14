# Git workflow standards (shared)

The single source of truth for how Springer agents use git when building an application: the branching model, commit discipline, pull requests, the merge bar, and the release and hotfix flow. The git skills and the developer agents reference this file by repo-relative path and own the mechanics of their own step, this file owns the overall model and the two decisions that no single skill owns, the merge criteria and the release-branch trigger. The model is trunk-based, the modern continuous-delivery practice, not gitflow. There is no long-lived `develop` branch.

This file governs applications Springer builds. It does not govern how the Springer repository itself is maintained, which commits small build changes directly to `main` per CLAUDE.md.

## Contents
- Branching model
- Branch types and naming
- Commit discipline
- Pull requests
- Merge criteria
- Release and hotfix flow
- Boundaries

## Branching model

`main` is the single long-lived branch and is always deployable. A merge to `main` is the confidence signal that a change is ready to ship, and a change not ready to ship is not ready for `main`. A merge to `main` auto-deploys to staging, and production deploys only on a deliberate human signal, owned by spgr-write-cd-pipeline.

Every other branch is short-lived, cut from `main`, and carries one logical change that maps to exactly one story, issue, or chore, per XP small-release discipline. A task that spans two stories needs two branches. `release/*` and `hotfix/*` are also short-lived and exist only for the stabilization and hotfix paths below, not as parallel long-lived lines of development.

## Branch types and naming

spgr-create-branch owns the naming regex and base selection. The five types and their bases:
- `feature/<story-id>-<slug>`, cut from `main`.
- `fix/<issue-id>-<slug>`, cut from `main`.
- `chore/<slug>`, cut from `main`.
- `release/<version>`, cut from `main`, see the release flow below.
- `hotfix/<version>-<slug>`, cut from the matching `release/<version>`, not from `main`.

Names match `^(feature|fix|hotfix|release|chore)/[a-z0-9-]+$`, lowercase letters, digits, and hyphens only. The mechanics, base refresh, and collision checks live in spgr-create-branch.

## Commit discipline

spgr-git-commit owns commit discipline. Every commit is a single Conventional Commits commit, `type(scope): description`, that records one logical change. Files are staged explicitly by path, never with `git add -A` or `git add .`. The full pre-commit hook chain (format, lint, test, commitlint) runs and passes with no bypass. Never pass `--no-verify`, and never pass `--amend` to rewrite a pushed commit. Merge commits and conflict-resolution commits follow the same Conventional Commits format.

## Pull requests

spgr-create-pr opens the PR and spgr-review-pr and the Code Reviewer agent review it. One PR covers one story boundary, a change that crosses two stories is split into two PRs first. A PR stays under 400 meaningful changed lines, excluding generated files, lockfiles, and migrations. Before a PR is marked ready rather than draft, its gates are green: the suite passes, lint is clean, and the test-first order was followed. The description carries the what, the how-to-test steps, and the risks and mitigations, and every vertical agent whose domain the diff touches is auto-tagged for consultation.

## Merge criteria

A pull request merges to `main` only when all of the following hold:
- The PR is ready, not draft.
- The Code Reviewer verdict is APPROVE, with no open P0 or P1 finding.
- Every vertical agent whose gate the diff triggered (for example Security, Compliance, Auth, Accessibility) has signed off.
- CI is green: tests, lint, typecheck, and format all pass.
- The branch is current with `main`, rebased or updated so the merge is a fast path.

The Code Reviewer is the automated gate, and a human is the required approver at the merge checkpoint, fired through spgr-notify-human. The merge keeps `main` linear, by squash or rebase rather than a merge commit, the resulting commit message follows Conventional Commits, and the source branch is deleted after the merge.

In an application project `main` is protected. Every change lands through a reviewed PR and there are no direct pushes to `main`. This is the point where an application differs from the Springer repository itself, where small build commits go directly to `main`.

## Release and hotfix flow

Versioning follows semantic versioning, owned by spgr-bump-version, and a release is tagged `vX.Y.Z`, annotated and immutable, owned by spgr-create-release-tag. `main` is the default release source: tag the release commit on `main` and deploy from it.

A `release/<version>` branch is cut from `main` only when one of two conditions holds:
- A version needs stabilization before general availability, so the release branch takes only fix commits while feature work continues on `main` toward the next version.
- A shipped version must receive a hotfix after `main` has already advanced past it, so the fix cannot simply ship from `main`.

A `hotfix/<version>-<slug>` branches from the matching `release/<version>`, fixes the defect, and is tagged as a new patch version. The same fix is brought forward to `main`, by cherry-pick or merge-forward, so `main` does not regress on the next release. The DevOps agent cuts and manages release branches.

## Boundaries
- spgr-create-branch owns branch naming and base selection.
- spgr-git-commit owns commit discipline and the hook chain.
- spgr-create-pr owns the pull-request artifact and its description.
- spgr-review-pr and the Code Reviewer agent own the review verdict.
- spgr-bump-version and spgr-create-release-tag own versioning and release tags.
- spgr-write-cd-pipeline owns deployment and the deployable-main guarantee.
- This reference owns the overall trunk-based model, the merge criteria, and the release-branch trigger.
