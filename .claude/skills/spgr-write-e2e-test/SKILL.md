---
name: spgr-write-e2e-test
description: Write an end-to-end test suite that drives the full application stack through complete critical user journeys, using Playwright for web and Detox or Maestro for mobile, with page objects, story-ID tags, hermetic per-test isolation, and failure-time screenshot, console, and network capture. Use when the QA agent owns the critical-journey coverage for a story marked as a P0 flow, or when a developer agent provides updated selectors or screen identifiers and the affected E2E tests must be rewritten to match.
---

# write-e2e-test

## Purpose

E2E tests answer the question unit and integration tests cannot: does the assembled system work for a user from UI through backend and back. They catch the bug class where every unit passes in isolation but the product fails for the user. Because they are slow and environment-dependent, reserve them for the critical journeys whose breakage is a P0 incident, and write each one to be hermetic, readable as user actions, and tagged to its source story so the suite stays clean as the product changes.

## Inputs

| Field | Description |
|-------|-------------|
| `user_stories` | The stories whose critical journeys this suite covers, read through spgr-read-artifact. A journey is critical only if its breakage stops a user getting the core value of the product. |
| `screen_flows` | The screen flow or wireframe sequence showing the expected UI steps for each journey. |
| `test_credentials` | Authentication and test-account credentials for the staging environment. |
| `selectors` | Page-object selectors from the frontend developer, or screen identifiers and navigation structure from the mobile developer. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `e2e_test_suite` | Source code. Playwright test files for web, or Detox tests or Maestro YAML flows for mobile, plus the page-object or screen-object layer. Written through spgr-write-file. |
| `test_run_report` | The journey pass/fail report with a screenshot or video and the console and network logs captured on each failure. |
| `journey_coverage_map` | The mapping from each story marked as a critical journey to its E2E test, surfacing any uncovered journey as a gap. |

## Procedure

1. Read each user story through spgr-read-artifact and confirm it is finalized. Read the screen flow for each journey. If a story is missing, still in draft, contradicts its screen flow, or names a journey with no test credentials, stop and raise an escalation through spgr-escalate with the precise list of what is missing rather than inventing the journey.
2. Select critical journeys only. Include sign up, the core primary workflow, payment, and key integrations. Exclude edge cases and error states that integration tests already cover. Record each include or exclude decision through spgr-log-decision so the scope is traceable.
3. For each selected journey, confirm an acceptance-criteria set exists through spgr-read-artifact. Write the failing E2E test before any page-object plumbing it depends on exists, following test-first order. Do not add coverage the acceptance criteria do not call for.
4. Write one test per critical journey covering the happy path end to end, plus one test for the single most common failure mode for that journey (for example incorrect password, checkout network timeout, expired session). Stop at the primary failure path. Additional failure modes belong in integration tests.
5. Build the page-object or screen-object layer first and route every selector through it. Write each test step as a user action ("clicks the submit button"), never as a raw DOM or element query. When a UI change breaks a test, fix the page object, not each test.
6. Make every test hermetic. Each test creates its own account, runs the journey, and cleans up after itself. Do not let a test read or write state another test produces. Tag each test with its source story ID for traceability and for removal when the story is deprecated.
7. Configure failure capture so every failure records a screenshot at the failure point, the full browser or device console log, and the network request log. A failure without these three artifacts is not debuggable from a nightly run.
8. Run the suite through spgr-run-tests against staging. Quarantine any test that fails intermittently by moving it to the non-blocking job at once, and record the quarantine through spgr-log-decision. A quarantined test must be fixed or deleted within the same sprint.
9. Build the journey coverage map: for each story marked as a critical journey, confirm a tagged E2E test exists, and surface any story with no test as a gap for the sprint dashboard.
10. Write the suite and the page-object layer through spgr-write-file, which enforces read-before-write and verifies the post-write checksum. On a nightly failure, notify the QA agent and the relevant vertical agent through spgr-tag-vertical-agent, and file the result as a P1 bug. A nightly E2E failure does not block merges.

## Notes

- The E2E suite is source code. Its correctness is verified by spgr-run-tests and by the nightly CI run against staging, not by an envelope schema.
- The test run report, the journey coverage map, and any flakiness report are not yet in the schema registry at /Users/gunderer/Repos/springer/schemas/. Write each through spgr-write-artifact once its registered schema is added in a later increment.
- A bug filed from a nightly failure is a bug-report artifact, which is in the registry. Write it through spgr-write-artifact with inline spgr-validate-artifact.
- E2E tests run nightly against staging, not on every commit. Keep each commit to one logical change and lint and format the suite clean before committing.
- Later increments add visual regression checks (screenshot comparison) alongside the functional assertions, and parallel execution (Playwright sharding, Detox parallel workers) to hold the nightly run under fifteen minutes as the journey count grows.
