---
name: spgr-implement-api-endpoint
description: Implement one REST or GraphQL endpoint as backend source code that matches the approved API spec exactly, with request validation, business logic, spec-defined error handling, response serialization, auth-first middleware, and rate-limit headers, plus contract tests and timed endpoint tests. Use when the Backend Developer agent picks up an endpoint from the API spec to implement, or when the QA or code-reviewer agent needs the endpoint built against its confirmed contract and acceptance criteria before review.
---

# implement-api-endpoint

## Purpose

Implement a single endpoint so that its behavior is faithful to the approved API spec, no more and no less. Strict adherence to the contract is what makes parallel backend and client development safe, so this skill builds nothing the spec does not define and exposes nothing the spec does not document. The output is source code, not an envelope artifact. Correctness is proven by failing-then-passing contract and endpoint tests under spgr-run-tests and CI.

## Inputs

| Field | Description |
|-------|-------------|
| `api-spec-entry` | The specific endpoint or operation from the OpenAPI 3.1 spec produced by spgr-write-api-spec. Read with spgr-read-artifact. Defines parameters, request and response schemas, status codes, auth, and rate-limit headers. |
| `data-model` | Entity and field definitions from the ERD and data dictionary (spgr-generate-erd, spgr-write-data-dictionary). Read with spgr-read-artifact. |
| `auth-model` | Identity and access decisions from the architecture ADR and auth model (spgr-design-auth-model, spgr-write-rbac-policy). Read with spgr-read-artifact. |
| `acceptance-criteria` | The Given/When/Then set for the parent story (spgr-write-acceptance-criteria). Defines the scope to build and nothing beyond it. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Endpoint implementation | Source code written with spgr-write-file: request validation at the API boundary, business logic, error handling for every spec-defined error case, and response serialization matching the spec schema. |
| Contract test | Consumer-driven contract test generated from the spec via spgr-write-contract-test, so spec drift fails in CI. |
| Endpoint tests | Integration and unit tests via spgr-write-integration-test and spgr-write-unit-test, including response-time assertions wired to the relevant NFR target. |

## Procedure

1. Read the api-spec-entry, data-model, auth-model, and acceptance-criteria with spgr-read-artifact. Read existing route, service, and serializer files with spgr-read-file before writing, to honor the read-before-write contract and match existing patterns.

2. Validate the inputs before building. Confirm the spec entry names every parameter with its required or optional flag, type, and format, all status codes, the response schema, the auth requirement, and the rate-limit headers. If any of these is missing, contradictory, or the data-model and spec disagree on a field, stop and raise spgr-escalate with the precise gap. Do not fill the gap with an assumption.

3. Write the failing tests first. Generate the contract test from the spec with spgr-write-contract-test. Write integration tests for the happy path, every spec-defined error case, and boundary conditions with spgr-write-integration-test, and unit tests for the business logic with spgr-write-unit-test. Include a response-time assertion in the endpoint tests, wired one-to-one to the parent NFR latency target. Run spgr-run-tests and confirm the new tests fail before any implementation exists.

4. Implement only what the acceptance criteria and the spec entry require (YAGNI). Order the request pipeline so auth enforcement is the first middleware, before any other processing. Validate all input at the API boundary before business logic runs, so invalid input never reaches the service layer. Implement the business logic, then serialize the response to match the spec schema exactly, with no undocumented fields.

5. Handle every error case the spec defines, returning only the spec-listed status codes and the spec's error envelope. Never expose internal error details to the caller. Log the internal error with context, return a sanitized message. Include the rate-limit headers on every response, including responses that do not approach the limit.

6. Run spgr-run-tests and confirm the contract test, integration tests, and unit tests all pass and the response-time assertion holds. Run lint and format and confirm both are clean before commit. For TypeScript or JavaScript, conform to `.claude/references/typescript-standards.md` and pass `tsc --noEmit`.

7. Confirm the implementation matches the spec exactly: no endpoint not in the spec, no status code not in the spec, no field not in the spec. If the spec cannot satisfy the requirement, do not deviate silently. Raise spgr-escalate to request a spec change with versioning through spgr-version-artifact, and consult the API Design vertical with spgr-tag-vertical-agent. Record any consequential implementation choice with spgr-log-decision.

## Notes

- The output is source code verified by spgr-run-tests and CI, not an envelope artifact with a registered schema. The contract test and endpoint tests are the proof of conformance.
- One logical change per commit. Lint and format must be clean before commit.
- Read schema and field definitions through spgr-read-artifact and spgr-validate-artifact against the registry at schemas/ rather than inlining field lists here.
- A deviation from the spec is a spec change, never a silent implementation difference. The spec stays the single source of truth for backend and every client surface.
