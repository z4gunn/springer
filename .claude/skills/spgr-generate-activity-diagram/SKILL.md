---
name: spgr-generate-activity-diagram
description: Produce a UML activity diagram or a flowchart as committed diagram-as-code (Mermaid flowchart by default, PlantUML activity for true swimlanes or formal fork and join) that shows the control and process flow of a workflow, algorithm, or business process, with branches, loops, concurrent work, and which actor performs each step, then render it to SVG and lint it for unmatched fork/join, unmatched decision/merge, and non-exhaustive guards. Use when the Architect agent models a pipeline or algorithm, the Product Manager maps a business workflow, or the Backend Developer reasons about a control-heavy procedure, and a process must be made explicit and reviewable before it is built or refactored. Do not use for time-ordered messages between participants (use spgr-generate-sequence-diagram), a single entity's lifecycle (use spgr-generate-state-diagram), the data model (spgr-generate-erd), C4 structure (spgr-generate-system-diagram), or deployment topology (spgr-write-infrastructure-diagram).
---

# generate-activity-diagram

## Purpose

Make a process explicit and reviewable before it is built or refactored. An activity diagram surfaces hidden branches, missing error paths, unsynchronized parallel work, and unclear ownership across actors, which are the defects that cost the most when found in code rather than on a diagram. This skill models control and process flow only. It does not restate the data model, the C4 structure, or the deployment topology, which belong to other diagram skills. The output is committed diagram-as-code (Mermaid or PlantUML source) plus a rendered SVG, kept in version control next to the code it documents, so it is regenerated from source rather than hand-edited and updated in the same commit as the workflow it depicts.

Read the shared family rules at .claude/references/diagram-standards.md and the notation decision at .claude/references/tool-selection.md before producing output. This skill adds only the activity-notation detail those files do not carry.

## Inputs

| Field | Description |
|-------|-------------|
| `process` | The business workflow, algorithm, or pipeline to model. The single question the diagram answers. |
| `actors` | The actors or components responsible for each step. Drives swimlanes when more than one participates. |
| `decisions` | The decision points, their guard conditions, and any concurrent work. |
| `objects` | Data objects passed between steps, where object flow matters rather than pure control. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Diagram source | A committed `.mmd` (Mermaid flowchart, the default) or `.puml` (PlantUML activity beta syntax) file, kept next to the code it documents. Cites the source artifact it is drawn from in a leading comment. |
| Rendered SVG | The compiled diagram, rendered and validated before delivery via the render script. |

## Procedure

1. Confirm this is a control-flow question, not another diagram type. A verb-phrase process with branches, loops, parallel steps, or actor lanes is an activity diagram. Time-ordered messages between participants are a sequence diagram, a single entity reacting to events is a state diagram, and data movement between processes and stores is a data-flow diagram, a distinct notation covered in [references/dfd-vs-activity.md](references/dfd-vs-activity.md). If the request is really one of those, name the mismatch and redirect rather than drawing the wrong model.

2. Choose the notation. Default to Mermaid flowchart for portability, since it renders inline in GitHub and Obsidian with no toolchain. Escalate to PlantUML activity, and state the reason in the diagram's leading comment, only when the process needs true swimlanes by responsibility or formal fork and join concurrency. Mermaid `subgraph` groups but does not partition by responsibility and has no fork primitive. Use swimlanes only when more than one actor participates, a single-actor process needs a plain flowchart.

3. Start from a golden template rather than a blank file. For a simple single-actor flow, copy [assets/simple-flowchart.mmd](assets/simple-flowchart.mmd). For a multi-actor responsibility flow, copy [assets/swimlane-activity.puml](assets/swimlane-activity.puml). For true concurrency, copy [assets/forkjoin-concurrent.puml](assets/forkjoin-concurrent.puml). Replace the leading source comment with the spec or artifact this diagram is drawn from.

4. Author the flow. For Mermaid syntax, node shapes, guards, and loops, read [references/mermaid-flowchart.md](references/mermaid-flowchart.md). For PlantUML beta syntax, swimlanes, and fork and join, read [references/plantuml-activity.md](references/plantuml-activity.md). Distinguish a decision (diamond, picks exactly one guarded branch) from a fork (bar, runs all branches concurrently). The glyph change is a semantic change. Pair every decision with a merge and every fork with a join. Put a guard on every outgoing decision edge and make the guard set mutually exclusive and exhaustive, including an explicit `else`.

5. Lint the source. Run the lint script, which flags an unmatched fork/join, an unmatched decision/merge, and a decision whose guards are not exhaustive (missing `else`). See [scripts/lint-diagram.sh](scripts/lint-diagram.sh). Fix every finding. The lint exits non-zero on any defect.

6. Render and validate. Run the render script to compile the source to SVG. See [scripts/render-diagram.sh](scripts/render-diagram.sh). It dispatches on extension (Mermaid for `.mmd`, PlantUML for `.puml`), fails on a non-zero exit, and fails when PlantUML writes an error annotation into the image. After it renders, confirm every declared node, lane, branch, and join is present in the output, since a silently dropped feature is the most dangerous failure. A diagram that has not been compiled and viewed is not done.

7. Commit the source and the rendered SVG together, in the same commit as the workflow they depict, citing the source artifact. For presentation-grade output, hand off to spgr-render-diagram-excalidraw rather than re-authoring by hand.

## Notes

- This is a diagram-as-code generation skill, not an envelope-artifact skill. It emits committed Mermaid or PlantUML source plus a rendered SVG and is verified by the render and lint scripts, not by a JSON schema. It does not call spgr-write-artifact and adds no schema.
- Run the scripts when their step says to: the lint before the render so a structural defect is caught before compile time, and the render before delivery. Both are tested against the golden templates in assets/.
- A data-flow diagram is an adjacent, distinct notation available on request. It shows data movement between processes and stores, not control flow, decisions, or sequencing. See [references/dfd-vs-activity.md](references/dfd-vs-activity.md). Do not conflate it with an activity diagram or flowchart.
