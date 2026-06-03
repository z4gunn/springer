---
name: spgr-detect-test-flakiness
description: Produce a flakiness report from CI test run history that identifies non-deterministic tests, classifies each by likely root cause, ranks them by failure rate and CI cost, and emits quarantine recommendations with a hard remediation deadline. Use when the QA, developer, or code-reviewer agent has at least 30 consecutive CI runs and must find, triage, and quarantine tests that fail non-deterministically before flaky failures train the team to ignore real ones.
---

# detect-test-flakiness

## Purpose

A flaky test is a test that lies. It sometimes reports broken code that works, and sometimes reports working code that is broken. Accumulated flaky tests train agents and developers to ignore failures, which means real failures get ignored too. Detect flakiness systematically from CI history, quarantine flaky tests immediately so they stop blocking merges, and treat quarantine as triage with a hard deadline, never a permanent state. A quarantined test not fixed within its quarantine sprint is unresolved test debt and is deleted.

## Inputs

| Field | Description |
|-------|-------------|
| `ci_run_history` | At least 30 consecutive CI runs, 50 or more preferred for lower-frequency flakes. Per-test records of name, run timestamp, pass or fail status, and failure message. |
| `result_format` | JUnit XML, JSON, or CSV holding the per-test records above. |
| `retry_telemetry` | Per-run record of every test retry, not just the final pass or fail. Tests that pass only after a retry are treated as flaky. |
| `run_metadata` | Per-run environment tags: parallelism level, runner specs, time of day. Required to diagnose load-sensitive and time-sensitive flakes. |
| `sprint_boundary` | The current sprint end date, used to set each quarantine remediation deadline. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `flakiness-report` | Summary (tests analyzed, flaky count, flakiness rate, estimated CI time wasted by reruns), ranked flaky tests with failure rate, failure pattern, and root-cause category, quarantine recommendations, and the per-test remediation deadline. Written via spgr-write-artifact. |
| Quarantine moves | For each test at or above the 5% threshold, the test moved to the quarantine CI job and a remediation ticket created. Source-code and CI-config changes written via spgr-write-file. |

## Procedure

1. Read the run history, retry telemetry, and run metadata with spgr-read-file. If fewer than 30 consecutive runs are present, stop and raise spgr-escalate naming the run count short and the minimum required, because the sample is below statistical significance.
2. For each test, compute the failure rate as failures divided by total runs. Count a retry-then-pass as a failure for this calculation, since it carries the same CI cost and hides real failures.
3. Classify each test by failure rate. At or above 5% over 30 or more runs is definitively flaky and must be quarantined. From 1% up to 5% is suspected flaky: flag it for monitoring with additional run data, do not quarantine yet.
4. Detect the failure pattern for each flaky test from the run records and metadata: passes on retry, fails under concurrent load, fails at specific times of day, or fails only after a specific other test runs.
5. Assign a root-cause category and remediation approach from the catalog below. For a timing dependency the fix is an explicit assertion with a retry or a waitFor that polls a condition, never an arbitrary sleep.
6. Rank flaky tests by failure rate and CI cost. Compute the summary metrics and the estimated CI time wasted by reruns.
7. For each test at or above the 5% threshold, move it to the quarantine CI job with spgr-write-file and create the remediation ticket automatically. No manual step. The quarantine job runs on the same schedule but does not block merges or deployments. Quarantine is not deletion: the test keeps running so its failure data accumulates and confirms when remediation is complete.
8. Set each quarantined test a remediation deadline at the end of the current sprint. Record that a test not fixed or deleted by that date is deleted, not extended.
9. Un-flag any previously quarantined test that is now stable across the analyzed window and return it to the main suite.
10. Write the flakiness report with spgr-write-artifact. Validate inline with spgr-validate-artifact against the registered schema. Record consequential calls, such as the chosen failure-rate threshold or a deletion recommendation, with spgr-log-decision.
11. If a quarantined test reaches its deadline unfixed, escalate the delete-or-fix decision with spgr-escalate rather than silently extending quarantine.

## Root-cause catalog

- Timing dependency. Test assumes a specific order of async operations. Fix with an explicit assertion that retries or a waitFor that polls until the condition holds. An arbitrary sleep keeps the test slow and still flaky under load.
- Shared state. Test mutates global state or a shared database row that other tests touch. Fix with isolation: reset between tests or use a per-test transaction.
- Network dependency. Test makes real calls to external services. Fix by mocking the call or using a WireMock stub.
- Order dependency. Test passes only after a specific other test runs. Fix by making each test fully self-contained.
- Resource exhaustion. Test fails under concurrent execution from connection-pool or file-handle limits. Fix with pool sizing or reduced test parallelism.

## Notes

- Run flakiness detection weekly on a rolling window so new flakes are caught as they appear and recovered tests are un-flagged.
- The remediation deadline is a hard rule: fix or delete within the quarantine sprint. Quarantine indefinitely is test-debt accumulation. A test that is consistently flaky and cannot be fixed is almost always badly designed, so delete it and replace it with a more deterministic test of the same behavior.
- Surface the flakiness backlog as a quality metric over time: total flaky count, remediations completed per sprint, and average time in quarantine before fix or deletion. Emit these trend metrics into the report summary.
- The flakiness-report type is not yet in the registered envelope schema. Write it via spgr-write-artifact with its registered schema added in a later increment, and validate inline with spgr-validate-artifact once that schema lands.
- Quarantine CI-job config and test-file edits are source code, verified by spgr-run-tests and CI rather than by an envelope schema.
- This skill detects and triages flakiness only. The actual test rewrite for each remediation belongs to the relevant test-authoring skill (for example spgr-write-unit-test or spgr-write-integration-test).
