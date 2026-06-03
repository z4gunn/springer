---
name: spgr-escalate
description: Raise a structured escalation when input is missing or contradictory, constraints conflict, scope changes, or a policy issue is found, then route it to the correct handler. Use when an agent cannot proceed correctly on its input and must stop and surface a precise list of what is wrong rather than filling gaps with assumptions.
---

# escalate

## Purpose

Make refusing to proceed a first-class action. An agent that stops on incomplete or contradictory input and returns exactly what is missing is doing its job, not failing. This skill formats the escalation, assigns a sortable ID, picks the routing target, and triggers the right notification so the blockage is visible and resolvable.

## Inputs

| Field | Description |
|-------|-------------|
| `escalation_type` | One of `missing-input`, `contradictory-input`, `constraint-conflict`, `scope-change`, `policy-compliance-security`, `blocked`, `system` |
| `description` | Precise statement of what is wrong, itemized where possible |
| `artifact_ref` | The artifact or input that triggered the escalation |
| `urgency` | `routine`, `urgent`, or `critical` |
| `originating_agent` | Slug of the agent raising it |
| `proposed_resolution` | Optional suggested fix or both sides of a conflict |

## Outputs

| Artifact | Description |
|----------|-------------|
| `escalation` | Artifact of type `escalation`: `escalation_id`, `escalation_type`, `description`, `artifact_ref`, `urgency`, `routing_target`, `originating_agent`, `status` |

## Procedure

1. Determine the routing target from the type. Ambiguity in specs or requirements routes to the upstream agent. A technical conflict between agents routes to the Architect. A policy, compliance, or security issue routes to the human and the specialist agent. A `scope-change` routes to the human. A blocked item with no agent resolution path routes to the human.
2. Assign `escalation_id` as `ESC-{YYYYMMDD}-{4-digit-seq}`. Set `status` to `open`.
3. Write the escalation with `spgr-write-artifact` (type `escalation`).
4. For `scope-change` and any human-routed escalation, notify with `spgr-notify-human`. Record the escalation with `spgr-log-decision`.
5. Return the escalation. The originating agent stops work on the blocked path until the escalation is resolved.

## Notes

- Do not fill gaps with assumptions to avoid escalating. An itemized escalation is cheaper than rework built on a guess.
- Resolution flow: the orchestrator or human sets `status` to `resolved` with resolution notes, and the pipeline re-routes to the originating agent with the resolved input.
