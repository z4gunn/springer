---
name: spgr-check-xp-compliance
description: Produce an XP-compliance check on a pull request, scoring it against the five Springer engineering disciplines (test-first, YAGNI, DRY, simple design, refactoring responsibility) with a per-rule verdict, evidence from the diff, and a blocking-or-non-blocking severity on each finding. Use when the Code Reviewer agent reviews a PR, or when the QA or developer agent needs XP discipline confirmed against a story's acceptance criteria before the change is allowed to merge.
---

# check-xp-compliance

## Purpose

Make XP compliance a reviewable gate rather than a general aspiration. XP principles are easy to agree with and easy to violate under sprint pressure, so this skill turns each discipline into a specific checkable question and returns a per-rule verdict with diff evidence. It enforces the Springer contract that "done" means tested, not merely implemented. The skill checks one PR at a time and does not fix the code. It reports findings for the Code Reviewer agent to act on.

## Inputs

| Field | Description |
|-------|-------------|
| `pr_diff` | The PR diff and description, read via spgr-read-file or from the pull-request artifact via spgr-read-artifact. |
| `acceptance_criteria` | The story's confirmed acceptance criteria, read via spgr-read-artifact, used to judge test coverage and YAGNI scope. |
| `xp_rules` | The project's XP compliance rules and any per-project thresholds. Defaults to the five disciplines below when none are supplied. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `xp-compliance findings` | A per-rule check result (test-first, YAGNI, DRY, simple design, refactoring responsibility), each with a verdict, the diff evidence, and a blocking-or-non-blocking severity, plus a coverage-gap list of changed lines with no covering test and an overall pass-or-block summary. |

## Procedure

1. Read the PR diff, the PR description, and the linked story acceptance criteria. Identify every changed line and group the diff into the new behaviors it introduces.

2. Run the coverage-gap detector. Map each changed line to the tests that exercise it. Build the list of changed lines that have no covering test. This list is the first-pass test-first signal and feeds rule 1 below.

3. Check test-first discipline. Confirm every new behavior has a corresponding test and that tests were added before or alongside the implementation, not after. Any new behavior with no covering test is a blocking finding, never a non-blocking suggestion.

4. Check YAGNI. Compare the implemented behavior to the acceptance criteria. Flag any behavior not in the criteria and any abstraction layer, hook, or configuration point with no current consumer. YAGNI violations are blocking, because untasked behavior inflates the PR, obscures intent, and adds maintenance burden for features that may never be used.

5. Check DRY. Search the codebase for logic the PR duplicates and record obvious extraction opportunities. Use spgr-search-codebase to confirm a suspected duplicate exists elsewhere before flagging it.

6. Check simple design. Confirm the implementation is the simplest change that makes the tests pass, with no speculative generality and no premature optimization.

7. Check refactoring responsibility (Boy Scout Rule). Scope this to code the PR touches, not the whole codebase. The bar is "leave it better than you found it," not "fix everything." Flag obvious messes left untouched in changed files.

8. Assign a severity to each finding. Mark test-first gaps and YAGNI violations as blocking. Mark DRY, simple-design, and refactoring findings as non-blocking unless a project XP rule raises them. Compute the overall summary as block when any blocking finding exists, otherwise pass.

9. Write the findings via spgr-write-artifact and validate inline with spgr-validate-artifact. The xp-compliance type is not yet in the schema registry, so write it via spgr-write-artifact with its registered schema added in a later increment, and surface the findings into the code-review artifact the Code Reviewer agent owns. Record any consequential judgment call with spgr-log-decision.

10. Escalate with spgr-escalate when the inputs do not support a verdict, for example when the acceptance criteria are missing or contradictory so YAGNI and coverage cannot be judged, or when the diff cannot be mapped to tests. Return the precise list of what is missing rather than guessing a verdict.

## Notes

- Output is findings, not source code. The skill reads and reports, it does not edit the PR. Acting on the findings belongs to the Code Reviewer agent.
- Reference the schema registry through spgr-validate-artifact rather than inlining field lists.
- Severity rule is fixed, not advisory. A missing test for new behavior and a YAGNI violation are always blocking. Do not downgrade either to a suggestion.
- Coverage data comes from a test run. When current coverage is unavailable, request it through spgr-run-tests before judging test-first, rather than inferring coverage from the diff alone.
