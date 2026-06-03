---
name: spgr-write-acceptance-criteria
description: Produce a Given/When/Then acceptance-criteria set for one user story, covering happy path, error path, and boundary conditions, with one independently testable scenario per entry. Use when a PM agent finalizes a user story and needs the QA-facing completion contract, or when a QA agent needs to validate that a story's acceptance criteria are complete before writing tests.
---

# write-acceptance-criteria

## Purpose

Acceptance criteria are the contract between the PM and QA agents. They state exactly which behavior must be observable for a story to count as complete. The QA agent consumes this set directly as input to spgr-write-acceptance-test, with a 1:1 relationship between each criterion and a test case. The quality of this set therefore sets the ceiling on test coverage. Write criteria that are specific, observable, and independently testable so that no downstream agent has to interpret completion subjectively.

## Inputs

| Field | Description |
|-------|-------------|
| `user_story` | The user story this set covers, in the finalized INVEST-compliant format. Read it through spgr-read-artifact. |
| `edge_cases` | Known edge cases, error conditions, and boundary values to cover. |
| `nfr_constraints` | Relevant NFR constraints (performance targets, security requirements) the story must satisfy. |
| `persona_context` | The persona's context, used to write realistic "Given" setup conditions. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `acceptance-criteria` | The artifact, written via spgr-write-artifact against its registered schema. Holds the array of criteria, the coverage summary, and the scenario count. |

Each criterion entry carries: `ac_id`, `story_ref`, `scenario_type` (one of `happy-path`, `error-path`, `boundary`), `given`, `when`, `then`, and `nfr_constraint_ref` (or null). The `ac_id` format is `AC-{story_id}-{seq}`, which ties each criterion to its parent story. The artifact also records a `coverage_summary` confirming all three scenario types are present and a `scenarios_count`.

## Procedure

1. Read the user story through spgr-read-artifact. Confirm it is finalized and INVEST-compliant. If the story is missing, still in draft, or contradicts its stated edge cases, stop and raise an escalation through spgr-escalate with a precise list of what is missing rather than inventing the gap.
2. Generate the criteria by walking the story systematically in this order: the primary success scenario, each stated edge case, the standard error paths (empty state, auth failure, network failure), and the NFR-driven scenarios.
3. Cover all three scenario types on every story. Mark each criterion with its `scenario_type`. Include at least one happy-path, one error-path, and one boundary criterion.
4. Write each clause to be testable. The "Given" establishes a specific system state a QA agent can set up without ambiguity. The "When" describes a single atomic user action. If a "When" contains "and then", split it into separate criteria. The "Then" describes an observable, verifiable outcome a test can assert on, not a subjective state.
5. Keep each criterion independently testable. Verifying one criterion must not depend on another passing first.
6. Assign `ac_id` values in sequence as `AC-{story_id}-{seq}`. Set `nfr_constraint_ref` on any criterion driven by an NFR, otherwise null.
7. Build the `coverage_summary` and count `scenarios_count`. If the count exceeds 8, flag the story for potential splitting through spgr-escalate, since a high criteria count signals the story is doing too much. Record the reasoning with spgr-log-decision.
8. Write the artifact through spgr-write-artifact, which runs inline schema validation before the write completes. If validation fails, correct the artifact and rewrite rather than handing off an invalid set. To validate a set received from another agent before consuming it, run spgr-validate-artifact.

## Notes

- The artifact type `acceptance-criteria` is in the schema registry at /Users/gunderer/Repos/springer/schemas/. Reference field rules through spgr-validate-artifact rather than inlining them.
- A story with N criteria should yield at least N test cases at the QA handoff, given the 1:1 criterion-to-test relationship. Do not collapse distinct behaviors into one criterion to keep the count down. Split the story instead.
- When a criterion touches a vertical domain (security, accessibility, performance), consult the specialist through spgr-tag-vertical-agent before finalizing that criterion.
