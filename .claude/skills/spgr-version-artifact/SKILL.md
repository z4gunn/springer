---
name: spgr-version-artifact
description: Stamp a new version on an artifact, incrementing minor on agent revision and major on human approval, and write a tamper checksum once approved. Use when an artifact changes after its first write, or when a human approves an artifact and it must become an immutable baseline.
---

# version-artifact

## Purpose

Keep artifact history honest. Artifacts are immutable once written, so every change is a new version rather than an edit. This skill computes the next version number, records the version header, and on approval writes a content checksum so downstream agents can detect tampering with a confirmed baseline.

## Inputs

| Field | Description |
|-------|-------------|
| `artifact_path` | Path to the artifact to version |
| `version_type` | `draft`, `candidate`, `approved`, or `archived` |
| `producing_agent` | Agent or human identifier applying the version |
| `version_notes` | Short description of what changed |

## Outputs

| Artifact | Description |
|----------|-------------|
| `version_header` | Object: `version`, `version_type`, `producing_agent`, `version_timestamp`, `parent_version`, `version_notes`, `checksum` |

## Procedure

1. Read the current artifact with `spgr-read-artifact` to get its `version` and `version_type`.
2. Compute the next version. Increment the minor number on an agent revision. Increment the major number and reset minor to zero on human approval. If there is no parent version, start at `v0.1-draft`.
3. Set `version_type` from the input. Carry the prior version into `parent_version`.
4. When `version_type` becomes `approved`, compute a checksum over the artifact content and store it in the header. This is the immutability marker for the confirmed baseline.
5. Write the updated artifact with `spgr-write-artifact` semantics (validate, then write). Append a decision-log entry with `spgr-log-decision` recording the version bump and its reason.

## Notes

- Approval is the boundary between mutable and immutable. After an `approved` stamp, a change requires a scope-change escalation, not a silent re-version.
- Downstream agents verify the stored checksum before consuming an approved artifact. A mismatch is an `invalid_reference` condition to escalate.
