---
name: spgr-write-bug-report
description: Produce a bug-report artifact that documents one defect with deterministic reproduction steps, severity, a root-cause hypothesis, and a committed regression test that fails before the fix and passes after. Use when a QA, developer, or code-reviewer agent observes a defect and must file a reproducible, fix-ready report.
---

# write-bug-report

## Purpose

Turn an observed failure into one bug-report artifact that any agent can act on without further context. A report that cannot be reproduced is a complaint, not a bug report, so the deterministic reproduction steps and the regression test are the load-bearing fields. Every escaped bug is a gap in the test suite, and the regression test closes that gap so the defect cannot recur silently. One report covers one defect. Split a report that describes two distinct failures.

## Inputs

| Field | Description |
|-------|-------------|
| `observed_behavior` | What actually happened, the failing behavior as seen |
| `failure_output` | Test output or log output at the time of failure, including stack traces, error messages, HTTP status codes, and network responses |
| `environment` | Service version, environment name (staging or prod), OS, browser, or device if relevant, test account identifier, and timestamp |
| `affected_story_id` | ID of the story or feature the defect affects, for impact analysis |
| `expected_source` | The acceptance criteria or spec entry that defines what the system should do |

## Outputs

| Artifact | Description |
|----------|-------------|
| `bug-report` | Envelope artifact validated against the `bug-report` schema, carrying title, severity, priority, reproduction steps, expected behavior, actual behavior, environment, root-cause hypothesis, and the regression test reference |
| regression test | A unit or integration test file committed to the repo, named with the bug ID, that fails (red) against current code and passes (green) after the fix |

## Procedure

1. Read the inputs. Read the failing source and the affected story's acceptance criteria with spgr-read-file and spgr-read-artifact so the expected behavior cites the AC or spec entry that defines it, not an opinion.

2. Establish deterministic reproduction. Identify the exact input, state, and sequence that reliably triggers the failure. Write numbered steps executable by any agent without added context. If the trigger is not yet deterministic, narrow it before filing. Do not file "sometimes the button does not work".

3. Write the regression test before or alongside the fix, never after. Confirm it fails against current code with spgr-run-tests, which proves it catches the defect. Name it with the bug ID for traceability. Write the test file with spgr-write-file.

4. If a regression test cannot be written because the failure is environmental or non-deterministic, record that explicitly in the report along with the reason. Omitting the regression test without this record is not allowed.

5. Assign severity (P0 to P3) using the table in Notes. Severity is the QA Agent's call. Set priority in coordination with the Product Manager Agent, since priority is a separate axis from severity and QA does not override PM on prioritization. Use spgr-tag-vertical-agent to reach the PM for the priority decision.

6. Form the root-cause hypothesis from the stack trace and reproduction steps, naming the most likely code location of the failure origin.

7. Before writing, scan open bug reports for similar titles, affected components, and stack-trace signatures. If a likely duplicate exists, surface it and stop rather than filing a second report against the same root cause. Note this duplicate check in the decision log.

8. Write the artifact with spgr-write-artifact, which runs inline spgr-validate-artifact against the registered `bug-report` schema. Record the severity call, the priority coordination, and the duplicate check with spgr-log-decision.

9. If severity is P0 or P1, notify the Product Manager Agent and the relevant vertical agent immediately with spgr-notify-human. Do not file the report and leave a release-blocking defect to be found in the next standup.

10. If inputs are missing or contradictory, or the failure cannot be reproduced and no environmental reason explains it, stop and raise spgr-escalate with the precise list of what is missing rather than guessing.

## Notes

- Validate via spgr-validate-artifact against the registered `bug-report` schema in schemas/. Do not inline the field list.
- Severity table. P0: data loss, security breach, crash, or no access to core functionality, blocks the release, fix first. P1: a feature is broken on the happy path, blocks the release, fix this sprint. P2: works on the happy path but fails in a documented scenario, does not block the release but must be scheduled. P3: cosmetic, copy, or minor UX degradation, batch with other P3s.
- The regression test is source code verified by spgr-run-tests and CI (red before fix, green after), not by an envelope schema. The bug-report artifact references it by path and bug ID.
- Reference the affected story by ID. Five reports against one story is a signal for architectural review with the Architect Agent, not just more fixes.
- A P0 or P1 open-bug count and bug-density signals (per story, per component, per sprint) are written via spgr-write-artifact under their registered schemas, added in a later increment. Do not block this report on them.
