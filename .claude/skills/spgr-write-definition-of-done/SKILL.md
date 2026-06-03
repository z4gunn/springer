---
name: spgr-write-definition-of-done
description: Produce the project-level Definition of Done, the shared checklist every story must satisfy before it counts as complete. Use when a Product Manager or QA agent needs to establish the quality bar at the start of a project or revise it at the start of a new development phase, so completeness is settled up front rather than negotiated when a story is claimed done.
---

# write-definition-of-done

## Purpose

Write the one Definition of Done (DoD) that applies to every story in the project. The DoD is the quality bar for how a story is built, distinct from story-level acceptance criteria, which state what a story does. Settling these criteria before development begins removes the late negotiation that happens when a story is claimed complete and the reviewer holds a different mental model of done. The DoD is project-level, agreed by all agents up front, and is the single standard against which every story is checked, not a per-reviewer judgment.

## Inputs

| Field | Description |
|-------|-------------|
| `project_type` | SaaS web app, mobile app, API, or library. Determines which gates apply. |
| `nfrs` | The non-functional requirements in scope, read from the NFR artifact. Each in-scope NFR class can add a gate. |
| `active_verticals` | The vertical agents active on this project (security, accessibility, performance, billing, and so on). Each active vertical whose sign-off is required becomes a gate. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `definition-of-done` | A document listing the gates a story must pass to be done. Each gate is verifiable against an artifact store, a CI result, or a review record, not by agent self-attestation. |

## Procedure

1. Read the inputs through spgr-read-artifact for the NFR artifact, and resolve the active vertical list. Confirm `project_type` is one of the four supported types.
2. Assemble the gate list. Start from the baseline gates that apply to every project:
   - All acceptance criteria pass, verified manually or by automated test.
   - Unit tests written and passing.
   - Integration tests written and passing where the story crosses a component boundary.
   - No new lint errors introduced.
   - Code reviewed and approved by the Code Reviewer agent.
   - Product Manager agent has verified the story against its acceptance criteria in staging.
3. Add conditional gates from the inputs:
   - For each active vertical whose sign-off is required, add a vertical sign-off gate (for example security, accessibility). Confirm the vertical via spgr-tag-vertical-agent where its inclusion is in question rather than assuming.
   - Add an API documentation gate when the story changes a public API. This gate applies on API and library project types, and on any project that exposes a public API.
   - Add a feature-flag gate when a change needs controlled rollout.
   - Translate each in-scope NFR class into a gate where it implies a per-story check (for example a performance budget or an accessibility standard).
4. For each gate, record how it is verified: the artifact store, CI result, or review record that proves it, so DoD compliance can be checked automatically per completed story rather than by self-attestation. State the source for each gate, not just the gate text.
5. Log the gate-selection reasoning with spgr-log-decision, including any project-type or NFR-driven gate that was added or omitted, so the rationale is traceable.
6. Write the artifact with spgr-write-artifact, which runs inline schema validation before the write completes. If validation fails, do not write a partial artifact. Surface the itemized issues.
7. Escalate with spgr-escalate rather than guessing when inputs are incomplete or contradictory: the project type is not one of the four supported types, the NFR artifact is missing or unreadable, the active vertical list cannot be resolved, or two inputs imply conflicting gates. Return a precise list of what is missing.

## Notes

- The DoD is project-level, not team-level, and applies to every story in this project. It is reviewed and updated at the start of each new development phase when scope or quality requirements change. On revision, version it with spgr-version-artifact.
- Keep the DoD separate from acceptance criteria. Acceptance criteria define what a story does. The DoD defines the quality bar for how it is done. Do not restate per-story acceptance criteria here.
- The `definition-of-done` artifact type is written through spgr-write-artifact with the shared envelope, and its registered JSON Schema is added to the schema registry in a later build increment. Until then validation covers the envelope and confidence signals.
- Because the DoD changes downstream completeness checks for every story, any later revision is a candidate scope change. Route it through spgr-notify-human when a gate is added or removed after development has begun.
