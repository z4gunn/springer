---
name: spgr-implement-feature
description: Implement one confirmed user story in a feature branch under test-first XP discipline, writing the failing acceptance test before any implementation, then the code that makes it pass, plus unit tests for non-trivial logic, and an opened pull request that confirms every acceptance criterion is tested. Use when the backend, frontend, or mobile developer agent has a story with confirmed acceptance criteria, the relevant API spec, and the approved architecture constraints, and must turn that story into working, reviewable code.
---

# implement-feature

## Purpose

Turn one confirmed user story into working, tested, reviewable code in a feature branch. The test-first constraint forces the acceptance criteria to be machine-verifiable and blocks any story from being called done without automated proof. The skill enforces the XP rules that the developer agents cannot deviate from: a failing test exists before implementation, the code builds only what the acceptance criteria specify, and an architecture conflict stops the work rather than spawning a workaround.

## Inputs

| Field | Description |
|-------|-------------|
| `user_story` | The user story being implemented, read via spgr-read-artifact against the user-story schema. |
| `acceptance_criteria` | The confirmed Given/When/Then acceptance-criteria set for the story, read via spgr-read-artifact. Each criterion becomes a testable scenario. |
| `api_spec` | The relevant endpoints from the OpenAPI spec, read via spgr-read-artifact. The implementation conforms to this contract. |
| `architecture_constraints` | The approved ADRs and tech-stack-decision artifacts that bound the implementation, read via spgr-read-artifact. |
| `design_spec` | For frontend or mobile stories, the selected design direction the implementation follows. Optional for backend. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Acceptance test(s) | Failing acceptance test per criterion, written first via spgr-write-acceptance-test. Source code, not an envelope artifact. |
| Implementation | Source code that makes the acceptance and unit tests pass, written via spgr-write-file. |
| Unit tests | Unit tests for non-trivial logic, written via spgr-write-unit-test. Source code, not an envelope artifact. |
| Pull request | A pull-request envelope artifact opened via spgr-write-artifact, referencing the story and confirming every acceptance criterion is tested. |

## Procedure

1. Read the story, the confirmed acceptance criteria, the relevant API spec, and the architecture constraints with spgr-read-artifact. Validate each on read. If the acceptance criteria are absent, ambiguous, or unconfirmed, stop and call spgr-escalate with the precise list of missing or unclear criteria. Do not implement against assumed criteria.
2. Check the story against the approved architecture before writing any code. If the architecture cannot cleanly support the story, call spgr-escalate to surface the conflict and stop. Do not introduce a workaround that creates technical debt. For an open question in a vertical domain such as auth, security, or accessibility, call spgr-tag-vertical-agent before proceeding.
3. Create the feature branch with the naming convention `feature/<story-id>-<short-description>`.
4. Write the failing acceptance test first, one scenario per acceptance criterion, via spgr-write-acceptance-test. Run the suite with spgr-run-tests and confirm the new tests fail for the right reason. A test that passes before any implementation is wrong and must be corrected before continuing.
5. Write the implementation that makes the acceptance tests pass, via spgr-write-file. Conform to the API spec exactly and stay inside the architecture constraints. Build only what the acceptance criteria specify. If a candidate change would solve a problem outside the acceptance criteria, stop and raise it as a new story rather than building it.
6. Add unit tests for any non-trivial logic via spgr-write-unit-test. Trivial pass-through code does not need a unit test, but every branch in business logic does.
7. Run the full suite again with spgr-run-tests, then run the linter and formatter. For TypeScript or JavaScript, conform to `.claude/references/typescript-standards.md` and pass `tsc --noEmit`. The story is not ready until all acceptance tests pass, all unit tests pass, the linter passes, the formatter passes, and no new lint errors were introduced.
8. Run the story implementation checklist in Notes. Every item must be satisfiable with evidence before the pull request opens. Any unsatisfied item that cannot be resolved within the architecture is an escalation, not a waiver.
9. Open the pull request via spgr-write-artifact against the pull-request schema, with inline spgr-validate-artifact. Reference the story ID and list each acceptance criterion against the test that covers it. Record the implementation time against the story point estimate with spgr-log-decision so estimation accuracy can be refined over sprints.

## Notes

- Story implementation checklist, run before opening the pull request: acceptance tests written first and now passing, unit tests present for non-trivial logic, API contract followed, design spec followed (frontend and mobile), no YAGNI violation. Each answer must point to a file or a test.
- One logical change per commit. Keep the implementation commit separate from the failing-test commit so the test-first sequence is visible in history.
- The acceptance tests, the implementation, and the unit tests are source code verified by spgr-run-tests and CI, not by an envelope schema. Only the pull request is an envelope artifact, validated against its registered schema in schemas/ through spgr-validate-artifact.
- Read schema field requirements through spgr-validate-artifact and spgr-read-artifact rather than inlining them here.
- Escalation is not failure. Stopping on absent or contradictory acceptance criteria, or on an architecture conflict, and returning a precise list of what is wrong is the correct outcome.
