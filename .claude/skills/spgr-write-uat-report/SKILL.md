---
name: spgr-write-uat-report
description: Produce a uat-report envelope artifact that records per-story acceptance-criteria status, tester observations, blocking issues, and a formal human sign-off block, then sets a go or hold deployment gate. Use when the QA Agent compiles UAT session notes and automated test results into the final pre-production checkpoint, or when the Product Manager Agent records human sign-off on a release before it deploys.
---

# write-uat-report

## Purpose

Turn the outcome of a user acceptance testing session into one uat-report artifact that gates production deployment. UAT is the human judgment pass that automated acceptance tests cannot replace. A story can pass every automated check and still fail UAT because it feels wrong, misrepresents the intended experience, or has a usability gap that the literal acceptance criteria did not name. This report records that human verdict per story, the formal attestation of who reviewed it, and the environment they reviewed against. The sign-off is a human-in-the-loop checkpoint. No product deploys to production without a named human recorded in the sign-off block. One report covers one release.

## Inputs

| Field | Description |
|-------|-------------|
| `session_notes` | Tester observations and recorded deviations from expected behavior across the UAT session |
| `acceptance_criteria` | The confirmed acceptance-criteria set for each story in scope, read for the per-AC status |
| `automated_test_results` | Release test run, read to confirm technical pass status before UAT begins |
| `participants` | UAT participants with name, role, and the stories each tested |
| `environment` | The exact environment UAT ran against (for example staging), since a sign-off is environment-specific |

## Outputs

| Artifact | Description |
|----------|-------------|
| `uat-report` | Envelope artifact validated against the `uat-report` schema, carrying the summary counts, per-story AC status and verdict, blocking issues, the named sign-off block, and the go or hold deployment gate status |

## Procedure

1. Read the inputs. Read each story's acceptance criteria with spgr-read-artifact and the automated test results with spgr-read-file or spgr-run-tests. Confirm the release passes its automated suite before opening UAT. If automated tests are failing, stop and raise spgr-escalate, since UAT does not begin on a technically failing build.

2. Record the tested environment once, explicitly. A sign-off on staging does not transfer to production if production configuration differs. Carry the environment name into every sign-off entry.

3. For each story in scope, record the status of each individual acceptance criterion as pass, fail, or conditional. Map each entry to its `ac_id` from the confirmed acceptance-criteria set so the report is traceable back to spgr-write-acceptance-criteria.

4. Capture tester notes per story. Record observations about usability, gaps between spec and experience, and unexpected behavior that may not violate the literal acceptance criteria but warrants discussion. Literal AC compliance is necessary but not sufficient.

5. Set the per-story sign-off verdict as accepted, rejected, or requires-changes. A story that passes automated tests but feels wrong or misrepresents the product experience is correctly recorded as requires-changes. For a conditional acceptance, record the specific issue and the agreed resolution timeline, since a conditional verdict accepts the story for deployment with a logged follow-up.

6. For every rejected or requires-changes story, write the specific rejection reason and the required changes before re-test into `rejection_reason`. The story returns to the implementing agent with those reasons attached. Rejection in UAT is the process working, not a process failure.

7. List every blocking issue that must be resolved before production deployment. A blocking issue holds the gate even if most stories are accepted.

8. Build the sign-off block. Each entry names the reviewer, their role, the environment tested, the date, and their decision. Anonymous sign-offs are not accepted. The Product Manager Agent is the primary product-acceptance authority, but a human principal must review and approve before the gate can read go.

9. Compute the summary counts (total, accepted, rejected, conditional) from the per-story verdicts and set `sign_off_status`. Set `deployment_gate_status` to hold whenever any story is rejected or requires changes, any blocking issue is open, or no human sign-off is recorded. Set it to go only when the human sign-off is present and no blocker remains.

10. Write the artifact with spgr-write-artifact, which runs inline spgr-validate-artifact against the registered `uat-report` schema. Record the gate decision and any conditional-acceptance terms with spgr-log-decision.

11. Pause the pipeline at the sign-off checkpoint with spgr-notify-human so a human records the acceptance decision before the gate opens. Do not mark the gate go on an agent decision alone.

12. If inputs are missing or contradictory, or a story's acceptance criteria are absent, stop and raise spgr-escalate with the precise list of what is missing rather than inferring a verdict.

## Notes

- Validate via spgr-validate-artifact against the registered `uat-report` schema in /Users/gunderer/Repos/springer/schemas/. Do not inline the field list.
- The sign-off is a hard human-in-the-loop gate. The deployment gate cannot read go without a named human entry in the sign-off block, delivered through spgr-notify-human.
- The report is release-scoped. Link each release to its uat-report so a post-mortem can check whether a production issue was seen and deferred in UAT.
- UAT rejection-rate tracking per story type and per implementing agent (a signal of spec misalignment, not just rework) is written via spgr-write-artifact under its registered schema, added in a later increment. Do not block this report on it.
