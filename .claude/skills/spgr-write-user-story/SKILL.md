---
name: spgr-write-user-story
description: Write one INVEST-compliant user story in As a / I want / So that form, linked to a persona and a PRD goal, with an INVEST self-assessment and a split recommendation for oversized stories. Use when the PM agent turns a feature need into a backlog-ready story, before acceptance criteria are written.
---

# write-user-story

## Purpose

Produce a single user story that is the atomic unit of the backlog, the smallest piece of value one developer can deliver in 1 to 3 days and a QA agent can test. Enforce INVEST at the point of creation so vague, oversized, or technically framed stories never reach development. The story output type is registered in the schema registry as `user-story` and every story links to a persona and at least one PRD goal so traceability holds from goal to delivered code.

## Inputs

| Field | Description |
|-------|-------------|
| `feature_need` | Plain-language description of the capability needed |
| `target_persona` | Persona ID from the persona set who is the actor in this story |
| `prd_goal_ref` | The PRD goal this story contributes to |
| `context` | Additional context about the workflow or constraint the story lives in |
| `estimated_complexity` | Optional initial signal: `small` (under 1 day), `medium` (1 to 3 days), `large` (over 3 days) |

## Outputs

| Artifact | Description |
|----------|-------------|
| `user_story` | Structured story in As a / I want / So that form with `story_id`, `title`, `persona_ref`, `prd_goal_ref`, and `estimated_size` |
| `invest_check` | Per-letter self-assessment: independent, negotiable, valuable, estimable, small, testable |
| `invest_failures` | List of INVEST letters that failed, with the reason |
| `split_recommendation` | When `small` or `independent` fails, a proposed split into 2 to 3 sub-stories, otherwise null |

## Procedure

1. Read the PRD and the persona set with spgr-read-artifact. Confirm `prd_goal_ref` resolves to a real PRD goal and `target_persona` resolves to a real persona in the set. If either does not resolve, stop at step 6.
2. Draft the story. Write the As a clause naming the persona archetype, never "the user" or "the system". Write the I want clause as an observable capability. Write the So that clause as business or user value, not a technical outcome. "So that I can see my account balance without calling support" is value. "So that I can update the database" is not.
3. Frame a purely technical story (infrastructure, refactoring, observability) in the same template, with a developer or ops engineer as the actor and a system-quality outcome as the value. Technical stories are not exempt from the template.
4. Run the INVEST check and set each letter:
   - Independent fails if the story explicitly depends on another story not yet delivered.
   - Negotiable holds when the story states the need, not a fixed implementation.
   - Valuable holds when the So that clause states user or business value.
   - Estimable holds when the work is understood well enough to size.
   - Small fails if `estimated_complexity` is `large`, or if the story touches more than 2 vertical domains (for example backend and frontend and mobile and infrastructure in one delivery).
   - Testable fails if the I want clause contains no observable outcome.
   Record every failed letter in `invest_failures` with its reason.
5. If `small` or `independent` failed, split the story into 2 to 3 sub-stories that each pass INVEST, and return them in `split_recommendation`. Do not finalize an oversized or dependent story.
6. Escalate with spgr-escalate when an input cannot be resolved. If `prd_goal_ref` does not map to any PRD goal, the story is a candidate for the out-of-scope list, or a new PRD goal is required, which is a scope change. Raise a scope-change escalation through spgr-escalate and pause for the human gate with spgr-notify-human rather than adding the goal silently. If `target_persona` does not resolve, escalate for a corrected persona ID.
7. Assign `story_id` in the format `STORY-{YYYY}-{seq}` so stories sort by creation date, and set `estimated_size`.
8. Write the story with spgr-write-artifact, which runs spgr-validate-artifact against the registered `user-story` schema inline before the write completes. Set the confidence signal on each section, marking any field that came from an unresolved input as needs-human-input.
9. Log any consequential framing or split choice with spgr-log-decision so the reasoning is traceable.

## Notes

- This skill writes one story only. After the story is finalized, the PM agent invokes the acceptance-criteria skill on it. Do not write acceptance criteria here.
- The output type `user-story` is registered in the schema registry at `schemas/`. Reference field requirements through spgr-validate-artifact rather than inlining them here.
- Do not fill a missing persona or PRD goal with an assumption. An unresolved link is an escalation, not a guess.
