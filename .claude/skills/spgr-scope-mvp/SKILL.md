---
name: spgr-scope-mvp
description: Produce an MVP scope artifact that cuts the backlog to the smallest feature set needed to test the core value proposition, with in-scope and deferred lists, the core user journey, and validation criteria. Use when a Product Manager agent has a PRD-derived backlog and must define the MVP before the go/no-go decision at the end of discovery.
---

# scope-mvp

## Purpose

Define the minimum viable product scope by cutting everything that is not required for the core value proposition to be testable with real users. The dominant failure mode in scoping is including too much, not too little. Apply one test to every backlog item: if we remove this, does the core user journey break? Items that fail that test are deferred to a labeled future milestone, not rejected. The resulting artifact is the baseline against which the go/no-go decision is made and against which later scope creep is measured.

## Inputs

| Field | Description |
|-------|-------------|
| `feature-backlog` | Full feature list derived from the PRD. Read via spgr-read-artifact. |
| `value-proposition` | One-line statement of the core value the product delivers. |
| `target-icp` | Ideal Customer Profile the MVP must serve. |
| `capacity-estimate` | Available development capacity for the MVP window. |
| `activation-event` | The PRD `activation_event` on `saas` and `mobile`, the action that proves the value proposition reached the user. Read from the PRD via spgr-read-artifact. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `mvp-scope` | MVP definition statement (one paragraph on what the MVP is and is not), in-scope feature list with a rationale per inclusion, out-of-scope feature list with a rationale and a planned deferral phase per item, the end-to-end core user journey the MVP must support, the minimum path to value from signup to the activation event, and success criteria stating the user behavior or metric that confirms the value proposition is validated. |

## Procedure

1. Read the inputs. Use spgr-read-artifact for the backlog and confirm the value proposition, ICP, and capacity estimate are present and unambiguous.
2. If any required input is missing, contradictory, or the value proposition is not stated in one testable sentence, stop and raise spgr-escalate with the precise list of what is missing rather than inferring it.
3. Construct the core user journey end to end. This is the single path a target ICP user takes to reach the value proposition.
4. Test each backlog item against the journey. Ask: if we remove this, does the core user journey break? If yes, mark it in-scope and write the rationale. If no, mark it a deferral candidate.
5. Apply the standing priors. Authentication is almost always in scope, since users need an identity. Billing is frequently out of scope, since you validate before monetizing. Record any departure from these priors as a decision with spgr-log-decision.
6. Assign each out-of-scope item a planned deferral phase and a rationale. Defer, do not reject. A user who definitely wants a feature will still want it in a later sprint.
7. Write the minimum path to value on `saas` and `mobile`. Inventory every step between signup and the activation event, including each screen, each form field, each confirmation, and each wait, because teams undercount their own steps. Mark each step essential or removable, where essential means the activation event cannot fire without it. Remove or defer the removable steps, reorder what remains so the user reaches value before any setup that can wait, and move deferred setup behind the activation event with progressive disclosure. Name the analytics event each remaining step emits, so the funnel from signup to activation is measurable from the first release. The step list is a section of the artifact, and the step count before and after is recorded with spgr-log-decision.
8. Write the success criteria. State the observable user behavior or metric that confirms the core value proposition is validated.
9. When a deferral or inclusion touches a vertical domain (for example deferring billing, or scoping auth), consult the owning vertical with spgr-tag-vertical-agent and fold the recommendation in before finalizing.
10. Write the mvp-scope artifact with spgr-write-artifact. If a downstream go/no-go gate or scope change requires human judgment, route it with spgr-notify-human.

## Notes

- The mvp-scope artifact is written through spgr-write-artifact. Its type is not yet in the schema registry, so its registered JSON Schema is added in a later build increment. Until then it carries the shared envelope and per-section confidence signals from spgr-write-artifact.
- This artifact is the baseline for the Phase 1 go/no-go decision and the reference point for scope-creep tracking. Capture the version that closes Phase 1 so the shipped scope at Phase 3 close can be diffed against it with spgr-diff-artifact.
- Record consequential inclusion or deferral choices with spgr-log-decision so the reasoning is traceable and settled decisions are not re-litigated.
