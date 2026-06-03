---
name: spgr-write-acceptance-test
description: Write an automated acceptance test suite in Gherkin Given/When/Then form from a confirmed acceptance-criteria set, one .feature file per story with one scenario per criterion, exercised at the integration level and confirmed failing before any implementation begins. Use when a QA agent turns a story's confirmed acceptance criteria into the executable specification, or when a developer agent is blocked from starting because the failing acceptance tests for a story do not yet exist.
---

# write-acceptance-test

## Purpose

Acceptance tests are the executable specification for a story and its primary definition of done. Writing them from the confirmed acceptance criteria before any implementation exists forces the criteria to be precise, since a criterion that cannot be encoded as a runnable scenario is not ready. The test-first sequence is the core XP loop at the story level. The developer agent does not begin implementation until these tests exist and a CI run has confirmed every scenario fails, establishing a true red state. Produce the suite as source code, not as an envelope artifact.

## Inputs

| Field | Description |
|-------|-------------|
| `acceptance_criteria` | The confirmed acceptance-criteria artifact for one story, read through spgr-read-artifact. Each criterion supplies one scenario. The set must be confirmed ready by the PM agent. |
| `api_spec` | The OpenAPI spec or data model relevant to the story, if available, read through spgr-read-artifact or spgr-read-file. Supplies the endpoints, request and response shapes, and database state the steps assert against. |
| `edge_cases` | Edge cases and error conditions named in the story, used to drive Scenario Outline rows beyond the base criteria. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `<story>.feature` | One Gherkin feature file per story, written through spgr-write-file. One Scenario per acceptance criterion, plus Scenario Outline entries for parameterized or boundary cases. |
| step definitions | Integration-level step definitions written through spgr-write-file, exercising the real test service over HTTP and asserting against real test-database state. |
| red-state record | A failing test run confirming every scenario fails before implementation, captured through spgr-run-tests and logged through spgr-log-decision. |

## Procedure

1. Read the acceptance-criteria artifact through spgr-read-artifact and validate it with spgr-validate-artifact. Confirm it is marked ready by the PM agent. If it is missing, still draft, or internally contradictory, stop and raise spgr-escalate to the PM agent with the specific ambiguity stated, for example which two criteria conflict and on what value, not a generic note that the criteria need clarification.
2. Read the relevant api_spec or data model so each step targets a real endpoint and a real database assertion rather than a guessed shape.
3. Create one `.feature` file for the story. Write one Scenario per acceptance criterion, with a 1:1 mapping from criterion to scenario. Map each criterion's Given, When, and Then directly into the scenario.
4. Title each scenario as a complete sentence describing the behavior, not the implementation. Write "User receives a 401 when accessing a protected resource without a valid token", not "test unauthenticated request".
5. Add a Scenario Outline with an Examples table for each parameterized or boundary case named in the edge_cases input, so boundary values are covered without copying a scenario per value.
6. Keep any Background block minimal, limited to shared setup such as creating a user and obtaining a token. A long Background signals test coupling, so move story-specific setup into the scenario it belongs to.
7. Write integration-level step definitions through spgr-write-file. Each step makes a real HTTP call to the test service and asserts against real test-database state. Do not mock at the system boundary, since a boundary mock removes the behavior the acceptance test exists to verify.
8. Run the full suite through spgr-run-tests and confirm every scenario fails. Record this red state through spgr-log-decision as the gate that unblocks implementation. If a scenario passes before any implementation exists, the test is asserting nothing meaningful, so correct it and rerun.
9. Hold the test-first sequence in this order: criteria confirmed, tests written and committed, CI confirms tests fail, then implementation begins. If asked to write tests against unconfirmed criteria, or if implementation has already begun without a recorded red state, raise spgr-escalate rather than proceeding.
10. Commit the feature files and step definitions as one logical change, lint and format clean, before any implementation commit. Build only the scenarios the criteria specify and no speculative cases beyond the named edge cases.

## Notes

- The output is source code, Gherkin feature files and step definitions, verified by spgr-run-tests and CI rather than by an envelope schema. There is no registered artifact type for the suite itself.
- Passing acceptance tests are never deleted or archived after implementation. They become the story's regression suite and run in CI on every merge.
- A story with N confirmed criteria yields at least N scenarios. Do not collapse distinct behaviors into one scenario to shrink the count.
- When a criterion touches a vertical domain such as security, accessibility, or performance, consult the specialist through spgr-tag-vertical-agent before encoding that scenario.
- The acceptance criteria consumed here come from spgr-write-acceptance-criteria. Read and validate that artifact through spgr-read-artifact and spgr-validate-artifact against its registered schema in /Users/gunderer/Repos/springer/schemas/ rather than inlining field rules.
