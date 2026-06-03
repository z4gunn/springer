---
name: spgr-prioritize-backlog
description: Order a product backlog by business value and core-value-prop impact, assigning a priority tier and per-story rationale, reserving explicit slots for tech debt and infrastructure, and recording deferrals. Use when the PM agent has a set of user stories that need a consistent, evidence-based order before development planning, or when an existing backlog must be re-prioritized after new research or a scope change.
---

# prioritize-backlog

## Purpose

Produce one ordered backlog whose sequence reflects where the product delivers the most value to the ideal customer profile first, not who asked loudest. Score each story on a fixed multi-factor framework, resolve dependency constraints, assign a priority tier, and write a rationale per story so the order is reproducible and traceable. Reserve explicit positions for tech debt and infrastructure so that work is never perpetually deferred. This is the PM agent's prioritization step, distinct from defining MVP scope or writing stories.

## Inputs

| Field | Description |
|-------|-------------|
| `story_set` | Array of user story IDs to prioritize |
| `business_context` | Current business priorities across revenue, retention, growth, compliance, and technical stability |
| `user_research` | Pain point taxonomy with severity and frequency per pain point |
| `prd_goals` | PRD goals in their intended priority order |
| `team_context` | Team composition and capacity signals, used to flag stories needing skills the team lacks |
| `dependencies` | Known story dependencies, used to enforce dependency ordering |

## Outputs

| Artifact | Description |
|----------|-------------|
| `prioritized_backlog` | Ordered story IDs, each with priority tier, priority score, rationale, and a dependencies_met flag |
| `tech_debt_slots` | Reserved backlog positions for tech debt and infrastructure stories, each with a reason |
| `deferred_stories` | Stories moved out of the current release, each with a deferral reason and a revisit condition |

## Procedure

1. Read each input through spgr-read-artifact: the story set, PRD goals, and pain point taxonomy. Read the dependencies and business and team context the PM agent supplied.

2. Validate that every story ID in `story_set` resolves and passes the INVEST estimable check. If a story cannot be estimated, set it `needs-refinement`, place it in a refinement queue outside the main backlog order, and exclude it from scoring.

3. Score each remaining story with the fixed framework. Do not vary the weights.
   `priority_score = (core_value_prop_impact x 3) + (pain_point_severity x 2) + (pain_point_frequency x 1) + (prd_goal_alignment x 2) + (business_context_alignment x 1) - (complexity_penalty x 1)`
   Score each factor on a consistent scale and record the inputs so the score is reproducible.

4. Assign a priority tier from the score and from whether the story blocks the core value proposition: `P0` must ship in MVP and blocks the core value prop, `P1` ships in MVP and is high value, `P2` ships in v1.1 and is valuable but not blocking, `P3` is future and low urgency or unvalidated, `deferred` is out of scope for the current release cycle. Stories that validate the core value proposition rank first regardless of other factors, because an unproven core promise makes the rest moot.

5. Enforce dependency ordering. If story B depends on story A, place A before B regardless of relative score, and set `dependencies_met` on B only when every dependency precedes it. When a higher-scored story depends on a lower-scored one, the dependency wins the order.

6. Break ties by observable user value. When two stories share a score, place the one that delivers more visible user value first, since it builds momentum and trust.

7. Reserve explicit `tech_debt_slots` at concrete positions in the order for tech debt and infrastructure work. Each slot names a position and a reason, with a story_id when one exists or null when the slot is held for work not yet written. Do not treat these as optional.

8. Record each story moved out of the current release in `deferred_stories` with a deferral reason and a revisit condition.

9. Write a one-line rationale per story stating why it sits in its position, referencing the factors that drove its score.

10. Escalate through spgr-escalate rather than guessing when an input is missing or contradictory. Trigger on a story ID that does not resolve, a dependency cycle, a dependency on a story absent from `story_set`, a story that requires a skill `team_context` says the team lacks, or a PRD goal order that conflicts with the supplied business context. Return the precise list of what is missing or in conflict.

11. Log any consequential ordering choice through spgr-log-decision, in particular a case where a dependency overrode score or a tie was broken on observable value, so the order is not re-litigated later.

12. Write the artifact through spgr-write-artifact, which runs inline validation before the write completes.

## Notes

- The `prioritized-backlog` artifact type is not yet in the schema registry. It is written through spgr-write-artifact, and its registered schema is added in a later build increment. Validate the upstream story, PRD, and pain point inputs against their registered schemas through spgr-validate-artifact.
- Prioritize by value delivered to the ICP, not by stakeholder volume. The loudest stakeholder and the highest-priority story are often not the same.
- Output shape: `{ backlog: [{story_id, title, priority_tier, priority_score, rationale, dependencies_met}], tech_debt_slots: [{position_in_backlog, story_id|null, reason}], deferred_stories: [{story_id, deferral_reason, revisit_condition}] }`.
