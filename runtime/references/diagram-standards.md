# Diagram standards (shared)

Cross-cutting rules for the Springer code-first diagram skill family: generate-uml-class-diagram, generate-sequence-diagram, generate-state-diagram, generate-activity-diagram, generate-design-pattern-diagram, and the presentation skill render-diagram-excalidraw. Each skill references this file by absolute path and adds only its own notation-specific detail. The data model, C4, and deployment diagrams stay with generate-erd, generate-system-diagram, and write-infrastructure-diagram.

## Contents
- Family quality rules
- Notation policy
- Render and validate
- Boundaries

## Family quality rules
1. One diagram answers one question for one audience at one altitude. Prefer several focused diagrams over one wall of detail.
2. Model only what serves the question. Suppress boilerplate such as trivial getters and setters. Over-detail drowns the structure.
3. The diagram-as-code is the source of truth. Keep it in version control next to the code it documents.
4. Regenerate from the source. Do not hand-edit rendered output.
5. Update the diagram in the same commit as the change it depicts. A stale diagram that contradicts reality is worse than none.
6. Cite the source the diagram is drawn from: the spec, the class, the entity, or the scenario.
7. Render before delivery. A diagram that has not been compiled and viewed is not done.

## Notation policy
Default to the notation named per diagram type in tool-selection.md. Mermaid is preferred where it suffices, because it renders inline in GitHub and Obsidian with no toolchain. Escalate to PlantUML only when the model needs a feature the default cannot express, and state the chosen notation and the reason in the output. The per-diagram escalation triggers and the Mermaid limitation list live in tool-selection.md.

## Render and validate
Every generate skill compiles its output before delivery and fails on a parse error or a silently dropped feature.
- Mermaid: `npx @mermaid-js/mermaid-cli@11 -i <src>.mmd -o <out>.svg`
- PlantUML: `java -jar ~/.plantuml/plantuml.jar -tsvg <src>.puml`
- PlantUML class diagrams, composite state diagrams, and swimlaned activity diagrams need Graphviz. Confirm with `dot -V`.

A render that exits non-zero, emits an error annotation in the output image, or drops a declared element is a validation failure. Fix the source and re-render. Treat a silently dropped feature as the most dangerous failure, because it leaves a clean render with missing semantics.

## Boundaries
- generate-erd owns the data model: entities, attributes, and PII markers.
- generate-system-diagram owns C4 Level 1 and Level 2: system context and components.
- write-infrastructure-diagram owns deployment and infrastructure topology.
- The five UML notations own static structure, interaction over time, entity lifecycle, process flow, and pattern application, one concern each.
- render-diagram-excalidraw owns presentation rendering only. It authors no model.
