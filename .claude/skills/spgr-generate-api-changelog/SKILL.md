---
name: spgr-generate-api-changelog
description: Produce a consumer-facing API changelog artifact organized by release version, listing breaking changes first with migration guides, then new features, behavior changes, deprecations, and bug fixes, all written from the API consumer's perspective. Use when the API Design Agent prepares a release and must give API consumers an actionable record of what changed across the API surface, or when the Documentation Agent needs the API changelog to fold into the developer documentation.
---

# generate-api-changelog

## Purpose

Produce the consumer-facing record of API surface change for one release. An API changelog is not a git commit log. It describes endpoint behavior that an API consumer can act on, not implementation detail. "Added optional `include_archived` query parameter to `GET /users`" belongs here. "Refactored user query builder to support filtering" does not. The artifact lets a consumer find what broke, what to migrate, and what is newly available, without reading code.

This skill belongs to the API Design vertical and runs in consultant and documentation-support mode. It writes its own envelope artifact and does not edit the API spec, the developer docs, or any horizontal agent's artifact directly. When the changelog must reach the Documentation Agent, route the handoff through spgr-tag-vertical-agent as a consultation rather than editing the docs in place.

## Inputs

| Field | Description |
|-------|-------------|
| `api_spec_diff` | OpenAPI diff between the current and previous API version. Read with spgr-read-file. |
| `git_commit_log` | Commit log for the release, filtered to API-touching commits. Read with spgr-read-file. |
| `breaking_change_register` | The register of breaking changes recorded for this release. Read with spgr-read-artifact if stored as an artifact, otherwise spgr-read-file. |
| `release_version` | The API version this changelog entry documents. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `api-changelog` | An envelope artifact holding one changelog entry per release version. Each entry carries five sections in fixed order: breaking changes, new features, changes, deprecations, bug fixes. Written via spgr-write-artifact. |

## Procedure

1. Read the inputs. Read `api_spec_diff`, `git_commit_log`, and `breaking_change_register`. If any required input is missing, contradictory (for example the diff shows a removed endpoint the breaking change register does not list), or the `release_version` is absent, stop and raise spgr-escalate with the precise list of what is missing. Do not infer the missing change set.

2. Auto-generate the breaking change candidate list. Run an OpenAPI diff tool (oasdiff or openapi-diff) against `api_spec_diff` to produce the candidate set of breaking changes. Treat this output as candidates, not as the final list.

3. Have the candidates reviewed before finalizing. The API Design Agent reviews each auto-generated candidate and confirms, reclassifies, or rejects it. A candidate the tool flags that the agent reclassifies as non-breaking moves to the changes or new-features section with a note. A breaking change present in the register but absent from the tool output is added by hand. Do not finalize the changelog from raw tool output.

4. Classify every confirmed change into one of the five sections, written from the consumer's perspective:
   - Breaking changes: any change a consumer must act on to keep working.
   - New features: new endpoints, new fields, new optional parameters.
   - Changes: behavior changes, new validation, status code changes.
   - Deprecations: what is deprecated, the removal timeline, the migration path.
   - Bug fixes: incorrect API behavior that was corrected.

5. List breaking changes first and mark them clearly. Consumers scan for breaking changes before anything else, so this section leads the entry regardless of how few or many other changes exist.

6. Write a migration guide on every breaking change. State the before and after concretely and the step to migrate. Example: "Before: `GET /users?status=active`. After: `GET /users?filter[status]=active`. Migrate by updating the query parameter name." A breaking change without a migration guide is incomplete, so escalate via spgr-escalate if a migration path cannot be determined.

7. Write the artifact and validate it. Write via spgr-write-artifact with an inline spgr-validate-artifact call. Version it alongside the API spec with spgr-version-artifact so each API version has a matching changelog entry. Record any consequential classification call (for example overriding a tool candidate) with spgr-log-decision.

8. Route to consumers of the changelog. When the Documentation Agent must fold this into developer docs, hand it off through spgr-tag-vertical-agent as a consultation. Do not edit the developer documentation directly.

## Notes

- Output type is an envelope artifact (api-changelog). Its content schema is not yet in the schema registry, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) for now. The content schema is registered in a later increment.
- The five sections are fixed and ordered. Breaking changes always lead. An empty section is omitted from the rendered entry but its absence is not a substitute for the candidate review in step 3.
- One artifact, one responsibility. This skill documents change. It does not decide versioning policy (see spgr-write-api-versioning-strategy) and does not produce the general product changelog (see spgr-generate-changelog).
