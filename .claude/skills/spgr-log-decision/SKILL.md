---
name: spgr-log-decision
description: Append a structured decision entry to an artifact's decision log, capturing the decision, rationale, alternatives considered, and downstream impact. Use whenever an agent makes a consequential choice while producing or revising an artifact, so the reasoning is preserved and traceable without re-litigating settled decisions.
---

# log-decision

## Purpose

Prevent decision amnesia. The decision log records not just what was chosen but why, which alternatives were rejected, and what the choice constrains downstream. The log is kept separate from the artifact body so the content stays clean and the audit trail stays append-only.

## Inputs

| Field | Description |
|-------|-------------|
| `artifact_ref` | ID or path of the artifact the decision belongs to |
| `decision` | The choice made, stated clearly |
| `rationale` | Why this choice over the alternatives |
| `alternatives_considered` | List of `{option, reason_rejected}` |
| `decision_maker` | Agent slug or human identifier |
| `artifact_section` | The section the decision affects |
| `confidence` | `confirmed`, `proposed`, or `needs-human-input` |
| `downstream_impact` | List of agents or artifacts the decision constrains |

## Outputs

| Artifact | Description |
|----------|-------------|
| `decision_entry` | The appended entry: `entry_id`, `timestamp`, `decision`, `rationale`, `alternatives_considered`, `decision_maker`, `artifact_ref`, `artifact_section`, `confidence`, `downstream_impact` |

## Procedure

1. Read the target artifact with `spgr-read-artifact` to get its current `decision_log`.
2. Build the entry. Assign `entry_id` as `DEC-{artifact_id}-{seq}` where seq is the next index in the log.
3. Append the entry to the `decision_log` array. Do not modify any body field to embed the decision inline.
4. Write the updated artifact through `spgr-write-artifact` so it re-validates against the registry before the new log is persisted.

## Notes

- The decision-entry shape is defined in the shared envelope at `schemas/_envelope-v1.json` under `$defs.decision_entry`. Validation against it happens through `spgr-validate-artifact`.
- An entry with only upside and no rejected alternatives is a red flag. Record the real tradeoff.
