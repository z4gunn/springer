---
name: spgr-read-artifact
description: Parse a stored artifact, validate it against its registered schema, and return its header, content fields, confidence map, and decision log. Use when an agent needs to consume an upstream artifact (a PRD, NFR, architecture decision, and so on) before acting on it, optionally reading only specific sections.
---

# read-artifact

## Purpose

Give agents a parse-and-validate read path so no agent acts on an artifact it has not confirmed is well-formed and version-matched. Reading is deterministic. The skill loads the file, validates against the registry, and returns structured fields plus the confidence map the consuming agent needs to decide what is safe to use directly.

## Inputs

| Field | Description |
|-------|-------------|
| `artifact_path` | Path to the artifact JSON in the store |
| `sections` | Optional list of content sections to return. Defaults to all |
| `expected_type` | Optional type the caller expects. A mismatch is an error |

## Outputs

| Artifact | Description |
|----------|-------------|
| `read_result` | Object: `artifact_id`, `artifact_type`, `schema_version`, `version_match`, `producing_agent`, `timestamp`, `confidence_map`, `artifact_fields`, `decision_log`, `read_errors` |

## Procedure

1. Read the file with `spgr-read-file` and parse it as JSON.
2. Validate with `spgr-validate-artifact`. If the schema version does not match the registry, set `version_match` false and report it in `read_errors`. Do not return fields as trustworthy when validation fails.
3. If `expected_type` is given and differs from the artifact's `artifact_type`, return an error rather than guessing.
4. When `sections` is given, return and validate only those sections. This keeps reads cheap when an agent needs a subset of a large artifact.
5. Return the structured `read_result`, including the `confidence_map` so the caller can tell which sections are `confirmed`, `proposed`, or `needs-human-input`.

## Notes

- The registry at `schemas/` defines the fields. Reference it through `spgr-validate-artifact` rather than restating field lists here.
- Cache parsed artifacts by `artifact_id` plus `schema_version` within a session to avoid repeated disk reads when several agents consume the same artifact.
- A consumer must not act on a `needs-human-input` section until a HIL checkpoint resolves it.
