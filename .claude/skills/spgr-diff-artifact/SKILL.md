---
name: spgr-diff-artifact
description: Compare two versions of an artifact field by field, summarize the changes, and flag scope changes that require human approval. Use when an artifact is revised and a downstream agent or the orchestrator needs to know what changed, whether scope expanded or contracted, and which agents are affected.
---

# diff-artifact

## Purpose

Make artifact change legible. When a versioned artifact is revised, downstream agents need to know exactly what moved, whether the change touches scope, and who is impacted. Field-level comparison is deterministic. Long free-text fields get a readable change summary.

## Inputs

| Field | Description |
|-------|-------------|
| `artifact_id` | The artifact to compare across versions |
| `v1_path` | Path to the earlier version |
| `v2_path` | Path to the later version |

## Outputs

| Artifact | Description |
|----------|-------------|
| `diff_result` | Object: `artifact_id`, `artifact_type`, `v1_version`, `v2_version`, `change_summary`, `section_diffs`, `scope_change_detected`, `impact_assessment`, `confidence_changes` |

## Procedure

1. Read both versions with `spgr-read-artifact`.
2. Compare fields. Tag each difference with a change type: `added`, `removed`, `modified`, `confidence_changed`, or `unchanged`. For long text fields, produce a short human-readable summary of the change rather than a raw character diff.
3. Detect scope change. For a PRD, any addition to `scope` or removal from `out_of_scope` is a scope expansion. Any addition to `out_of_scope` is a scope contraction. Either sets `scope_change_detected` true.
4. Build `impact_assessment`: list the agents or artifacts affected by each change and why.
5. Record `confidence_changes` where a section's confidence signal moved, even if its value did not.

## Notes

- A detected scope change is not resolved here. Hand it to the orchestrator, which routes a scope-change escalation to the human. See `spgr-escalate`.
- The registry at `schemas/` defines the comparable fields. Read both versions through `spgr-read-artifact` so each is validated before the diff.
