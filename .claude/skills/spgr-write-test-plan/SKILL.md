---
name: spgr-write-test-plan
description: Produce a test-plan artifact defining the full testing strategy for a release or sprint, covering scope, a per-type test matrix, coverage targets by layer, entry and exit criteria, and a test-data strategy. Use when the QA Agent starts a release or sprint and developers need the blocking quality contract before they write code.
---

# write-test-plan

## Purpose

Write the test-plan artifact that fixes what testing means for a release before any implementation code exists. In the XP discipline Springer follows, the test plan is a first-class artifact and a blocking dependency for the backend, frontend, and mobile developer agents, who do not begin implementation until it is confirmed. The contract here is that every NFR maps to a test type and target, every risk area gets coverage beyond the baseline, and coverage is stated per layer rather than as one project-wide number that hides the gaps. A test plan that lists wishes instead of testable targets fails its job.

## Inputs

| Field | Description |
|-------|-------------|
| `story_backlog` | All stories in scope for the release or sprint, each with a story ID |
| `nfrs` | Non-functional requirements by ID, covering performance, security, and availability targets |
| `risk_areas` | High-risk areas named by the Architect or PM Agent, for example authentication, billing, data integrity |
| `deployment_model` | Container, serverless, mobile, or other target that shapes which test types apply |
| `environment_inventory` | Available environments and test databases (dev, staging, prod, test) plus CI pipeline constraints from DevOps |

## Outputs

| Artifact | Description |
|----------|-------------|
| `test-plan` | Envelope artifact holding scope, test type matrix, coverage targets, risk-weighted coverage, entry criteria, exit criteria, environment requirements, and test data strategy |

## Procedure

1. Read each input through spgr-read-file for raw files and spgr-read-artifact for upstream artifacts (story backlog, NFRs, risk areas). Validate each upstream artifact against its schema before consuming it.
2. Define scope. Name the stories, features, and system boundaries under test, and record every in-scope story ID in `story_refs`. Pull these from the machine-readable backlog where one exists rather than retyping them.
3. Build the test type matrix. For each applicable type from unit, integration, e2e, performance, security, accessibility, contract, and smoke, state the tooling, the owner agent, the run frequency, and the environment. Drop a type only when the deployment model makes it inapplicable, and say why in the decision log. Map security to SAST plus DAST and accessibility to the WCAG level from the NFRs.
4. Set coverage targets per layer, not as one number. State separate targets for business logic (unit), service boundaries (integration), user journeys (e2e), and NFR validation (performance, security). Each target is a measurable threshold a CI gate can check, for example "90% branch coverage on business logic" or "100% of acceptance criteria covered by integration tests."
5. Apply risk-weighted coverage. For each risk area, list the additional test types beyond the baseline. A risk area gets at minimum one extra type, for example authentication carries unit plus integration plus security rather than unit alone.
6. Trace every NFR to a test type and target. If an NFR has no corresponding test, it is not a requirement and must be flagged, not silently dropped. Record the story-to-test traceability so gap analysis is fast: map each story ID to the acceptance, integration, and e2e tests that cover it.
7. Write entry and exit criteria. Entry criteria are the conditions that must hold before testing begins on a story, including acceptance criteria written and acceptance tests written and failing before implementation, per test-first discipline. Exit criteria are the conditions for done, including all acceptance tests passing, no P0 or P1 bugs open, and coverage targets met.
8. State environment requirements concretely. Specify the test database provisioning and seeding strategy, external service mocking or sandboxing, and secrets handling in test environments. Reject aspirational phrasing such as "we will need a test database." Define the test data strategy: fixture factories, anonymized production data policy, and synthetic data generation.
9. Produce the artifact with spgr-write-artifact, which stamps the shared envelope, records per-section confidence, initializes the decision log, and runs spgr-validate-artifact against the registered test-plan schema inline before write. Do not hand-build the envelope.
10. Log each consequential choice (a dropped test type, a coverage target, a risk weighting) with spgr-log-decision so the reasoning is traceable.
11. If inputs are missing or contradictory, an NFR cannot be made testable, or a story carries no acceptance criteria to test against, stop and raise spgr-escalate with a precise list of what is missing or conflicting rather than inventing a target. When the plan is ready for the developer agents to begin, surface it through spgr-notify-human if a gate requires confirmation.

## Notes

- The test-plan artifact type is registered in the schema registry at `schemas/` as `test-plan-v1.json`. Reference field requirements through spgr-validate-artifact rather than inlining them here.
- The test plan is a living document for the release. When a story is added mid-sprint, revise the plan with spgr-version-artifact so coverage and traceability stay current rather than drifting.
- A test type without an owner agent or an NFR without a matching target is an incomplete plan, not a confirmed one. Mark the section proposed and confirm it before developers begin.
- This skill produces the entry-and-exit contract that spgr-run-tests and CI enforce. Coverage targets declared here are the thresholds the CI gate fails the build against. Acceptance criteria referenced by entry criteria come from spgr-write-acceptance-criteria.
