---
name: spgr-archive-artifact
description: Move a superseded or retired artifact to the dated archive store, append an archive index entry, and clear the active-store copy. Use when an artifact is superseded by a new version or retired, so the active store holds only current artifacts and history stays recoverable.
---

# archive-artifact

## Purpose

Keep the active artifact store free of stale versions while preserving an auditable history. Archiving is deterministic. The skill moves the artifact to a dated path, records an index entry, and confirms the active copy is cleared so no agent reads a superseded artifact by accident.

## Inputs

| Field | Description |
|-------|-------------|
| `artifact_path` | Path to the artifact to archive |
| `reason` | Why it is being archived, for example superseded or retired |
| `superseded_by` | Optional artifact ID of the replacement |
| `archived_by` | Agent or human identifier |

## Outputs

| Artifact | Description |
|----------|-------------|
| `archive_result` | Object: `artifact_id`, `archive_path`, `archive_timestamp`, `reason`, `superseded_by`, `archived_by`, `archive_confirmed`, `active_store_cleared` |

## Procedure

1. Read the artifact with `spgr-read-artifact` to capture its `artifact_id`, `artifact_type`, and `version`.
2. Write a copy to the archive store at `archive/{artifact_type}/{YYYY-MM}/{artifact_id}-{version}.json` using `spgr-write-file`.
3. Append an index entry to the central archive index: `artifact_id`, `artifact_type`, `archived_at`, `reason`, `superseded_by`, `archive_path`.
4. Remove the artifact from the active store and set `active_store_cleared` true. Confirm the archive copy exists first so the artifact is never lost between steps.
5. Append a decision-log entry to the replacement artifact, if any, recording what it supersedes.

## Notes

- To roll back, read the archived copy with `spgr-read-artifact`, re-validate with `spgr-validate-artifact`, write it back to the active store, and record the rollback rationale with `spgr-log-decision`.
- Archive before writing a new version of the same artifact, so the active store never holds two live versions at once.
