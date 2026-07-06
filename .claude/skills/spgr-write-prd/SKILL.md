---
name: spgr-write-prd
description: Produce a Product Requirements Document artifact from confirmed Discovery outputs and human vision inputs, covering problem, goals, personas, scope, NFR summary, success metrics, and open questions. Use when the PM Agent writes the canonical product contract that architects, developers, and QA read before build work begins.
---

# write-prd

## Purpose

Write the PRD, the primary contract between the PM Agent and every downstream agent. Architects read it to make stack and component decisions, developers read it to know what they are building and why, and QA reads it to know success criteria. The PRD removes divergence by giving canonical answers to four questions: what problem, for whom, measured how, and explicitly what is not in scope. This skill is PM-exclusive.

## Inputs

| Field | Description |
|-------|-------------|
| `discovery_artifact` | Confirmed Discovery output: problem statement, ICP, personas, go decision. Read with spgr-read-artifact. |
| `human_vision_inputs` | Free-form human input on vision, constraints, non-negotiable requirements, and aesthetic direction. |
| `competitive_matrix` | Competitive analysis output, used to ground differentiation claims. |
| `pain_point_taxonomy` | Synthesized pain point taxonomy, the source of problem statement evidence. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `prd` | Complete PRD artifact, type `prd` in the schema registry, covering all required sections. |
| `scope_summary` | One-page in-scope and out-of-scope summary carried in the PRD, designed for quick human review. |

## Procedure

1. Read the discovery artifact with spgr-read-artifact and confirm its go decision and confidence signals. If discovery is missing, unconfirmed, or contradicts the human vision inputs, stop and raise spgr-escalate with the precise list of what is missing or conflicting. Do not invent product intent.
2. Write the problem statement grounded in the pain point taxonomy. Cite specific pain points as evidence references. Do not write invented summaries.
3. Write goals. Give every goal at least one measurable, specific success metric with a measurement method. Reject vague metrics such as "users are successful" in favor of targets such as "70% of new users complete their first workflow within 15 minutes of signup."
4. Write personas from the discovery artifact, each with a primary use case.
5. Write the in-scope feature list. Tie every feature back to at least one goal. Move any feature with no goal connection to the out-of-scope list.
6. Write the out-of-scope list. Treat it as equal in weight to the scope list. Name what is not being built so dev agents have clear authority to reject features outside scope, and give each item a reason for exclusion.
7. Apply scope drift prevention. If human vision inputs reference features not connected to any pain point in the taxonomy, surface them as open questions rather than adding them to scope silently.
8. Write the NFR summary section covering performance, security, availability, scalability, and compliance.
9. Write success metrics, the user-stories overview, and open questions, each open question carrying an owner and a deadline.
10. Run inter-section consistency checks: every scope feature ties to a goal, every goal has a metric, every problem claim has evidence.
11. After the NFR section is written, tag the Architect with spgr-tag-vertical-agent so architecture decisions are grounded in the PRD NFR, and tag Security, Compliance, and Accessibility as early vertical consultants. Fold any required amendment back into the relevant section.
12. Write the artifact with spgr-write-artifact against the `prd` schema, set per-section confidence signals, and run spgr-validate-artifact inline before the write completes. Resolve every itemized issue before proceeding.
13. Pause at the approval gate with spgr-notify-human. The PRD must receive human approval before routing to the architect or the backlog-building phase. Record the human response on return and version with spgr-version-artifact.

## Notes

- The `prd` artifact type is registered in the schema registry. spgr-validate-artifact resolves its required fields, types, and confidence signals from the registry. Do not inline the field list here.
- Log consequential choices made while drafting, such as moving a vision-input feature to open questions, with spgr-log-decision so the reasoning stays traceable.
- Human approval through spgr-notify-human is a required gate. Work does not route downstream without it.
