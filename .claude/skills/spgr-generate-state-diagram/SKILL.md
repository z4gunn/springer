---
name: spgr-generate-state-diagram
description: Produce a UML state machine diagram for one stateful entity as committed diagram-as-code (Mermaid stateDiagram-v2 by default, PlantUML state when the model needs history, entry/exit/do behaviors, internal transitions, or orthogonal regions) plus a rendered SVG, with transitions in canonical trigger[guard]/action form, one initial pseudostate per region, a final state, and durable behavior in entry, exit, or do. Use when the Architect Agent must capture the authoritative lifecycle of an entity such as an order, subscription, connection, document, job, or payment, naming its states and the events, guards, and actions that move between them, or when the Backend Developer Agent needs a verifiable contract for a status field and its allowed transitions before implementing it. Do not use for ordered messages between participants (use spgr-generate-sequence-diagram), for control or process flow with branches and lanes (use spgr-generate-activity-diagram), for static code structure (use spgr-generate-uml-class-diagram), or for the data model that holds the status field itself (use spgr-generate-erd).
---

# generate-state-diagram

## Purpose

Answer one question for one entity: what states does it occupy, and on what events, guards, and actions do transitions fire between them. The diagram is the authoritative lifecycle reference for that entity, so it prevents illegal transitions, unreachable states, and events left unhandled in a state, and it gives backend implementers a verifiable contract for a status field and its allowed changes. The output is committed diagram-as-code plus a rendered SVG kept in version control next to the entity it documents. This is not an envelope artifact. Do not call spgr-write-artifact and do not add a JSON schema. Emit the source and the SVG, render before delivery, and update both in the same commit as any lifecycle change.

## Inputs

| Field | Description |
|-------|-------------|
| `entity` | The single stateful entity to model, for example order, subscription, connection, document, job, or payment. One diagram models one entity. |
| `states_and_events` | The discrete states the entity can occupy, the events that can occur to it, and the condition under which each event fires. |
| `guards_and_actions` | The guard condition on each transition, and any entry, exit, do, or transition action tied to a state. |
| `lifecycle_shape` | Whether the lifecycle has nested sub-lifecycles, concurrent regions, or resume-after-interrupt behavior. This decides the renderer. |
| `erd_artifact` | The ERD artifact JSON that holds the entity's status enum, used by the consistency check. Read it from the project artifact store. |

## Outputs

| Artifact | Description |
|----------|-------------|
| State diagram source | A `.mmd` (Mermaid stateDiagram-v2) or `.puml` (PlantUML state) file, committed next to the code it documents, with transitions in canonical `trigger[guard]/action` form, one initial pseudostate per region, a final state, and durable behavior in entry, exit, or do. |
| Rendered SVG | The compiled diagram, rendered before delivery and committed in the same change. |

## Procedure

1. Confirm the request is one entity with a lifecycle. If the input describes ordered messages, a verb-phrase process, or static structure, stop and redirect to the sibling skill named in the description rather than modeling the wrong concern. Heuristic: a noun with a lifecycle is a state diagram.

2. Draft the state model in Mermaid stateDiagram-v2, the default for portability. Write every transition in canonical `trigger[guard]/action` form. Give every region exactly one initial pseudostate and add a final state. Put durable behavior in entry, exit, or do rather than duplicating an action on every inbound transition. Reserve a history pseudostate for a genuine resume-after-interrupt case, otherwise prefer an explicit initial substate. For the Mermaid syntax, see [references/mermaid-state.md](references/mermaid-state.md). Start from the linear golden in `assets/order-lifecycle.mmd` rather than a blank file.

3. Run the renderer-selection check on the draft before rendering. See [scripts/select-renderer.py](scripts/select-renderer.py). When it reports a PlantUML-only feature (history, entry/exit/do, internal transition, or orthogonal region), re-author the model in PlantUML state and run the script with `--stamp` so the escalation reason is recorded as a header comment in the source. For the PlantUML syntax, see [references/plantuml-state.md](references/plantuml-state.md) and the composite-with-history golden in `assets/subscription-lifecycle.puml`. Mermaid drops these four features silently, so the semantics vanish with a clean render. Never ship a Mermaid diagram the check flagged.

4. Lint the source for the four structural defects a renderer will not catch: unreachable states, states with no outgoing transition, events declared in the model vocabulary that no state handles, and non-exhaustive guards on a `<<choice>>` or `<<fork>>` branch. See [scripts/lint-state.py](scripts/lint-state.py). Declare the event vocabulary with an `%% events: ...` (Mermaid) or `' events: ...` (PlantUML) comment so the unhandled-event check has a baseline. Fix every finding. Either handle the event in the relevant state or document the implicit ignore.

5. Run the consistency check against the entity's status enum in the ERD. See [scripts/check-status-consistency.py](scripts/check-status-consistency.py). It reads the ERD artifact, validates it through the shared schema registry at schemas/ rather than restating field lists, extracts the status enum for the named entity, and compares it to the diagram states. Reconcile any drift so the diagram, the ERD, and the API spec agree on every state name. When the check reports no ERD status enum found, proceed. Not every entity carries an enumerated status.

6. Render the source to SVG and fail on any render error. See [scripts/render-validate.sh](scripts/render-validate.sh). A render that exits non-zero, stamps an error annotation into the SVG, or drops a declared element is a validation failure. Fix the source and re-render. The shared render-and-validate contract is in .claude/references/diagram-standards.md.

7. Commit the source and the SVG together, next to the code the entity belongs to. Cite the source the diagram is drawn from. When the diagram revises an existing one, ship the change in the same commit as the lifecycle change that caused it, so a stale diagram never contradicts reality.

8. If the lifecycle is too large to explain in one diagram, split it into composite states or a separate diagram per sub-lifecycle rather than over-detailing. If an input contradicts itself, names a state with no path to it that the inputs cannot resolve, or conflicts with the ERD status enum in a way the inputs cannot reconcile, stop and raise spgr-escalate with a precise list of what is missing or contradictory rather than guessing.

## Notes

- The notation policy and the Mermaid limitation list are in .claude/references/tool-selection.md. Do not restate them here.
- The diagram-as-code is the source of truth. Regenerate it from the source. Do not hand-edit the rendered SVG.
- The escalation reason recorded by the renderer-selection check is part of the deliverable. Keep it in the source so the renderer choice is traceable in the diff.
- The four scripts are deterministic checks rerun on every change, so they live in `scripts/` rather than being rewritten each run. The two golden templates in `assets/` are the starting points, so output is verified rather than improvised.
