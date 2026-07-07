---
name: spgr-write-artifact
description: Produce a typed output artifact with the shared envelope header, per-section confidence signals, an initialized decision log, and inline schema validation before write. Use whenever an agent produces a deliverable artifact for handoff so the result is readable and validatable by downstream agents.
---

# write-artifact

## Purpose

Hold the artifact contract that every agent-to-agent handoff depends on. Each artifact carries a schema version, a confidence signal per section, and an initialized decision log, and it passes validation before it is ever written. This is the single production primitive. Agents pass structured content, and this skill assembles the envelope, validates, and writes.

## Inputs

| Field | Description |
|-------|-------------|
| `artifact_type` | Type identifier matching a registered schema, for example `prd`, `nfr`, `architecture-options`, `adr`, `escalation` |
| `artifact_id` | Unique ID. Generated if not provided |
| `producing_agent` | Slug of the agent writing the artifact |
| `content_fields` | Field name to value map covering all schema-required and optional content fields |
| `confidence_map` | Section name to confidence signal map (`confirmed`, `proposed`, `needs-human-input`) |
| `schema_version` | Schema version the artifact conforms to, for example `v1` |
| `parent_artifact_ref` | Optional ID of the upstream artifact this derives from |

## Outputs

| Artifact | Description |
|----------|-------------|
| `artifact_document` | Complete artifact: envelope header, content, confidence map, empty decision log |
| `artifact_id` | Assigned ID |
| `artifact_path` | Path written in the artifact store |
| `validation_result` | Inline result from `spgr-validate-artifact`, which must pass before the write completes |

## Procedure

1. Assemble the envelope header: `artifact_id`, `artifact_type`, `schema_version`, `producing_agent`, `timestamp`, `parent_artifact_ref`, `version` (start at `v0.1-draft`), `version_type` (`draft`), `confidence_map`, an empty `decision_log`, and `content` built from `content_fields`.
2. For any required field whose value is unknown, include the field and mark its section `needs-human-input` in the confidence map rather than omitting it. The artifact must be complete even when some answers are open.
3. Apply the confidence propagation rule: if the parent artifact has `needs-human-input` sections consumed here, mark the derived sections `needs-human-input` too, unless a HIL checkpoint resolved them.
4. Validate inline with `spgr-validate-artifact`. If validation fails, do not write. Escalate with `spgr-escalate` carrying the itemized issue list.
5. Write the artifact to the store with `spgr-write-file`. Record the path. Populate the decision log later with `spgr-log-decision`, never by editing the body inline.

## Notes

- The schema registry at `schemas/` defines every field and type. Reference it through `spgr-validate-artifact` rather than restating field lists here.
- Artifacts are immutable once versioned. A change produces a new version with `spgr-version-artifact`, not an edit to the existing file.
- Confidence signals drive downstream behavior: `confirmed` is consumable directly, `proposed` should be reviewed first, `needs-human-input` blocks until a HIL checkpoint resolves it.
