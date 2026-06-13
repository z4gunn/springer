---
name: spgr-create-pr
description: Open a pull request and produce a pull-request envelope artifact with a structured description that gives the reviewer the what, the story link, how to test, risks and mitigations, and a completion checklist, plus auto-tagging of every vertical agent whose domain the diff touches. Use when the backend, frontend, mobile, or DevOps developer agent has finished a change on a branch with passing tests and a clean lint, and needs the change opened for review against the approved acceptance criteria.
---

# create-pr

## Purpose

Open one pull request and record it as a pull-request artifact the Code Reviewer Agent can act on without reconstructing context from the diff. A PR description is a communication artifact, not just a merge trigger. The what, the how-to-test, and the risks are the load-bearing fields, because they turn review into a focused conversation rather than a discovery exercise. One PR covers one story boundary. Split a change that crosses two stories into two PRs before opening either.

## Inputs

| Field | Description |
|-------|-------------|
| `source_branch` | The branch to merge from, the work just completed |
| `base_branch` | The merge target, `main` by default, the release branch for a hotfix |
| `story_ids` | The originating story or issue references the change satisfies |
| `change_summary` | What changed and why, the raw material for the what field |
| `acceptance_criteria` | The confirmed acceptance-criteria set for each story, read to confirm every criterion is tested |

## Outputs

| Artifact | Description |
|----------|-------------|
| `pull-request` | Envelope artifact validated against the registered `pull-request` schema, carrying pr_id, story_ids, source and base branch, what, how_to_test, risks_and_mitigations, the completion checklist, vertical_consultations, and the draft flag |
| opened PR | A pull request opened on the remote with the structured description filled from the artifact content, opened as draft when the work is still in progress |

## Procedure

1. Read the inputs. Read each story's confirmed acceptance criteria with spgr-read-artifact and the changed files with spgr-read-file, so the description cites what the change satisfies rather than an opinion.

2. Check the story boundary. Confirm the diff maps to the stories in `story_ids` and does not bundle unrelated work. If it crosses two stories, stop and split before opening, since a reviewer cannot approve two stories under one decision.

3. Check the PR size. The guideline is under 400 changed lines, excluding generated files, lockfiles, and migrations. If the change exceeds that, split it at a story boundary and open the smaller PR first. Record the split in the decision log.

4. Confirm the gate is green before opening as ready. Run spgr-run-tests and confirm the suite passes, confirm the lint is clean via spgr-lint-code, and confirm the test-first order was followed (the failing acceptance test preceded the implementation). Set the checklist booleans from these results, not from intention. Open a draft PR instead when the work is incomplete and needs early feedback.

5. Build the what, the how-to-test, and the risks. Write the what as one paragraph naming what changed and why. Write how_to_test as numbered steps any reviewer can run without added context. Record risks_and_mitigations covering edge cases, rollback concerns, and any dependency on another open PR. Reference screenshots or recordings in how_to_test for a UI change.

6. Auto-tag vertical agents by file path. Map each changed path to its vertical domain (for example `src/auth/**` to the Auth Agent, a security-sensitive or dependency change to the Security Agent, a user-facing UI change to the Accessibility Agent), and call spgr-tag-vertical-agent for each match. Record each consultation in `vertical_consultations`. See the path-to-vertical map in Notes.

7. Write the artifact with spgr-write-artifact, which runs inline spgr-validate-artifact against the registered `pull-request` schema. Open the PR on the remote with `gh` using the artifact content as the description body, marking it draft when step 4 set the draft flag. Record the size check, the split decision if any, and the vertical tags with spgr-log-decision.

8. If the gate is not green (a test fails, lint is dirty, or the test-first order was not followed), do not open a ready PR. Either open a draft and note the failing gate, or stop and fix the gate first. Do not set a checklist boolean to true that the gate run did not confirm.

9. If inputs are missing or contradictory, the source branch does not exist, no story reference is supplied, or a confirmed acceptance criterion is untested, stop and raise spgr-escalate with the precise list of what is missing rather than opening a PR on incomplete input.

## Notes

- Validate via spgr-validate-artifact against the registered `pull-request` schema in schemas/. Do not inline the field list.
- The schema requires `test_first_followed`, `tests_passing`, and `lint_clean` in the checklist. These reflect XP discipline and gate the PR. `docs_updated` and `agents_notified` are recorded when applicable.
- A draft PR is not reviewed by the Code Reviewer Agent until it is converted to ready. Set `is_draft` true while the work needs early feedback only.
- Path-to-vertical map (extend per project structure): `**/auth/**` to Auth, dependency or secrets-sensitive change to Security, user-facing UI to Accessibility, schema or migration change to Architect, billing or tenancy paths to Billing or Multi-tenancy. Each match becomes one spgr-tag-vertical-agent consultation listed in `vertical_consultations`.
- A merge is a human-in-the-loop gate. This skill opens the PR and records the artifact. It does not merge. The merge decision runs through spgr-notify-human at the merge checkpoint.
