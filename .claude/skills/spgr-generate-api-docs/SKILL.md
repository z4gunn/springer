---
name: spgr-generate-api-docs
description: Generate developer-facing API reference documentation from a validated OpenAPI spec, producing a getting-started guide, per-endpoint-group reference, tested request and response examples in curl plus one SDK language, an authentication reference, an error-code reference, rate-limiting docs, and a changelog link, plus a CI lint check that fails on undocumented parameters, missing response schemas, and undescribed properties. Use when the Documentation Agent must publish or refresh API reference docs for a release so the docs stay in sync with the actual API surface, or when the QA or code-reviewer agent needs the generated reference and its CI doc-lint gate stood up before a release proceeds.
---

# generate-api-docs

## Purpose

Generate developer-facing API reference documentation that is derived from the OpenAPI spec, so the reference never drifts from the actual API. The reference layer (endpoints, parameters, schemas, error codes) is generated from the spec by a renderer such as Redoc or Mintlify. Author the explanatory layer that the spec cannot express on its own: a getting-started narrative, authentication walkthroughs, integration workflow guides, and working code samples. Wire a CI doc-lint check that fails the build when the OpenAPI spec carries undocumented parameters, missing response schemas, or undescribed properties, so documentation gaps are caught before merge.

This is source and config output. Write the docs and the lint check via spgr-write-file, then verify the lint check by running it. Documentation coverage as a release gate is owned by spgr-audit-doc-coverage, not this skill. This skill produces the docs and the inline spec-lint gate.

## Inputs

| Field | Description |
|-------|-------------|
| `openapi-spec` | Validated and complete OpenAPI spec. Read via spgr-read-file. The single source for endpoints, parameters, schemas, and error codes. |
| `auth-model` | Authentication model documentation. Supplies every supported auth method and its setup steps. |
| `integration-patterns` | Common integration patterns from the product spec, used to write workflow guides. |
| `sample-languages` | Code sample language preferences. At minimum curl plus one SDK language. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `docs/api/` source files | Getting-started guide (auth, first API call, pagination, error handling), per-endpoint-group reference, tested examples, auth reference, error-code reference, rate-limiting docs, and a changelog link. Written via spgr-write-file. |
| `api-doc-lint` CI check | Spec-lint config and CI step that fails on undocumented parameters, missing response schemas, and undescribed properties. Written via spgr-write-file, verified by running it. |
| consultation record | When advising another agent (for example flagging spec gaps to the API Design Agent), route the recommendation through spgr-tag-vertical-agent rather than editing that agent's artifact. |

## Procedure

1. Read the OpenAPI spec with spgr-read-file. Confirm it is valid and complete. If the spec is missing, invalid, or has no endpoints, stop and raise spgr-escalate with the precise list of what is missing. Do not write docs against a partial spec.
2. Read the auth model and the integration patterns. If the auth model documentation is absent and the spec declares auth, escalate via spgr-escalate rather than guessing at setup steps.
3. Generate the endpoint reference from the spec using the configured renderer (Redoc, Mintlify, or the project equivalent). Do not hand-write endpoint, parameter, or schema content that the spec already carries, so the reference cannot drift.
4. Author the getting-started guide: authentication, the first API call, pagination, and error handling, written as a narrative a new consumer can follow start to finish.
5. Author the authentication reference covering every supported auth method with step-by-step setup.
6. Write request and response examples for representative endpoints in curl plus one SDK language. Run every example against the API or a contract fixture. An example that does not work is worse than no example, so do not ship an untested sample. If an example cannot be made to pass, treat it as a spec or implementation gap and route the finding to the owning agent via spgr-tag-vertical-agent.
7. Build the error-code reference. Every machine-readable error code in the API must have an entry stating the code, its description, the typical cause, and the resolution. If the spec defines an error code with no description, record it as a lint failure (step 9) and flag it to the API Design Agent via spgr-tag-vertical-agent.
8. Add the rate-limiting documentation and the changelog link (the changelog is produced by spgr-generate-api-changelog).
9. Wire the api-doc-lint CI check: scan the OpenAPI spec for parameters without a description, responses without a schema, and properties without a description. Configure it as a blocking CI step so any of these conditions fails the build. Run the check and confirm it passes on the current spec or reports the exact gaps. Fix the docs or escalate the spec gaps before considering the work done.
10. Write all source files via spgr-write-file. Verify the lint check by running it and verify rendered examples execute. Record consequential choices (renderer selection, which auth methods documented, sample language) with spgr-log-decision.

## Notes

- Output type is source and config (generated docs plus a CI doc-lint check). It is not an envelope artifact, so it is written via spgr-write-file and verified by running the lint check and the examples, not via spgr-validate-artifact.
- If this run also emits a consultation or audit-style summary as an envelope artifact, that artifact's content schema is not registered yet. spgr-validate-artifact falls back to envelope-only validation for unregistered types (header, confidence map, decision log, version), and the content schema is registered in a later increment.
- The reference layer is generated from the spec and is never hand-edited for content that the spec carries, so the docs and the API cannot diverge.
- Every code example is tested before it ships. An untested or failing example is not published.
- Every machine-readable error code has a reference entry. A code without a description is a lint failure, not an acceptable omission.
- A recommendation to a horizontal agent (for example a spec gap for the API Design Agent) flows through spgr-tag-vertical-agent as a consultation, not by editing that agent's artifact directly.
- Release-level documentation coverage is gated by spgr-audit-doc-coverage. This skill stands up the docs and the inline spec-lint gate that feed it.
