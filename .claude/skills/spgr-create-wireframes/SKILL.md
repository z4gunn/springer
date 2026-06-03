---
name: spgr-create-wireframes
description: Produce a low-fidelity wireframe set as a markdown artifact, covering happy-path and edge-case screens for every primary user flow, with grayscale-only structure, labeled boxes for icons and imagery, per-screen annotations, and a review checklist that confirms empty, error, and loading states. Use when the Design Agent has a confirmed IA document and user stories and must validate flow and structure before any high-fidelity design begins, so structural problems surface while they are cheapest to fix.
---

# create-wireframes

## Purpose

Produce a low-fidelity wireframe set that communicates structure and flow without color, typography, or imagery, so structural and flow problems are caught at the wireframe stage before any visual polish is applied. The wireframe set is an envelope artifact written with spgr-write-artifact. It is reviewed and approved before high-fidelity design starts. A change to an approved wireframe after high-fidelity work has begun is a scope change and must be escalated.

## Inputs

| Field | Description |
|-------|-------------|
| `ia_document` | IA artifact with the screen inventory and navigation model. Read with spgr-read-artifact. Defines the set of screens to wireframe and how they connect. |
| `user_stories` | User stories whose acceptance criteria define the flows to cover. Read with spgr-read-artifact. Each wireframe references its corresponding story. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `wireframe-set` | Markdown artifact written with spgr-write-artifact. Contains happy-path wireframes for every primary flow, edge-case wireframes (empty, error, permission-denied, loading) for every key decision point, per-screen annotations of non-obvious interactions or content decisions, a screen-to-story and screen-to-IA-inventory reference on each wireframe, and the completed review checklist. |

## Procedure

1. Read the IA document with spgr-read-artifact to get the screen inventory and navigation model. Read the user stories with spgr-read-artifact to get the flows and acceptance criteria. If either input is missing, contradictory, or omits a screen referenced by a flow, stop and raise spgr-escalate with the precise list of what is missing rather than inventing screens.
2. Derive the set of primary user flows from the user-story acceptance criteria. Map each flow to its screens in the IA inventory. Confirm every screen in a flow exists in the inventory.
3. Wireframe the happy path for each primary flow. Keep fidelity low: grayscale only, no color, no real typography choices, no icons. Replace every icon and image with a labeled box that names what it stands for. The goal is structure and flow, not aesthetics.
4. Wireframe the edge cases at each key decision point. At minimum, produce an empty state, an error state, and a loading state for every screen that fetches data, plus a permission-denied state wherever access is gated.
5. Annotate each wireframe with the non-obvious interactions and content decisions a reader cannot infer from the layout alone.
6. Reference each wireframe to its corresponding story and to its screen in the IA inventory, so every wireframe traces back to an input.
7. Run the review checklist over the set. For every screen that fetches data, confirm it has an empty state, an error state, and a loading state. List any screen that fails a check and add the missing state before the artifact is marked confirmed.
8. For the highest-risk flows, recommend lightweight user testing on the wireframes before high-fidelity design proceeds, and note the recommendation in the artifact.
9. Write the wireframe set with spgr-write-artifact and run inline spgr-validate-artifact. Record the structural choices and any open questions with spgr-log-decision. Version the artifact with spgr-version-artifact.
10. If a flow cannot be wireframed within the confirmed IA (a screen is missing, a navigation path is undefined, or two stories contradict each other), stop and raise spgr-escalate. Do not fill the gap with an assumed screen or path.

## Notes

- Output type is an envelope artifact (wireframe-set). The wireframe-set content type has no registered content schema yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered. Still call spgr-validate-artifact inline.
- Low fidelity is a hard constraint, not a style preference. No color, no real typography, no icons. Labeled boxes stand in for every icon and image.
- The review checklist is the gate: every data-fetching screen must show an empty state, an error state, and a loading state before the artifact is confirmed.
- Wireframes are approved before high-fidelity design begins. A change to an approved wireframe after high-fidelity work has started is a scope change and is raised through spgr-escalate, not edited in silently.
- Set the confidence on each section per the contract: confirmed where the IA and stories fully support the screen, proposed for a structural choice that needs review, needs-human-input where a flow is ambiguous and was escalated.
