---
name: spgr-generate-design-directions
description: Produce a design-directions artifact holding three or more genuinely distinct creative directions for human selection, each with visual language, interaction model, information-architecture rationale, emotional tone, one or two key screen mockups, and a per-persona usability prediction. Use when the Design Agent has personas, core user flows, brand constraints, platform targets, and accessibility requirements and must open the design space before any detailed design work, or when a HIL checkpoint needs distinct directions for a human to pick one or scope a hybrid.
---

# generate-design-directions

## Purpose

Generate three or more meaningfully distinct creative directions so a human chooses the design direction deliberately, rather than having it decided implicitly by the first reasonable option that gets built. The contract that matters here is distinctness. Three directions that vary only in color palette are one direction with three colorways, not three directions. Each direction must vary on at least one structural axis (navigation model, density, interaction paradigm, or content hierarchy) and carry a rationale tied to the personas and flows, not aesthetic preference alone.

## Inputs

| Field | Description |
|-------|-------------|
| `personas` | User personas the directions must serve, read via spgr-read-artifact. |
| `user-flows` | Core user flows the directions must support. |
| `brand-constraints` | Existing brand, color-palette restrictions, tone of voice. |
| `platform-targets` | Web, iOS, Android, or the stated combination. |
| `accessibility-requirements` | Target WCAG level and any platform accessibility constraints. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `design-directions` | Envelope artifact holding three or more directions. Per direction: visual language (color palette, typography style, density, use of imagery), interaction model (navigation pattern, gesture conventions, feedback style), information-architecture rationale, emotional tone, one or two key screen mockups, a per-persona usability prediction, and an optional lightweight mood board as supporting material. Written via spgr-write-artifact. |

## Procedure

1. Read every input artifact via spgr-read-artifact. If personas, core user flows, brand constraints, platform targets, or accessibility requirements are missing or contradictory, do not fill the gap with an assumption. Raise spgr-escalate with a precise list of what is missing and stop.

2. Map the design space. Name the structural axes that can vary: navigation model, density, interaction paradigm, content hierarchy. Pick distinct positions on these axes so the directions cannot collapse into one. A direction that varies only in color or typography from another is not a separate direction.

3. Draft at least three directions. For each, write the visual language, the interaction model, the information-architecture rationale, the emotional tone, and one or two key screen mockups that illustrate the direction concretely. Express all visual values as tokens, with no hardcoded hex codes, pixel sizes, or font names baked into the mockup descriptions.

4. Tie each direction to evidence. State why this direction serves the personas and the user flows. A direction without a defensible rationale anchored to a persona or a flow is rejected, not shipped.

5. Add a per-direction usability prediction. Name which persona the direction is likely to test best with and why, drawing on the persona's stated goals, context, and constraints.

6. Add an optional lightweight mood board per direction as supporting material when it clarifies the emotional tone. Keep it as a token-based reference, not a finished comp.

7. Run a distinctness check across the full set. Confirm each pair of directions differs on at least one structural axis. If two directions differ only in surface styling, merge or replace one so the set holds three or more genuinely distinct directions.

8. Confirm every direction satisfies the accessibility requirements at the target level. Tag the Accessibility vertical via spgr-tag-vertical-agent when a direction's density, contrast intent, or interaction paradigm raises an accessibility question before the human selects.

9. Write the artifact via spgr-write-artifact and validate it inline with spgr-validate-artifact. Version it with spgr-version-artifact and record the direction-space reasoning with spgr-log-decision.

10. Route the set to the human selection gate via spgr-notify-human. Do not begin any detailed design work until a direction is selected. If the human selects a hybrid, document exactly what was taken from each direction, with explicit constraints, before proceeding. Record the hybrid scope with spgr-log-decision. A hybrid that is not explicitly scoped is rejected.

## Notes

- Output type is an envelope artifact (design-directions). The design-directions content type has no registered content schema yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered. Still call it.
- All visual values are token-based. No hardcoded style values appear in any direction or mockup.
- Mark each direction's status in the confidence map as proposed. The full set carries needs-human-input until a direction is selected at the HIL checkpoint.
- Three or more directions is a hard floor. Stop and escalate rather than ship two.
