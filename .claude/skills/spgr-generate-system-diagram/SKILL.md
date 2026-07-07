---
name: spgr-generate-system-diagram
description: Produce a system-diagram artifact holding C4 Level 1 context and Level 2 component diagrams in Mermaid, showing users, external systems, internal components, and their relationships. Use when the Architect Agent needs a shared structural view of an approved architecture, or when an architectural change must update the diagram in the same commit.
---

# generate-system-diagram

## Purpose

Build the system-diagram artifact for an approved architecture so every agent and human shares one mental model of who uses the system, what it touches externally, and how its internal components relate. The artifact carries two C4 levels, a Level 1 system context for business and technical readers and a Level 2 component view for technical contributors. Diagrams are version-controlled Mermaid so they live alongside the code and stay reviewable in a diff.

## Inputs

| Field | Description |
|-------|-------------|
| `architecture_decision` | The approved architecture option or ADR that fixes the structure to diagram. |
| `components` | The list of services, modules, and significant libraries with their responsibilities. |
| `external_dependencies` | Third-party APIs, data stores, auth providers, and messaging systems the system interacts with. |
| `actors` | The human and system users that initiate interactions with the system. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `system-diagram` | A system-diagram artifact with a Level 1 system context diagram and a Level 2 component diagram, each as Mermaid, with labeled relationships. Written and validated through the plumbing skills. |

## Procedure

1. Read the approved architecture through spgr-read-artifact and confirm it is human-approved. If it is proposed or needs-human-input, do not diagram an unapproved structure. Raise the gap with spgr-escalate.
2. Confirm the component list, external dependencies, and actors are present and consistent with the architecture. If a component appears in the architecture but is missing from the input list, or the lists contradict the architecture, stop and call spgr-escalate with the precise contradiction rather than inferring the missing element.
3. Draw the Level 1 system context. Show the system as a single box, every actor, and every external system. Label each relationship with what data flows and in which direction. Keep this level free of implementation jargon so non-technical stakeholders can read it.
4. Draw the Level 2 component diagram. Show each internal component as a box where one box is a deployable or logically cohesive unit, state its responsibility, and draw the relationships between components and to external systems. Add a Level 3 container or code diagram only for the most complex or highest-risk components, not by default.
5. Encode both diagrams as Mermaid so they version-control and review in a diff. Note any presentation-only Excalidraw export as a derived view, not the source of truth.
6. Record any non-obvious modeling choice with spgr-log-decision, for example collapsing several modules into one component box or omitting a minor dependency.
7. Write the artifact through spgr-write-artifact, which runs spgr-validate-artifact against the registered system-diagram schema inline before the write completes. Resolve any reported issue before handoff.
8. When this diagram revises an existing one, stamp the new version with spgr-version-artifact and ship the change in the same commit as the architectural change that caused it, so a stale diagram never contradicts reality.

## Notes

- This skill produces the diagram only. Artifact envelope, header, confidence map, and decision log are handled by spgr-write-artifact and spgr-read-artifact. Schema fields live in the registry at schemas/ and are checked by spgr-validate-artifact, not restated here.
- The output type system-diagram is a registered schema, so the write validates against an envelope schema with no further setup.
- A diagram that contradicts the current architecture is worse than no diagram. Update it in the same commit as the change, or escalate if the change cannot be diagrammed within the approved architecture.
