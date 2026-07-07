---
name: spgr-write-api-design-standards
description: Produce an api-design-standards artifact that fixes the project-level conventions every endpoint must follow, covering naming, verb semantics, response envelopes, pagination, status codes, and reusable OpenAPI component templates. Use when the API Design Agent sets the API constitution before any endpoint is specified or built.
---

# write-api-design-standards

## Purpose

Establish the one document that answers "how should this be designed?" before the question arises on any specific endpoint. The api-design-standards artifact replaces per-endpoint judgment calls with documented conventions, so the API surface is predictable for consumers and reviewable for the API Design Agent. It is the foundation that spgr-review-api-consistency checks against, and it emits OpenAPI component templates so implementation matches the standard by construction rather than by later correction.

Operate as the API Design vertical in consultant and gate mode. The standards are authored once and enforced thereafter. A recurring per-endpoint naming debate is a symptom of an undefined or unread standard, not a signal to relitigate a settled rule.

## Inputs

| Field | Description |
|-------|-------------|
| `api_type` | REST, GraphQL, gRPC, or mixed. |
| `product_context` | Internal API, public third-party API, mobile API, or partner API. Drives strictness of identifier and error-code rules. |
| `existing_conventions` | Current API conventions when extending an existing API. Optional. When present, reconcile rather than overwrite. |

Read inputs with spgr-read-file, and read any upstream artifact (tech-stack-decision, api-spec) with spgr-read-artifact before authoring.

## Outputs

| Artifact | Description |
|----------|-------------|
| `api-design-standards` | Envelope artifact written with spgr-write-artifact. Carries the standards sections below, an inline OpenAPI component template block, a confidence map, and a decision log. |

Required standards sections:
- URL design. Resource naming as plural nouns in kebab-case, nesting depth limit of two, query parameter naming.
- HTTP verbs. Correct GET, POST, PUT, PATCH, DELETE semantics, with idempotency requirements stated per verb.
- Response envelope. Standard success shape (`data`, `meta`, `links`) and standard error shape (`code`, `message`, `details`).
- Pagination. Cursor-based as the default, offset-based only where ordering is stable, page-size defaults and limits, the pagination response envelope.
- Identifiers. UUID v4 for all resource IDs. Never expose auto-increment IDs in a public API.
- Timestamps. ISO 8601 UTC for all timestamps, with consistent field naming (`created_at`, `updated_at`).
- HTTP status codes. When to use 200, 201, 204, 400, 401, 403, 404, 409, 422, 429, 500.
- Error codes. A machine-readable error-code scheme (for example `VALIDATION_FAILED`, `RESOURCE_NOT_FOUND`).
- OpenAPI templates. The success and error envelope and the pagination shape rendered as reusable `$ref` components.

## Procedure

1. Read `api_type`, `product_context`, and `existing_conventions`. If `api_type` is missing or contradictory, or `product_context` is absent, stop and raise spgr-escalate with the precise list of what is missing rather than assuming a default. Do not author standards against an unknown surface.
2. When `existing_conventions` is present, reconcile each existing rule against the standard. Where an existing convention conflicts with a standard rule, record both, recommend one, and mark the field `needs-human-input` if the conflict carries migration cost for existing consumers.
3. Author each standards section above. Set pagination default to cursor-based for any resource that accepts writes during pagination, because offset pagination returns inconsistent results when items are inserted or deleted mid-page. Allow offset only where ordering is stable and the dataset is bounded.
4. Define the error envelope with a machine-readable `code` field and a human-readable `message` field. Do not let an HTTP status code be the only error classification, because status codes are too coarse-grained to drive consumer logic.
5. Generate the OpenAPI component templates. Express the success envelope, the error envelope, and the pagination shape as reusable `$ref` components so downstream api-spec work references them rather than re-declaring shapes.
6. Set the confidence map. Mark each section `confirmed`, `proposed`, or `needs-human-input`. A reconciliation conflict or any rule with consumer-breaking impact is `needs-human-input`.
7. Write the artifact with spgr-write-artifact and run spgr-validate-artifact inline. On a validation failure, correct the artifact and revalidate before returning. Do not return an artifact that has not passed validation.
8. Record each consequential choice (pagination default, identifier policy, error-code scheme) with spgr-log-decision, capturing the rationale and the alternative rejected.
9. When this standard is a recommendation to a horizontal agent (for example the Backend Developer adopting the envelope), route it through spgr-tag-vertical-agent as a consultation. Do not edit another agent's artifact directly.
10. When the artifact carries any `needs-human-input` field, raise it to the human with spgr-notify-human so the contested rule is decided before downstream endpoints adopt it. On revision after first write, stamp the version with spgr-version-artifact.

## Notes

- Output type is a spec or policy envelope artifact (`api-design-standards`), written via spgr-write-artifact with inline spgr-validate-artifact. Its content schema is not registered yet, so envelope-only validation (header, confidence map, decision log, version) applies for now and a content schema is registered in a later increment.
- The standards are immutable once confirmed in the same sense an ADR is. A consumer of this artifact that cannot satisfy a rule escalates rather than deviating silently.
- spgr-review-api-consistency reads this artifact as its rule source. Keep section names stable so the review skill can map findings back to a named rule.
