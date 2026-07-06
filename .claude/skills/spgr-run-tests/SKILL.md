---
name: spgr-run-tests
description: Execute a test suite against a target environment, capture pass/fail counts, coverage, and per-failure diagnostics, and exit non-zero on any failure or coverage-floor breach. Use when a QA, developer, or DevOps agent needs to run tests locally, in CI, or as a deployment gate, with enough output to locate every failure without a re-run.
---

# run-tests

## Purpose

Run a test suite and return a result the calling agent or pipeline can act on without ambiguity. Test execution is the heartbeat of the XP feedback loop, so the result is a failure count (zero on a clean run), a coverage percentage, and enough diagnostic output to locate every failure on the first read. The exit code is a hard contract with the caller. A non-zero exit means the build is not green, and that signal is never softened to let a known failure pass. Suites that exceed the XP ten-minute build rule are flagged for a fast/slow split rather than left to grow.

## Inputs

| Field | Description |
|-------|-------------|
| `suite` | Which suite to run: unit, integration, e2e, load, or all |
| `target_environment` | Where to run: local, ci, or staging |
| `filter` | Optional test filter pattern, a story-ID tag or a path pattern |
| `selection_mode` | Optional: full, or changed for smart selection from the diff coverage map |

## Outputs

| Artifact | Description |
|----------|-------------|
| Result summary | One-line first: total run, passed, failed, skipped, duration (e.g. "128 passed, 2 failed, 3 skipped in 47.2s") |
| Coverage report | Branch and line coverage by module, written as HTML and a machine-readable file alongside the run |
| Failure details | Per failing test: name, failure message, stack trace, and for e2e the screenshot or video artifact |
| Exit code | Non-zero if any test fails or coverage falls under the hard floor, otherwise zero |
| Split recommendation | When total runtime exceeds 10 minutes, the slow subset and a proposed fast/slow split |

## Procedure

1. Read the test plan with spgr-read-artifact to get the coverage targets and the hard coverage floor for this project. If the test plan is missing or has no declared coverage targets, escalate with spgr-escalate rather than assuming a floor.
2. Resolve the suite and filter into a concrete command for the project's test runner. When `selection_mode` is changed and the branch carries a small diff, map the changed files to their covering tests through the coverage map and run only that subset. Fall back to the full suite on merge or when no map exists.
3. Run the suite. Capture stdout, stderr, the coverage data, and any e2e screenshot or video artifacts.
4. Emit output in the fixed structure so agents can parse it: the one-line summary first, then the coverage table, then the detailed failure output. Do not reorder these sections.
5. Compare coverage against the test plan. Coverage below a declared target prints a warning in the output. Coverage below the hard floor sets a non-zero exit even when every test passed.
6. If total runtime exceeds 10 minutes, produce the fast/slow split recommendation. Unit tests are the fast tier and target under 3 minutes on every commit. Integration is the medium tier and targets under 10 minutes on every merge. E2e and load are the slow tier for nightly runs.
7. Quarantine, never soften. Tests known to fail and tests known to be flaky are moved to a separate non-blocking job and excluded from the main suite. The main suite exits zero only when all of its tests pass. Report a flaky test's flakiness rate separately and hand flakiness investigation to spgr-detect-test-flakiness.
8. Set the exit code last: non-zero if any main-suite test failed or the coverage floor was breached, otherwise zero. The caller (CI stage, pre-commit hook, deployment gate) depends on this contract.
9. When running in CI, capture every artifact (coverage HTML, failure screenshots, logs) as a CI artifact with at least a 7-day retention. An artifact that disappears before an agent can investigate a failure is worse than none.
10. When a test carrying a story-ID tag fails in CI, write the failure summary back to that story or ticket so the failure is visible at the work item.

## Notes

- The output is source-level execution output and project files (the coverage report, captured artifacts), verified by the exit-code contract and CI rather than by an envelope schema. Write any captured files with spgr-write-file.
- A standalone flakiness report or a test-result trend record is an artifact type not yet in the registered schema list. When one is produced, write it via spgr-write-artifact with its registered schema added in a later increment, and route flakiness analysis to spgr-detect-test-flakiness.
- Escalation cases for spgr-escalate: a missing or target-less test plan, a test runner that cannot start in the target environment, and a coverage map requested for changed-file selection that does not exist when the caller required it.
- Never edit a failing test to make the suite green. Report the failure. Fixing the code or the test is the calling agent's decision under test-first discipline.
