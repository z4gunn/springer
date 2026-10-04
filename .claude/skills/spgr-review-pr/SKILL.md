---
name: spgr-review-pr
description: Review a pull request for correctness, architecture compliance, XP discipline, and test coverage, producing a code-review envelope with severity-categorized findings and an APPROVE, REQUEST_CHANGES, or COMMENT verdict. Use when the Code Reviewer agent picks up a ready PR, or when a change needs a structured review gate before merging to main.
---

# review-pr

## Purpose

Review one pull request and record the result as a code-review artifact the author and the orchestrator can act on without re-reading the diff. Code review is the last quality gate before code reaches main. The job is not to find every possible improvement, which produces review paralysis and adversarial dynamics, but to catch the things that are expensive to fix after merge: bugs, deviations from confirmed ADRs, and missing tests for new behavior. Automated tools already check style and formatting, so spend the review budget on what those tools cannot see. The reviewer does not refactor the code in the PR. The reviewer requests the change from the author and explains why, because editing during review conflates authorship and review and erases accountability.

## Inputs

| Field | Description |
|-------|-------------|
| `pr_ref` | The pull-request artifact or PR reference under review, read for the diff, the what, the how-to-test, and the story link |
| `story_ref` | The originating story whose confirmed acceptance criteria the change must satisfy, used to confirm every criterion is tested |
| `adrs` | The relevant Architecture Decision Records the change must conform to |
| `style_guide` | The project style guide, used to confirm the automated style gate covers the conventions in play |

## Outputs

| Artifact | Description |
|----------|-------------|
| `code-review` | Envelope artifact validated against the registered `code-review` schema, carrying pr_ref, story_ref, axes_checked, findings with per-finding file, line, severity, axis, description, and remediation, a `declined_to_judge` list, a `cannot_verify` list, a summary, and the verdict |

## Procedure

1. Read the inputs. Read the PR with spgr-read-artifact for the pull-request envelope and spgr-read-file for the changed files, the linked story's confirmed acceptance criteria with spgr-read-artifact, and each relevant ADR with spgr-read-artifact. Count the meaningful changed lines, excluding generated files, lockfiles, and migrations.

2. Check the PR size first. If the change exceeds 400 meaningful lines it cannot be reviewed coherently. Stop, set the verdict to REQUEST_CHANGES with a single finding that requests a split at a story boundary, and do not review the rest. Record the size check with spgr-log-decision.

3. Confirm the automated gates ran. Confirm tests pass via spgr-run-tests output and lint is clean. Style and formatting are the automated tools' job, so do not raise style nits the formatter already enforces. Treat a failing test gate or a dirty lint as a blocking finding rather than re-doing the tools' work by hand.

4. Review correctness. Read the diff for bugs, broken edge cases, incorrect error handling, and logic that does not match the story. Each correctness defect is a blocking finding.

5. Review test coverage. Confirm every confirmed acceptance criterion for the linked story has a test, and that the failing test preceded the implementation per test-first order. New behavior without a test is always a blocking finding.

6. Review architecture compliance. Compare the change against the relevant ADRs. Any deviation from a confirmed ADR is always a blocking finding, since the architecture is an immutable constraint once approved.

7. Review docstrings and contracts. Confirm public functions and exported contracts carry the documentation the project requires. A missing or wrong contract doc is a finding scaled to its impact.

8. Review design quality when the diff touches UI: markup, styles, components, screens, or motion. Run `.claude/skills/spgr-render-design-comps/scripts/capture-comps.py` on the changed routes or files, which captures them headless and runs the slop detector when those tools are installed, then read the captures and critique by the procedure in `.claude/references/design-quality.md`. A calibration-cluster hit on an axis the brief left free, a craft-floor miss, or a detector finding is a P1 on the `design` axis, with the detector line, the screenshot path, or the measured value as evidence. Motion and copy items are P2. When neither tool is installed, critique the markup and styles against the same sections and say so in the summary. Skip this step on a diff with no UI change and set the `design` axis to false.

9. Tag verticals when the diff touches a vertical domain. Call spgr-tag-vertical-agent for a domain-specific review (for example security on a dependency or auth change, accessibility on user-facing UI) and fold each returned recommendation into the findings.

10. Pass each candidate finding through the pre-report gate before writing it: the file and line, the named input or state and the failure it produces, the criterion, ADR, rule, or test gap it violates by id, and for a blocking finding the evidence that confirms it (a test or command run with its output pasted, a grep showing the caller, or the ADR clause quoted). A candidate that cannot answer all four is downgraded to P3 or dropped. Then write the finding so it is specific and actionable. Name the file and line, state what is wrong and the consequence, and give the remediation. "This is wrong" is not a finding. State the cause and the fix instead, for example a query that fetches a full object where only one field is needed and so causes N+1 calls in the calling loop. Map severity to the schema tiers: P0 and P1 for blocking defects (bugs, missing tests for new behavior, ADR deviations, security issues), and put the evidence in the finding's `evidence` field, which the schema requires on those tiers. P2 and P3 are non-blocking items (optional improvements, deferred cleanups). Style nits the formatter does not enforce are P3 and never block. Record clarification requests as findings on the relevant axis and let the verdict reflect whether any blocker remains. The Code Reviewer agent carries the list of recurring false findings that are never raised.

11. Compute the review coverage metric and record it in the summary: the percentage of changed lines that received a finding or comment. Very low coverage signals the diff was glossed over and warrants a second pass. Very high coverage signals the PR is too large, which step 2 should already have caught.

12. Fill the two lists that keep the review honest. `declined_to_judge` names every behavior in the diff that was looked at and set aside, with the reason. `cannot_verify` names every check the package could not answer (execution, a live service, a file outside the diff) with the command that would answer it, and the harness runs those in Check. Neither list is optional when it has members.

13. Set the verdict. REQUEST_CHANGES if any P0 or P1 finding exists. APPROVE if only P2 or P3 findings remain and every acceptance criterion is tested, including an APPROVE with no findings at all, which is the expected result on a small, tested diff. COMMENT when the review raises only questions that may or may not lead to a change. Set each axes_checked boolean from the work actually done, not from intent.

14. Write the artifact with spgr-write-artifact, which runs inline spgr-validate-artifact against the registered `code-review` schema. Record the verdict rationale, the coverage figure, and any vertical tags with spgr-log-decision.

15. Escalate rather than guess. If the inputs are missing or contradictory, the diff is unreadable, the linked story or its acceptance criteria are absent, or an ADR conflicts with what the change requires, stop and raise spgr-escalate with the precise list of what is missing or in conflict rather than approving on incomplete input.

## Notes

- Validate via spgr-validate-artifact against the registered `code-review` schema in schemas/. Do not inline the field list.
- The `design` axis applies to UI-touching diffs only. Its bar is `.claude/references/design-quality.md` and its deterministic half is the detector output the capture script records.
- The implementer's report is read as the implementer grading itself. Its pasted output is evidence of the command it shows, its rationale never downgrades a finding, and a test it evidences is not re-run for reassurance. The Code Reviewer agent carries the full reading rules.
- Severity maps the spec's categories onto the schema enum: blocking is P0 or P1, non-blocking is P2 or P3, and questions are findings whose verdict is COMMENT when no blocker exists. The schema requires per-finding file, line, severity, description, and remediation, an axis from architecture, xp, style, docstring, correctness, security, or design, and on P0 and P1 an `evidence` field. A blocking finding without evidence fails validation and is never written.
- Bugs, missing tests for new behavior, and ADR deviations are always blocking. Style nits the formatter enforces are never findings, and other style preferences are never blocking.
- Do not refactor or edit the PR code in this skill. Request the change from the author through the findings. The merge decision is a human-in-the-loop gate handled by spgr-notify-human, not by this skill. This verdict is the automated gate in the merge criteria defined in `.claude/references/git-workflow.md`, an APPROVE with no open P0 or P1 is a precondition for merge.
