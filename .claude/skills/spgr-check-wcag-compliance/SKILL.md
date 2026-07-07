---
name: spgr-check-wcag-compliance
description: Produce a WCAG conformance report that assesses a UI component, screen, or feature against WCAG 2.1 and 2.2 success criteria one criterion at a time, with per-criterion verdicts and a severity mapping that gates release on any Level A failure. Use when the Accessibility Agent must confirm a UI conforms to its target WCAG level before release.
---

# check-wcag-compliance

## Purpose

Assess a UI artifact against the WCAG success criteria one criterion at a time, and emit a conformance report. WCAG conformance is not a binary state, it is a criterion-by-criterion judgment, so the report records a verdict per criterion rather than a single overall claim. This is the Accessibility vertical operating as auditor and gate. The severity mapping is the gate: a Level A failure is a barrier that prevents access and blocks the release, a Level AA failure is high priority, and a Level AAA gap is advisory. The verdict and findings reach the owning horizontal agent through a consultation, not by editing that agent's artifact.

Do not confuse this with spgr-run-accessibility-audit. That skill runs axe-core and manual testing on a built UI. This skill is the systematic criterion-by-criterion conformance assessment and report, and it consumes automated-scan results as evidence rather than producing them.

## Inputs

| Field | Description |
|-------|-------------|
| `markup` | HTML or JSX of the component or screen under review |
| `rendered_output` | Rendered result, a Storybook preview, a screenshot, or a live URL |
| `user_flow` | Description of the task the user is trying to accomplish |
| `wcag_target` | Target conformance level. AA is the floor, AAA is pursued where feasible |
| `scan_results` | Optional axe-core or Lighthouse output, consumed as evidence for the criteria it covers |

Read source and artifact inputs through spgr-read-file and spgr-read-artifact. Do not assume an input that was not supplied. If markup, rendered output, the user flow, or the WCAG target is missing or contradictory, stop and raise spgr-escalate with the precise list of what is missing rather than guessing.

## Outputs

| Artifact | Description |
|----------|-------------|
| `wcag-compliance-report` | Conformance report envelope artifact carrying per-criterion verdicts with evidence, per-failure remediation, a severity mapping, and a PASS or GATE verdict |

Write the report through spgr-write-artifact with inline spgr-validate-artifact. The report carries:

- Per-criterion assessment of pass, fail, or not-applicable, each with the evidence that supports the verdict.
- Each failure stated with the specific success criterion, the specific element, and the user impact.
- Remediation guidance per failure, naming the specific code change or design change required.
- Severity mapping: Level A failure is blocking, Level AA failure is high priority, Level AAA gap is advisory.
- Overall verdict: GATE when any Level A criterion fails, otherwise PASS.

## Procedure

1. Read the inputs. Pull markup and any scan results through spgr-read-file and spgr-read-artifact. Confirm the WCAG target and the user flow are present. If any required input is missing or contradictory, stop and call spgr-escalate.
2. Set the assessment scope to the target level and all lower levels. An AA target assesses every Level A and Level AA criterion. Treat AAA criteria as advisory unless AAA is the stated target.
3. Walk the WCAG 2.1 and 2.2 success criteria in scope one at a time. For each, record pass, fail, or not-applicable with concrete evidence from the rendered output or markup.
4. Assess what the user experiences, not what the markup intends. An `aria-label` of "button" satisfies the letter of 4.1.2 Name Role Value but fails the user, so mark it failed with the user-impact note.
5. Use automated scan results as evidence only for the criteria they cover. Automated tooling catches roughly 30 to 40 percent of WCAG violations, so never record a pass on an automatable criterion from tooling alone and never claim full conformance from tooling. Assess the remaining criteria manually.
6. Prioritize the high-impact Level A criteria in the assessment: 1.1.1 Non-text Content, 1.3.1 Info and Relationships, and 4.1.2 Name Role Value account for the majority of high-impact failures.
7. For every failure, write the criterion, the element, the user impact, and the specific remediation, then apply the severity mapping.
8. Compute the verdict. Any Level A failure sets the verdict to GATE. Otherwise the verdict is PASS with Level AA failures listed as high priority.
9. Write the report through spgr-write-artifact with inline spgr-validate-artifact. Record the gate decision and its rationale with spgr-log-decision, and version the report with spgr-version-artifact on revision.
10. Deliver the verdict and findings to the owning Frontend Developer or QA agent through a consultation via spgr-tag-vertical-agent. Do not edit that agent's artifact directly. On a GATE verdict, notify the human checkpoint with spgr-notify-human so the release does not proceed.

## Notes

- Output type is an audit or review report (a check-* report), written as an envelope artifact. Its content schema is registered in a later increment, so envelope-only validation applies for now.
- The gate is the Level A line. A report with any failed Level A criterion returns GATE and blocks the release. Level AA failures are high priority but do not block. Level AAA gaps are advisory.
- The fix order is fixed: Level A first, then Level AA, then Level AAA opportunistically.
- A recommendation to a horizontal agent flows through spgr-tag-vertical-agent as a consultation, never as a direct edit of the other agent's artifact.
- To wire automated coverage into development, integrate axe-core into the component test suite so the violations it can catch fail tests at development time rather than at accessibility review time. That test wiring belongs to spgr-run-accessibility-audit, which this report references rather than duplicates.
