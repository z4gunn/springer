# Package diagram

How to build a package diagram: module grouping and dependency direction, used to expose and govern layering. Notation glyphs live in plantuml-syntax.md. Family quality rules and the render loop live in the shared standards at .claude/references/diagram-standards.md.

## What a package diagram is

A package diagram groups classes into packages or namespaces and draws the dependency arrows between them. It is the map of the system's module structure. Use it to make layering explicit, to show which package depends on which, and to govern that dependency direction so the layering stays acyclic.

## Dependency direction and stereotypes

- An arrow points from the package that depends to the package it depends on.
- `<<import>>` brings the target's public names into the source namespace.
- `<<access>>` uses the target without importing its names.
- Point dependencies toward the stable core. A presentation package depends on a domain package, not the reverse.

## Cyclic dependencies are a design smell

A cycle in the package graph means two packages cannot be understood, tested, or deployed independently. Flag every cycle as a design smell in the output. Do not silently draw the cycle as if it were acceptable. Name the packages in the cycle and recommend the inversion or extraction that breaks it.

## Nested packages route to PlantUML

PlantUML renders nested `package`/`namespace` natively. Mermaid has fragile nested-namespace support and carries no package annotations, so any nested-package or annotated-package request routes to PlantUML through the trap linter. The lightweight Mermaid alternative is a single-level flowchart with subgraphs, acceptable only for a flat Markdown map with no `<<import>>` or `<<access>>` stereotype and no nesting. The flowchart approximation is not a true UML package diagram, so state the limitation in the output when you use it.

## Map first, detail second

Use the package diagram as the map and class diagrams for the detail inside each package. One package diagram answers one question: what depends on what, and is the layering acyclic. Do not crowd it with class members.

## Rendering

Generate the source as `.puml` for the full UML package diagram, or `.mmd` for the flat flowchart map. Render with scripts/render-and-verify.sh. Golden templates are assets/templates/package.puml and assets/templates/package.mmd.
