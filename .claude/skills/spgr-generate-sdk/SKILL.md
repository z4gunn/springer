---
name: spgr-generate-sdk
description: Generate a typed client SDK from the validated OpenAPI spec for one or more target languages, with typed models, auth, pagination, error classes, a quickstart, and contract tests against staging. Use when the Documentation Agent regenerates SDKs after an API spec change, or when the DevOps Agent needs SDK packages built before publishing.
---

# generate-sdk

## Purpose

Produce a typed client SDK per target language from the confirmed OpenAPI spec, so a consumer can install the package and call the API with full type safety instead of constructing HTTP requests by hand. The SDK is generated from the spec, not hand-maintained, so it is regenerated when the API changes rather than patched. The Documentation Agent owns this work as a vertical specialist. The output is source code, so write the SDK files through `spgr-write-file` and verify them with contract tests against staging rather than emitting an envelope artifact for the SDK itself.

## Inputs

| Field | Description |
|-------|-------------|
| `openapi-spec` | The validated OpenAPI spec, read through `spgr-read-file` or, if registered as an artifact, `spgr-read-artifact`. This is the single source for models, endpoints, and errors. |
| `target-languages` | The languages to generate, chosen by primary consumer audience (TypeScript or JavaScript, Python, Swift, Kotlin, Go). |
| `naming-and-packaging` | SDK naming conventions and package organization preferences (package name, namespace or module layout). |
| `auth-flow-type` | The authentication flow the SDK must support (API key or OAuth), which sets how the auth module handles credentials, header injection, and token refresh. |
| `staging-base-url` | The staging API base URL plus a test credential, used by the contract tests to make real calls. |

## Outputs

Per target language, write these as source files via `spgr-write-file`:

| Artifact | Description |
|----------|-------------|
| SDK package | Generated client with typed request and response models matching the spec. |
| Auth module | Handles credential storage, token refresh, and header injection for the declared `auth-flow-type`. |
| Pagination helpers | Idiomatic iteration for paginated endpoints (async iterators or a `nextPage()` helper). |
| Error classes | One typed exception or error per error category defined in the spec. |
| Quickstart README | Installation and a minimal call example for the package. |
| Contract tests | One test per SDK method that calls the live staging API and asserts the generated SDK works against it. |

## Procedure

1. Read the OpenAPI spec through `spgr-read-file` or `spgr-read-artifact`. If the spec is missing, unvalidated, or internally inconsistent (an endpoint without a response model, an undocumented error category, an auth scheme the spec does not declare), stop and raise `spgr-escalate` with the precise gap. Do not infer the missing piece.
2. Confirm `target-languages`, `naming-and-packaging`, `auth-flow-type`, and `staging-base-url` are all supplied. If any is missing, escalate through `spgr-escalate` rather than choosing a default.
3. For each target language, generate the SDK with the configured generation tool (Fern, Stainless, openapi-generator, or AutoRest). Prefer Fern or Stainless where they produce more idiomatic code for the target. Write every generated file through `spgr-write-file`.
4. Review the generated output for idiomatic quality in each language rather than accepting a mechanical translation. A Python SDK follows Python conventions (snake_case, context managers for pagination), a Go SDK follows Go conventions, and so on. A TypeScript or JavaScript SDK is generated as TypeScript, conforms to `.claude/references/typescript-standards.md`, and passes `tsc --noEmit`, lint, and format clean. Correct non-idiomatic output before proceeding.
5. Generate or verify the auth module against `auth-flow-type`, the pagination helpers, the typed error classes, and the quickstart README for each package.
6. Set the SDK version to mirror the API version. When a new API major version ships, release a new SDK major version. Record this mapping with `spgr-log-decision` on the owning documentation artifact so consumers on the old SDK keep working against the old API version.
7. Write the contract tests: one per SDK method, each making a real call against `staging-base-url` with the test credential, asserting request serialization, response typing, and error mapping. Run them through `spgr-run-tests` (or CI). If any method fails against staging, the SDK is not valid output. Fix the generation or escalate.
8. Record the generation run as an envelope artifact through `spgr-write-artifact` with an inline `spgr-validate-artifact` call: the languages generated, tool used, API-to-SDK version mapping, and the contract-test verdict. This is the trace the DevOps Agent reads before publishing.
9. If the SDK changes another agent's work or needs a sign-off (for example an auth-flow detail owned by the Auth Agent, or a publish step owned by DevOps), route the recommendation through `spgr-tag-vertical-agent` as a consultation rather than editing that agent's artifact directly.

## Notes

- Output type is SOURCE OR CONFIG (generated SDK packages plus contract tests), written via `spgr-write-file` and verified by `spgr-run-tests` or CI, not an envelope content schema. The generation-run record in step 8 is an envelope artifact whose content schema is registered in a later increment, so envelope-only validation applies for now.
- Publishing to a package registry (npm, PyPI) is the DevOps Agent's step. This skill produces and verifies the package. Hand off the publish through the consultation path, do not publish from here.
- The contract test against staging is a hard gate. An SDK whose generated methods do not pass against the live staging API is not shippable output.
