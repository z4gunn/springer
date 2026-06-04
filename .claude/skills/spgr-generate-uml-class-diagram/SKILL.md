---
name: spgr-generate-uml-class-diagram
description: Generate a UML class diagram of the code's static structure as committed diagram-as-code (PlantUML by default, Mermaid classDiagram for a standalone Markdown class view) plus a rendered SVG, covering classes, interfaces, enums, members and visibility, and the five relationship kinds with labelled multiplicities and roles, and the two supporting views in the same family, the object diagram (a runtime instance snapshot, PlantUML only) and the package diagram (module grouping and acyclic dependency direction). Use when the Architect, Backend Developer, or Frontend Developer agent needs a class diagram, an object diagram, a package diagram, or any code-level static-structure view before or during implementation so type relationships and module boundaries are agreed rather than discovered late. Defer component and deployment diagrams (C4 Level 1 and 2), composite-structure diagrams, and profile diagrams to spgr-generate-system-diagram, the data model to spgr-generate-erd, deployment topology to spgr-write-infrastructure-diagram, runtime message ordering to spgr-generate-sequence-diagram, and a GoF pattern applied to a problem to spgr-generate-design-pattern-diagram.
---

# generate-uml-class-diagram

## Purpose

Produce the code-level static-structure view: classes, interfaces, and enums, their members and visibility, and the relationships among them, so encapsulation, type relationships, and module boundaries are agreed before implementation drifts. Two supporting views ship in the same family. An object diagram validates a class model against a concrete runtime case. A package diagram exposes and governs dependency direction so layering stays acyclic. The output is committed diagram-as-code plus a rendered SVG, kept in version control next to the code it documents, not an envelope artifact. Default to PlantUML because it natively renders all three types. Use Mermaid only for a standalone class view destined for Markdown, and only after the trap linter confirms Mermaid can express it.

## Inputs

| Field | Description |
|-------|-------------|
| `domain-model` | Domain model or existing class, interface, and enum definitions. Read with spgr-read-file. |
| `design-question` | The one question the diagram must answer: which subsystem, which concern, which audience. |
| `module-layout` | Module or package layout, for a package diagram. |
| `scenario` | A concrete scenario or test fixture, for an object diagram. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Diagram source | A `.puml` (default) or `.mmd` (standalone Markdown class view only) file committed next to the code it documents. Class diagrams carry classifiers, members, visibility markers, abstract and static markers, generics, stereotypes, and the five relationship kinds with named roles and multiplicities at both ends. Object diagrams carry instance specifications with concrete slot values and links, no multiplicity, no operations. Package diagrams carry packages or namespaces with directional acyclic dependency arrows and import or access stereotypes. |
| Rendered SVG | The compiled output from scripts/render-and-verify.sh, committed in the same change as the source. |

## Procedure

1. Settle the question first. Confirm the diagram type (class, object, or package), the subsystem or concern, and the audience. If the request does not name a question, ask for one with spgr-escalate rather than drawing the whole codebase. See [references/best-practices.md](references/best-practices.md).

2. Confirm this is the right skill. Static code structure belongs here. Defer component and deployment views to spgr-generate-system-diagram, the data model to spgr-generate-erd, deployment topology to spgr-write-infrastructure-diagram, runtime ordering to spgr-generate-sequence-diagram, and a GoF pattern to spgr-generate-design-pattern-diagram. If the request is one of those, route to that skill instead of producing a degraded version here.

3. Read the inputs with spgr-read-file: the domain model or class definitions, the module layout for a package diagram, the scenario for an object diagram.

4. Choose the notation. Default to PlantUML. Use Mermaid only for a standalone class view destined for Markdown. An object diagram routes to PlantUML unconditionally, because Mermaid has no object-diagram type. The decision table is in the shared reference at /Users/gunderer/Repos/springer/.claude/references/tool-selection.md.

5. For any candidate Mermaid view, run scripts/mermaid-trap-lint.sh on the source before generating further. It is a GATE, not a warning. On a non-zero exit (a comma-separated generic, a nested namespace, or a package annotation), regenerate the view as PlantUML using the matching golden template. Do not ship the Mermaid version of a trapped view.

6. Generate the source from the matching golden template in assets/templates/ rather than from a blank file. Build the type-specific content per the reference for the chosen type: [references/class-diagram.md](references/class-diagram.md), [references/object-diagram.md](references/object-diagram.md), or [references/package-diagram.md](references/package-diagram.md). Use the exact glyphs in [references/mermaid-syntax.md](references/mermaid-syntax.md) or [references/plantuml-syntax.md](references/plantuml-syntax.md).

7. Apply the static-structure quality rules while generating. Model only the members that serve the question and suppress trivial getters, setters, and boilerplate. Pick the relationship by lifecycle: composition with the filled diamond only when the whole owns the part's lifecycle, aggregation with the hollow diamond for a shared or independent part, plain association otherwise, with the diamond always at the whole. Always label multiplicities at both ends and name the association role. Make the classifier kind visible with a keyword or stereotype. For a package diagram, flag any cyclic dependency as a design smell. For an object diagram, keep it a true snapshot and pair it with its class diagram. State the chosen notation and the reason in the output.

8. Render and validate. Run scripts/render-and-verify.sh on the source. It compiles the source to SVG and fails on a non-zero exit, an error annotation baked into the image, or a dropped relationship. A silently dropped relationship is the most dangerous failure, because it leaves a clean image with missing semantics. Fix the source and re-render until it passes. A diagram that has not compiled and rendered clean is not done.

9. Commit the source and the rendered SVG together, next to the code they document, in the same change as the structural change. Regenerate on change rather than hand-editing the rendered output.

## Notes

- The output is committed diagram-as-code plus a rendered SVG, verified by the render script in step 8, not an envelope artifact. This skill does not call spgr-write-artifact and adds no JSON schema.
- Family quality rules, the notation policy, and the render-and-validate commands are shared across the diagram family. See /Users/gunderer/Repos/springer/.claude/references/diagram-standards.md. The Mermaid-versus-PlantUML decision table and the Mermaid limitation list are at /Users/gunderer/Repos/springer/.claude/references/tool-selection.md. Do not restate them in the references here.
- scripts/render-and-verify.sh renders both notations, controls the output path with PlantUML `-pipe`, and counts declared versus rendered relationships to catch a silent drop. Run it on every generated source before delivery.
- scripts/mermaid-trap-lint.sh routes the three known Mermaid traps to PlantUML as a GATE. Run it on every candidate Mermaid source before generating further.
- Golden templates are in assets/templates/: class and package in both notations, object in PlantUML only. Mermaid has no object type, so there is no object.mmd, and the Mermaid package map is a flat flowchart approximation, not a true UML package diagram.
