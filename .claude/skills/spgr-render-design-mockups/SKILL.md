---
name: spgr-render-design-mockups
description: Turn a design-directions artifact into at least three clickable, multi-screen HTML mockups under docs/design/, one folder per direction covering the primary user flow with working links between screens, plus a docs/design/index.html entry point. Use when the Design Agent has generated design directions and the human needs to open the layouts in a browser to compare them before selecting a direction, where layout and information architecture are the point and style is deliberately low fidelity.
---

# render-design-mockups

## Purpose

The design-directions artifact describes each direction in prose. A human choosing a direction at the selection gate is better served by clickable layouts they can open in a browser and walk through. This skill reads the design-directions artifact and the backlog and emits static, self-contained HTML mockups, one folder per direction, covering the primary user flow with real links between screens, plus an index page that puts the directions side by side. The mockups are layout-and-IA studies, not visual comps. Style is intentionally low fidelity so the human compares structure, not color. The directions must differ in layout and information architecture, matching the design agent's genuinely-distinct requirement, not in palette or typeface. These are throwaway selection aids, the same spirit as spgr-create-prototype, not maintained deliverables and not application code.

## Inputs

| Field | Description |
|-------|-------------|
| `design_directions_artifact_path` | Path to the confirmed design-directions artifact in the run store. Read with spgr-read-artifact. |
| `story_backlog_path` | The confirmed backlog, read to derive the primary user flow and the screens that flow visits. |
| `docs_path` | Optional. The mockups root, default `docs/design/`. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Per-direction folders | `docs/design/<direction-slug>/` each holding a set of linked `.html` pages covering the primary flow, navigable by clicking. |
| `docs/design/index.html` | The entry point. Links to every direction and names what makes each distinct, so the human starts here. |
| `docs/design/mockup.css` | The single shared low-fidelity stylesheet, copied from this skill's assets. |
| `mockup_report` | The list of paths written and the screen count per direction, returned to the calling agent for the HIL notification. |

## Procedure

1. Read the design-directions artifact with spgr-read-artifact. If it is missing, fails validation, or holds fewer than three directions, do not proceed. Raise spgr-escalate with the precise gap. Three directions is a hard floor, the same floor the generating skill enforces.

2. Read the backlog with spgr-read-artifact and derive the primary user flow: the ordered set of screens a core persona passes through for the main job. This screen sequence is the spine every direction renders, so the human compares the same flow across directions. Keep the set small, the primary flow only, not every screen.

3. For each direction, choose a slug from the direction name and create `docs/design/<direction-slug>/`. Render one `.html` page per screen in the flow. Each page lays out that screen according to the direction's information architecture and interaction model: its navigation placement, content density, and hierarchy. Two directions must produce visibly different layouts of the same screen, because that structural difference is what the human is choosing between.

4. Make the flow clickable. Every page carries working `<a href>` links to the next and previous screens in the flow and to the direction's first screen, using relative paths so the mockup works from `file://` with a double click. The primary action on each screen links to the screen it would advance to. See [references/mockup-construction.md](references/mockup-construction.md) for the page skeleton and the linking rules.

5. Keep fidelity low and layout focused. Use semantic HTML and the shared `docs/design/mockup.css` only. Use labeled placeholder boxes for images, charts, and media that name what they stand for. No real branding, no design tokens, no JavaScript, no framework, no external assets or web fonts. The construction details and the labeled-placeholder convention are in [references/mockup-construction.md](references/mockup-construction.md).

6. Copy the shared stylesheet from this skill's [assets/mockup.css](assets/mockup.css) to `docs/design/mockup.css` and have every page link it by relative path. Do not inline styles per page beyond the structural layout that defines the direction, so the comparison stays about layout rather than surface styling.

7. Write `docs/design/index.html`. List the directions with a short, neutral description of what makes each structurally distinct (navigation model, density, interaction paradigm, content hierarchy), and link to each direction's first screen. This page is the human's starting point at the selection gate.

8. Write every file with spgr-write-file. Confirm each path stays under the repository root, which the write-file boundary enforces. Return `mockup_report` with the paths and the per-direction screen count so the calling agent can reference `docs/design/index.html` in the selection notification.

## Notes

- These mockups are not typed artifacts. They carry no envelope and no schema. Do not route them through spgr-write-artifact. The design-directions artifact in the run store stays the source of truth, and the mockups are a regenerable rendering of it.
- This skill does not select a direction and does not begin detailed design. It produces the comparison aid for the one design HIL gate. The human selects, the agent does not.
- The mockups cover the primary flow only. They are not a screen inventory and not a prototype for usability testing, that is spgr-create-prototype's job after a direction is chosen.
- This skill has no Phase 1 vault spec. It was authored to the Springer build standards as a net-new capability, so there is no "Phase 2 Build Notes" brief to map from.
- Construction details, the page skeleton, the linking rules, and the labeled-placeholder convention are in [references/mockup-construction.md](references/mockup-construction.md). Read it before generating pages.
