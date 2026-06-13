---
name: spgr-write-integration-test
description: Produce an integration test suite that verifies component and service interactions at real system boundaries, covering API endpoints against a running service, repository reads and writes against a real test database, service-to-service contracts at the real interface, and error boundaries, with per-test isolation and environment-injected configuration. Use when the QA or Backend Developer agent has an API spec, service boundary definitions, and data contracts and must catch contract drift, schema migration errors, and boundary marshaling bugs that unit tests cannot, or when the API Design agent reviews that the tests match the published spec.
---

# write-integration-test

## Purpose

Write tests that exercise the seams between components rather than functions in isolation. These tests confirm the database schema matches what the ORM expects, the API handler serializes the domain object correctly, and a consumer processes events in the format a producer emits. Integration tests hit real infrastructure, a test database and real test-environment instances of dependent services, because mocking at this level defeats the purpose and has historically missed every interesting class of integration failure. Write them test-first, before or alongside the implementation they cover, and build only the cases the acceptance criteria specify.

## Inputs

| Field | Description |
|-------|-------------|
| `api_spec` | OpenAPI spec for the endpoints or interfaces under test. |
| `service_boundaries` | Which services own which data and which service calls which. |
| `data_contracts` | Request and response schemas, event payload schemas. |
| `db_schema` | Database schema or current migration state. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Integration test files | Source code covering API endpoint tests against a running test service, database interaction tests against a real test database, service-to-service contract tests at the real interface, and error boundary tests, plus a database setup and teardown mechanism that isolates each run. |

## Procedure

1. Read the API spec, service boundary definitions, and data contracts with spgr-read-artifact, and read the current schema or migration files with spgr-read-file. If a contract or boundary needed to write a test is missing or contradicts another input, stop and raise it with spgr-escalate rather than guessing the interface shape.

2. Read the acceptance criteria for the story under test with spgr-read-artifact, or call spgr-write-acceptance-criteria when they are absent. Scope the suite to those criteria. Do not add tests for behavior the criteria do not specify.

3. Write each test as a failing test first, before the implementation it covers exists or is complete, then confirm it passes once the implementation lands. Run the suite with spgr-run-tests at each step.

4. Write API endpoint tests as real HTTP calls against a running test service. Cover the nominal success path, authentication for authenticated versus unauthenticated requests, authorization where a correct role is allowed and an incorrect role receives 403, and input validation for malformed bodies, missing required fields, and oversized payloads. Verify request parsing, business logic invocation, response serialization, and the correct HTTP status code per case.

5. Write database interaction tests that confirm repository or DAO implementations read and write a real test database in the expected schema. Provision the test database through the IaC and seed it with fixture factories before each run.

6. Write service-to-service tests against the real callee interface, not a mock, and confirm the request and response formats match the spec. The one exception is an external third-party service (payment processor, email or SMS provider). Use the provider sandbox or test account where one exists, or verify the integration with a separate contract test.

7. Write error boundary tests that drive boundary failures, a downed database, an upstream timeout, a malformed request, and confirm each is handled gracefully with the correct error response.

8. Make each test reset or clean its own state, or rely on a full database reset between runs. Never assume state left by a prior test, since shared state is the primary cause of order-dependent failures.

9. Inject all environment configuration, database connection strings and service URLs, through environment variables. Never hardcode a connection string or URL in a test file.

10. Generate a baseline endpoint test scaffold from the API spec and fill in the business logic assertions by hand. Add a contract diff check that compares the suite against the current API spec on every spec change and flags tests that no longer match. Add parallel execution with database sharding when the suite runtime grows past the target.

11. Run the full suite, lint, and format with spgr-run-tests and confirm clean before write. For TypeScript or JavaScript, conform to `.claude/references/typescript-standards.md` and pass `tsc --noEmit`. Write each test file through spgr-write-file. Record any non-obvious test design choice with spgr-log-decision. When a case touches a vertical's domain, an authorization rule or a data-exposure boundary, consult that specialist with spgr-tag-vertical-agent before treating the section as done.

## Notes

- The output is source code verified by spgr-run-tests and CI rather than by an envelope schema. Integration tests run in CI on every merge to main and need not run on every local commit. Expect a 1 to 5 minute runtime for a typical service.
- The contract diff result and any flakiness report are written via spgr-write-artifact with a registered schema added in a later increment.
- Commit one logical change per commit, lint and format clean.
