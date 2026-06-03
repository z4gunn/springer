---
name: spgr-refactor
description: Improve the internal structure of a code section without changing its external behavior, using the existing test suite as the safety net and applying XP simple-design rules in priority order. Use when the Backend, Frontend, or Mobile Developer agent has a clear refactor goal (extract method, eliminate duplication, simplify a conditional, rename for clarity) on a covered code section, or when the Code Reviewer agent identifies a complexity hotspot that should be reduced before it becomes a bottleneck.
---

# refactor

## Purpose

Restructure a named code section so it reveals intent and carries less complexity, while the test suite proves external behavior is unchanged. A refactor is structural only. It never changes behavior and never changes a public interface in the same step. The test suite is the contract that makes the change safe, so refactoring without adequate coverage is not allowed. This keeps the codebase at a complexity level where downstream agents can work confidently.

## Inputs

| Field | Description |
|-------|-------------|
| `target` | The specific file, module, or class to refactor, read via spgr-read-file before any change |
| `goal` | The refactor goal stated clearly (extract method, eliminate duplication, simplify conditional, rename for clarity) |
| `test_suite` | The test suite covering the target, run via spgr-run-tests both before and after the refactor |

## Outputs

| Artifact | Description |
|----------|-------------|
| Refactored source files | Structurally improved code, written via spgr-write-file, with the test suite passing before and after and no behavior change |

## Procedure

1. Read the target section via spgr-read-file and confirm the stated goal is a pure structural change. If the goal requires a public interface change (method signature, API, component props), stop. That is not a refactor. Escalate via spgr-escalate so it gets the same review and communication as any interface change.
2. Run the full test suite via spgr-run-tests and confirm it passes before any edit. This is the baseline that proves behavior. If it fails, stop and report. Do not refactor on a red suite.
3. Assess coverage on the target. If coverage is not adequate to detect a behavior change, do not refactor yet. Add the missing tests first via spgr-write-unit-test (or the integration equivalent), confirm they pass, then return to step 2.
4. Apply the refactor in small focused edits via spgr-write-file. Follow XP simple-design rules in priority order: (1) passes all tests, (2) reveals intention clearly, (3) no duplication, (4) fewest elements. Stop when all four are satisfied. Do not add structure the goal does not call for.
5. Run lint and format on the changed files and resolve every issue so the result is clean before commit.
6. Run the full test suite again via spgr-run-tests. It must pass with the same results as the baseline. If a test now fails, the change altered behavior. Revert the edit and narrow the refactor.
7. If the refactor reveals a bug, do not fix it here. Record it via spgr-write-bug-report and fix it in a separate commit with its own test. A refactor commit never also changes behavior.
8. Log the structural decision via spgr-log-decision, then commit the refactor as one logical change separate from any feature or fix work.

## Notes

- The output is source code, verified by spgr-run-tests and CI rather than by an envelope schema.
- One commit is one logical change. Never combine a refactor with a behavior change or a bug fix.
- Keep the change small. A refactor that touches hundreds of files is a merge-conflict and review burden, so split it.
- A complexity metric (cyclomatic or cognitive complexity) in CI flags refactor candidates before they become critical-path bottlenecks. Treat a flagged hotspot as a candidate goal, not as license to refactor uncovered code.
- Track refactor work as explicit sprint-backlog stories, not as incidental work folded into feature commits.
- An interface-changing edit is out of scope here. Route it via spgr-escalate to the developer flow that owns interface changes.
