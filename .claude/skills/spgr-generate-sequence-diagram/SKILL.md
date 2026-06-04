---
name: spgr-generate-sequence-diagram
description: Produce a UML sequence diagram as committed Mermaid or PlantUML source plus a rendered SVG that shows, for one scenario, how participants collaborate over time through ordered messages, with lifelines, activation bars, synchronous and asynchronous and return arrows, self-calls, object creation, and combined fragments (alt, opt, loop, par), and a communication-diagram view on request. Use when the Architect designs an interaction, the Backend Developer implements a call protocol, or the API Design Agent defines call ordering for one flow, and the deliverable is the time-ordered interaction between participants rather than data model, C4 structure, or deployment topology.
---

# generate-sequence-diagram

## Purpose

Capture the message protocol for one scenario as diagram-as-code: who calls whom, in what order, synchronous versus asynchronous, request versus response, so contributors agree on the runtime contract before implementation. It answers one question for one scenario, how participants interact over time. Emit committed Mermaid or PlantUML source and a rendered SVG kept in version control next to the code the diagram depicts. This is not an envelope artifact. Do not call spgr-write-artifact and do not add a JSON schema. The source plus the rendered SVG are the deliverable.

## Inputs

| Field | Description |
|-------|-------------|
| `scenario` | One interaction scenario, API protocol, or user story for a single flow. One diagram covers one scenario for one audience. |
| `participants` | The actors, services, components, or objects involved, named with stable domain aliases. |
| `semantics` | Sync versus async per message, and the branch, optional, loop, and concurrency conditions for the scenario. |
| `view` | Optional. A communication view (linked participants, decimal-numbered messages) instead of the default time-axis layout. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Sequence-diagram source | Mermaid `sequenceDiagram` by default, or PlantUML on an escalation trigger. Participants with lifelines, activation bars, synchronous (`->>`), asynchronous (`-)`), and return (`-->>`) messages, self-calls, object creation and destruction, and combined fragments (`alt`, `opt`, `loop`, `par`, and where needed `critical`, `break`, `ref`). Committed next to the code. |
| Rendered SVG | The compiled output from scripts/render-sequence.sh, committed alongside the source. |
| Communication view (on request) | The same interaction by link topology with decimal-numbered messages, via PlantUML or the Mermaid numbered-flowchart approximation, with the chosen tool and reason stated. |

## Procedure

1. Confirm the deliverable is interaction over time for one scenario. If it is process flow with responsibility lanes use spgr-generate-activity-diagram, a single entity lifecycle use spgr-generate-state-diagram, static structure use spgr-generate-uml-class-diagram, the data model use spgr-generate-erd, C4 structure use spgr-generate-system-diagram, and deployment topology use spgr-write-infrastructure-diagram. If the input names no concrete scenario, no participants, or contradicts itself on sync versus async, stop and raise spgr-escalate with the precise gap. Do not assume a protocol.

2. Select the notation. Default to Mermaid `sequenceDiagram`. Escalate to PlantUML only on a trigger in /Users/gunderer/Repos/springer/.claude/references/tool-selection.md: richer fragments, a true communication or object view, `autoactivate`, object creation, or finer styling Mermaid cannot express. State the notation and the trigger in the source as a comment when you escalate.

3. Author the source from the matching golden template so output stays consistent across runs. For Mermaid, copy from assets/mermaid/ (`sync-request-response.mmd`, `async-fire-and-forget.mmd`, `alt-opt-loop.mmd`). For PlantUML, copy from assets/plantuml/ with the same three names. For the message arrows, activation, and fragment rules, read references/mermaid-sequence.md or references/plantuml-sequence.md.

4. Declare participants up front with stable domain aliases. Show the messages that carry the scenario and no more. Reserve the async open arrow for genuinely non-blocking calls. Turn on `autonumber` when call ordering is part of the deliverable. Keep activation open and close in one style, either the `+`/`-` suffix or explicit `activate`/`deactivate`, never one of each for the same bar.

5. Split, do not deep-nest. When a scenario branches into a happy path and an error path, produce two diagrams rather than nesting combined fragments deeply, which is the top readability killer.

6. For a communication view, use PlantUML's communication form, or approximate it in Mermaid with a numbered flowchart, since Mermaid has no communication-diagram type. State the chosen tool and reason. See references/mermaid-sequence.md for the flowchart approximation.

7. Validation gate. Run scripts/render-sequence.sh on every source file. It runs scripts/lint-sequence.sh first to flag any `alt`, `opt`, `loop`, or `par` missing its `end` and any `activate` missing its `deactivate`, then compiles with mmdc or plantuml.jar and fails on a non-zero exit or an error annotation drawn into the SVG. A render that exits non-zero, draws an error into the image, or drops a declared participant is a validation failure. Fix the source and re-render. Do not deliver an uncompiled diagram.

8. Commit the source and the rendered SVG together, in the same commit as the code or spec change they depict. Regenerate from the source on every change. Never hand-edit the rendered SVG.

## Notes

- The output is committed diagram source plus a rendered SVG, verified by the render-and-validate script, not by an envelope schema. Do not call spgr-write-artifact for this skill.
- Cross-cutting diagram quality rules (one question per diagram, source of truth, render before delivery, cite the source) live in /Users/gunderer/Repos/springer/.claude/references/diagram-standards.md. The notation decision table and the Mermaid limitation list live in /Users/gunderer/Repos/springer/.claude/references/tool-selection.md. Do not restate them here.
- Keep use-case, interaction-overview, and timing diagrams out of scope. This skill owns interaction over time only.
- For presentation-grade output, hand the committed source to spgr-render-diagram-excalidraw rather than re-authoring by hand.
- scripts/render-sequence.sh is the validation gate. Run it before every delivery. scripts/lint-sequence.sh is the structural balance check it calls first, and can also run standalone on a draft. assets/mermaid/UNBALANCED-do-not-ship.mmd is a deliberately broken fixture for testing the lint, not a template.
