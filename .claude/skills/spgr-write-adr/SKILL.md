---
name: spgr-write-adr
description: Record one Architecture Decision Record in standard format, capturing context, the decision, status, rejected alternatives, and honest consequences. Use when the Architect Agent makes a significant architectural choice whose reasoning must be preserved so the decision is not re-litigated.
---

# write-adr

## Purpose

Capture one significant architectural decision so the reasoning behind it survives the moment it was made. An ADR records not only what was chosen but why, which alternatives were weighed, and what the choice makes easier or harder. The contract here is the standard ADR shape, the immutability rule once a decision is accepted, and the sequential numbering that lets later agents trace and reference decisions. A new ADR is the correct way to change a decision, never an edit to an accepted one. Without this discipline a team rediscovers the same constraints by accident and reopens settled questions.

## Inputs

| Field | Description |
|-------|-------------|
| `context` | The problem being solved, the forces at play, and the constraints that drove the decision |
| `options_considered` | The alternatives weighed, each with a brief rationale for why it was kept or rejected |
| `decision` | The choice made, stated in one clear declarative sentence |
| `rationale` | Why this option won over the others, tied back to the forces in the context |
| `consequences` | What becomes easier, harder, or different as a result, including the downsides |
| `supersedes` | The ADR number this decision replaces, when it overturns an earlier one, otherwise null |

## Outputs

| Artifact | Description |
|----------|-------------|
| `adr` | One Architecture Decision Record with adr_number, title, status, context, decision, and positive, negative, and neutral consequences |

## Procedure

1. Confirm the decision is significant before writing. Significant means it constrains future work, involves a real tradeoff, or would surprise a new team member. If the choice is a trivial implementation detail, do not write an ADR. Tell the caller why and stop.
2. Assign the next sequential ADR number in the `ADR-NNN` form by reading the existing ADRs with spgr-read-artifact and incrementing past the highest. Never reuse or skip a number.
3. Write the context as the problem, the forces, and the constraints. State enough that a reader who was not present understands what pressure shaped the decision.
4. State the decision as one clear declarative sentence. Map the options considered into the context or a rationale paragraph so the rejected alternatives and the reason each lost are on the record.
5. Set status to Proposed. A decision becomes Accepted only at human architecture approval, recorded through spgr-version-artifact when the human approves the baseline. Do not write status Accepted yourself.
6. Write the consequences honestly across positive and negative, with neutral when it applies. An ADR with only positive consequences is a red flag. If you cannot name a single downside, you have not examined the decision hard enough, so reexamine it before writing.
7. When this ADR overturns an earlier decision, set `supersedes` to the prior ADR number, and write a new revision of the prior ADR through spgr-version-artifact that sets its status to Superseded and its `superseded_by` to this ADR number. Never edit the accepted text of the prior ADR to change its decision.
8. Produce the artifact with spgr-write-artifact, which stamps the shared envelope, records per-section confidence, initializes the decision log, and runs spgr-validate-artifact against the registered adr schema inline before write. Do not hand-build the envelope.
9. If the inputs are incomplete or contradictory, for example a decision with no rationale, options that contradict the stated forces, or a supersedes target that does not exist, stop and raise spgr-escalate with a precise list of what is missing or conflicting rather than inventing the missing reasoning.
10. Log any consequential modeling choice with spgr-log-decision so the reasoning behind how the ADR was framed is itself traceable.

## Notes

- The adr artifact type is registered in the schema registry at `schemas/` as `adr-v1.json`. Reference field requirements through spgr-validate-artifact rather than inlining them here.
- ADRs are immutable once accepted. A decision is changed by writing a new ADR that supersedes the old one, never by editing the accepted decision. The only edit allowed on an accepted ADR is a status change to Superseded with its `superseded_by` set.
- An honest negative consequence is a required output, not optional. A consequences set with no downside fails review.
- A decision log index that summarizes every ADR by number, title, and status, and the linter that flags missing sections and superseded ADRs left unupdated, are project-level tooling outside this single-artifact skill and are added in a later build increment.
