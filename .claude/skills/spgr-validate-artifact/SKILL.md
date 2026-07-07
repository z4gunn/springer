---
name: spgr-validate-artifact
description: Validate an artifact against its registered JSON Schema and report a structured pass or fail with itemized issues. Use before consuming an artifact received from another agent, and inline before any artifact write completes, to confirm required fields, types, schema version, and confidence signals.
---

# validate-artifact

## Purpose

Hold the line on the typed-artifact contract. A receiving agent validates before acting so it never builds on a malformed or version-mismatched input, and `spgr-write-artifact` validates inline so no invalid artifact is ever written. Schema and field validation is deterministic and runs through the shared validator. Semantic consistency checks that need judgment run separately.

## Inputs

| Field | Description |
|-------|-------------|
| `artifact_path` | Path to the artifact JSON to validate |
| `artifact_type` | Optional override. Defaults to the artifact's own `artifact_type` |
| `schema_version` | Optional override. Defaults to the artifact's own `schema_version` |
| `validation_mode` | `schema` (default) or `schema+semantic` to add consistency checks |

## Outputs

| Artifact | Description |
|----------|-------------|
| `validation_result` | Object: `is_valid`, `artifact_id`, `artifact_type`, `schema_version_match`, `validation_mode`, `error_count`, `warning_count`, `issues`, `validated_at` |

## Procedure

1. Run the deterministic validator: `python3 schemas/validate.py <artifact_path>`. It loads the schema for `artifact_type` plus `schema_version` from the registry, resolves the shared envelope, and reports every schema issue with its field path. A zero exit means schema-valid.
2. Map each reported issue to one of the issue types: `missing_required_field`, `wrong_type`, `schema_version_mismatch`, `missing_confidence_signal`, `internal_contradiction`, `out_of_range_value`, `invalid_reference`.
3. When `validation_mode` is `schema+semantic`, add the per-type consistency checks that schema alone cannot express. Examples: PRD success metrics reference goal dimensions defined earlier in the same artifact, architecture component dependencies are acyclic, a test plan references only story IDs that exist in the backlog.
4. Return the structured `validation_result`. Set `is_valid` false if any error-severity issue exists. Warnings do not fail validation.

## Notes

- The schema registry and validator live at `schemas/` (see [schemas/validate.py](../../../schemas/validate.py)). Do not restate field lists here. The registry is the single source of truth for required fields and types.
- Validation has two modes. When a content schema is registered for the artifact type, the validator applies it (mode `content`). When no content schema exists yet, the validator falls back to validating the shared envelope header only (mode `envelope-only`), so the header, confidence map, decision log, and version are still checked while content is treated as opaque until a schema is added. Report the mode so the caller knows whether content was checked.
- Validation never edits the artifact. It reports. The caller decides whether to fix, re-version, or escalate.
