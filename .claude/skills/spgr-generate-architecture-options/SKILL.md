---
name: spgr-generate-architecture-options
description: Produce an architecture-options artifact holding two or more genuinely distinct architecture options, each with full topology, data, API, auth, and infrastructure choices, a strengths and weaknesses analysis, a complexity and cost-at-scale estimate, and a weighted scoring matrix. Use when the Architect Agent has an approved PRD with NFRs and constraints and must present alternatives to the human for selection at the first architecture checkpoint, before any architecture decision or build work proceeds.
---

# generate-architecture-options

## Purpose

Generate the architecture-options artifact that drives the first human-in-the-loop checkpoint. This skill produces at least two options that differ at the structural level so the human chooses deliberately rather than ratifying a single default. The skill does not select an option. It presents tradeoffs, scores them against weighted criteria drawn from the NFRs and constraints, and hands the decision to the human through spgr-notify-human. The downside of a wrong choice here is the most expensive to reverse later, so the contract requires distinct, self-consistent options and explicit assumptions on every estimate.

## Inputs

| Field | Description |
|-------|-------------|
| `prd` | Approved PRD artifact, read via spgr-read-artifact. Source of goals, scope, and core value proposition. |
| `nfr` | Non-functional requirements artifact. Source of the measurable targets each option must meet and the weights for the scoring matrix. |
| `compliance_scope` | Stated compliance regimes in scope (for example SOC 2, HIPAA, GDPR), which constrain data residency, auth, and infrastructure choices. |
| `constraints` | Team size, budget, timeline, and existing infrastructure that bound feasibility. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `architecture-options` | One artifact containing two or more option entries plus a weighted scoring matrix. Each option states topology, data model approach, API style, auth model, infrastructure, strengths, weaknesses, estimated complexity as S, M, L, or XL, and estimated cost at scale with stated assumptions. |

## Procedure

1. Read the PRD and NFR with spgr-read-artifact, and confirm the constraints and compliance scope are present. If any required input is missing, empty, or contradictory, stop and raise spgr-escalate with a precise list of what is missing rather than filling gaps with assumptions.
2. Derive the comparison criteria and their weights from the NFR targets and the constraints (for example time to market, operational complexity, cost at scale, scalability headroom, compliance fit, team-skill fit). Record each weight choice with spgr-log-decision so the weighting is traceable.
3. Draft at least two options that are distinct at the structural level. A monolith against microservices is distinct. Two microservice topologies with different service boundaries are not. If the only differences are cosmetic, collapse them and draft a genuinely different alternative instead.
4. For each option, specify topology, data model approach, API style, auth model, and infrastructure together, and confirm the parts are self-consistent. The data model, API style, and infrastructure must work as one design.
5. For each option, write strengths and weaknesses, assign a complexity tier of S, M, L, or XL, and estimate cost at scale. State every assumption behind a complexity or cost estimate inline, including the scale figures the cost assumes.
6. Score every option against the weighted criteria from step 2 to produce the scoring matrix. Keep the narrative tradeoff analysis alongside the matrix so the human reads both the numbers and the reasoning.
7. When a vertical domain bounds an option (security model, compliance posture, auth approach), consult the relevant specialist with spgr-tag-vertical-agent before marking that section confirmed, and fold any required amendment into the option.
8. If the constraints make every option infeasible, do not force-fit a bad option. Surface the infeasibility explicitly through spgr-escalate, naming which constraint each option violates.
9. Write the artifact with spgr-write-artifact, which validates against the registered architecture-options schema with spgr-validate-artifact before the write completes. Set per-section confidence signals: confirmed where a choice is settled, proposed where it depends on the human selection, needs-human-input where the option set itself awaits the checkpoint decision.
10. Route the completed artifact to the human with spgr-notify-human as the architecture-options checkpoint. The human selects one option or specifies a hybrid. Do not proceed to any architecture decision or ADR until that response returns.

## Notes

- This artifact is the sole input to the first architecture checkpoint. It presents and scores options. It never selects one. Selection is the human's, recorded on the spgr-notify-human return.
- The architecture-options type is registered in the schema registry at schemas/. Reference fields through spgr-validate-artifact rather than inlining them here.
- A hybrid choice from the human is a valid outcome. When the human specifies a hybrid, the downstream architecture-decision and ADR work proceeds from that hybrid, not from a single listed option.
- Two options is the floor, not the target. Add a third when the constraints admit a meaningfully different third structure.
