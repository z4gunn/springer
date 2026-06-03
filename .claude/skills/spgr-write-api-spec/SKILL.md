---
name: spgr-write-api-spec
description: Produce a complete OpenAPI 3.1 spec that is the binding contract between the backend and every client surface, with every endpoint, request and response schema, per-endpoint auth, rate-limit headers, a consistent pagination pattern, and a versioning strategy. Use when the Architect or API Design agent has resource definitions, operations, an auth model, and an error format and must define the API contract before any backend or client implementation begins, so backend and frontend or mobile work can proceed in parallel against one source of truth.
---

# write-api-spec

## Purpose

Write the API contract that backend and all client agents build against before any of them write code. The spec removes ambiguity so backend and client surfaces cannot diverge on assumptions, and it unlocks parallel development once confirmed. The contract is immutable once confirmed. A breaking change is a new API version, not an edit to the confirmed spec.

## Inputs

| Field | Description |
|-------|-------------|
| `resources` | Entities exposed by the API. |
| `operations` | CRUD and business operations per resource. |
| `auth_model` | JWT, OAuth 2.0, API key, session, or similar. |
| `error_format` | Error envelope structure, error codes, and message shape. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `api-spec` | OpenAPI 3.1 YAML covering every endpoint, request schema (path params, query params, headers, body), success and error response schemas, HTTP status codes per operation, per-endpoint auth, rate-limit headers, the pagination pattern, and the versioning strategy. |

## Procedure

1. Read the upstream architecture and data artifacts with spgr-read-artifact to ground resources, operations, and field types. Confirm the auth model and error format are supplied. If any of the four inputs is missing or contradictory, stop and raise it with spgr-escalate rather than inventing a default.

2. Define one OpenAPI 3.1 path-and-operation entry for every operation. Do not collapse similar operations. An entry of "similar to the above" is not valid. Each operation states its full request shape and every HTTP status code it can return.

3. Specify every error response as completely as the success response. Model the supplied error envelope as a reusable component and reference it from each error status code so clients can handle failures.

4. Set auth requirements explicitly on each endpoint from the supplied auth model. Do not rely on a global default to imply per-endpoint behavior.

5. Add the rate-limit response headers `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` to every endpoint.

6. Apply one pagination pattern across all list endpoints. Prefer cursor-based pagination over offset for large datasets, and keep the parameter and response shape identical on every list endpoint.

7. State the versioning strategy in the spec (for example a path or header version). Record the strategy choice and any non-obvious modeling decision with spgr-log-decision.

8. When the auth model, an error code carrying security meaning, or a data-exposure question falls in a vertical's domain, consult that specialist with spgr-tag-vertical-agent before treating the affected section as confirmed.

9. Validate the spec with OpenAPI tooling and Spectral linting before write. Resolve every lint finding, including incomplete or duplicated entries. Write the validated YAML through spgr-write-artifact.

10. Generate contract-testing stubs (Pact or similar) from the confirmed spec, and wire the Spectral lint into CI so later edits cannot land an incomplete or off-style entry.

11. The confirmed spec is immutable. When a change is breaking, create a new API version with spgr-version-artifact rather than editing the confirmed spec in place.

## Notes

- The api-spec is OpenAPI 3.1 YAML validated by OpenAPI tooling and Spectral, not by an envelope JSON Schema. It is written via spgr-write-artifact, and a registered envelope schema is added in a later build increment.
- Schema field types for request and response bodies trace to the data dictionary and ERD artifacts. Read them through spgr-read-artifact rather than restating field lists here.
