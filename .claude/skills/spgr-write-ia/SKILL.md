---
name: spgr-write-ia
description: Produce an information-architecture artifact fixing the complete screen inventory and navigation model, with a site map, per-screen purpose and entry and exit points, and every user story mapped to a screen. Use when the Design Agent has approved requirements and a selected design direction and must settle screen scope before wireframing begins.
---

# write-ia

## Purpose

Make the full scope of the product's screens and navigation explicit before any detailed design begins. A screen that is not in the inventory does not officially exist and will not get designed or tested, so the inventory is the authoritative index for every later design and build task. This artifact prevents screens from being forgotten, duplicated, or structured inconsistently, and it gives scope a concrete number through a screen count.

## Inputs

| Field | Description |
|-------|-------------|
| `requirements` | Approved PRD and user stories. Read with spgr-read-artifact. |
| `design-direction` | The selected design direction, including its interaction model. Read with spgr-read-artifact. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `ia` | Information-architecture envelope artifact written with spgr-write-artifact. Contains the site map, the screen inventory, the navigation model, the content hierarchy, the screen-count metric, and the story-to-screen cross-reference. |

## Procedure

1. Read the approved requirements and the selected design direction with spgr-read-artifact. If either is missing, unapproved, or the design direction is not yet selected, call spgr-escalate with the precise list of what is missing and stop. Do not infer a direction.
2. Build the site map as the hierarchical structure of all screens, grouped to reflect how a user understands the product rather than how the data is stored.
3. Write the screen inventory. List every screen with its name, purpose, entry points, and exit points. Entry points define how a user can reach the screen, and multiple entry points are common, so list all of them. Exit points define what a user can do from the screen, including navigate to, trigger, and dismiss.
4. Define the navigation model: primary navigation, secondary navigation, and contextual navigation patterns. Match the navigation model to the selected design direction's interaction model. If the requirements demand a navigation pattern the selected direction cannot support, call spgr-escalate rather than diverging from the direction.
5. Record the content hierarchy for the product: what content is prominent, what is secondary, and what is on-demand.
6. Add the screen-count metric to the artifact so the screen scope is a concrete number for sizing design and development effort.
7. Cross-reference the screen inventory against the user stories. Confirm every story maps to at least one screen. List any story with no associated screen and any screen that traces to no story. If a story has no screen, call spgr-escalate, because the inventory is incomplete or the story is out of design scope.
8. Set the confidence signal on each section (confirmed, proposed, or needs-human-input). Mark a section needs-human-input where the requirements or direction did not settle it.
9. Write the artifact with spgr-write-artifact and run spgr-validate-artifact inline. On a validation failure, fix the artifact and revalidate before returning. Log the IA decisions with spgr-log-decision.

## Notes

- Output type is an envelope artifact. The `ia` content type has no registered content schema yet, so spgr-validate-artifact falls back to envelope-only validation (header, confidence map, decision log, version) until a content schema is registered.
- The IA is the index for all subsequent design work, so completeness is the contract. Every screen in the product must appear in the screen inventory.
- An IA change after wireframes have started is a significant scope event. When asked to revise an IA whose wireframes are in progress, treat the change as a scope event and route it through spgr-escalate for human approval before applying it, then version the result with spgr-version-artifact.
- This artifact produces structured markdown only. It names screens, navigation, and content priority. It does not specify visual style, layout coordinates, or per-screen state design, which are downstream wireframe and design-system work.
