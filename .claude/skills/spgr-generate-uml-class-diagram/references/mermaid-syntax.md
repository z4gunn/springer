# Mermaid classDiagram syntax

Glyph reference for Mermaid `classDiagram`, the standalone-Markdown class view only. Mermaid has no object-diagram and no true package-diagram type. The Mermaid limitation list and the Mermaid-versus-PlantUML decision table live in the shared reference at /Users/gunderer/Repos/springer/.claude/references/tool-selection.md. Run scripts/mermaid-trap-lint.sh before committing any Mermaid class view.

## Relationship glyphs

| Glyph | Relationship |
|-------|--------------|
| `<|--` | generalization (inheritance) |
| `..|>` | realization (interface implementation) |
| `*--` | composition |
| `o--` | aggregation |
| `-->` | association |
| `..>` | dependency |

The triangle, diamond, or arrowhead sits at the end of the glyph that points to it. `Refundable <|.. Card` and `Card ..|> Refundable` both render the realization with the hollow triangle at the interface.

## Members, visibility, classifiers

- Visibility: `+` public, `-` private, `#` protected, `~` package.
- Attribute: `+String name`. Operation: `+save(Item item) Result`.
- Abstract operation: append `*`, for example `+authorize(Money amount) AuthResult*`.
- Static member: append `$`, for example `-taxRate Decimal$`.
- Classifier annotation in the class body: `<<abstract>>`, `<<interface>>`, `<<enumeration>>`, `<<service>>`.
- Generic with a single type parameter: `Repository~T~`.

## Multiplicity and roles

Quote the multiplicity on each end and put the role after the colon:
```
Order "1" *-- "1..*" LineItem : contains
```

## Traps that route to PlantUML

These are GATEs, not warnings. The trap linter exits non-zero and the view must be regenerated as PlantUML:
- Comma-separated generic, for example `List~K,V~`. Mermaid breaks on the comma inside the tildes. Single-parameter generics such as `List~T~` are fine.
- Nested or multiple namespaces. Mermaid namespace support is fragile and does not nest.
- Package annotation, for example `<<package>>`. Mermaid carries no package annotation.

## Object and package views

Mermaid has no object-diagram type, so a runtime snapshot routes to PlantUML unconditionally. Mermaid has no true package-diagram type either. A flat package map can be approximated with a `flowchart TB` plus `subgraph` groups, acceptable only for a single-level Markdown map with no stereotypes and no nesting. State the approximation in the output.

## Golden template

Start from assets/templates/class.mmd. The package flowchart map is assets/templates/package.mmd.
