# Best practices

Quality guardrails for the class-diagram family, beyond the syntax. Family-wide rules (one question per diagram, model only what serves the question, version control, regenerate not hand-edit, render before delivery) live in the shared standards at .claude/references/diagram-standards.md. This file adds the static-structure-specific judgments.

## Ask the question first

Before generating, settle what the diagram must answer and for whom. A class diagram of "the whole codebase" is a wall of boxes that teaches nothing. Name the subsystem and the concern. If the request does not name a question, ask for one rather than guessing.

## Suppress boilerplate

Show only the members that serve the question. Drop trivial getters, setters, and default constructors. A reader infers accessors from a private field. Spend the diagram's attention on the behavior and the relationships that are not obvious from the code.

## Pick the relationship by lifecycle

The single most common error in this family is the wrong containment glyph:
- Composition (filled diamond) only when the whole owns the part's lifecycle and the part belongs to one whole.
- Aggregation (hollow diamond) when the part is shared or outlives the whole.
- Plain association otherwise.
The diamond always sits at the whole. Do not put it on the part. Do not draw realization (implements) as generalization (is a kind of).

## Always label multiplicities and roles

An edge with no multiplicity and no role is ambiguous. State the count at both ends and name the role. This is not optional decoration. It is the semantics of the relationship.

## Make the classifier kind visible

Use the native keyword or a stereotype so a reader sees interface, abstract, enum, or a domain role, not just a rectangle. PlantUML stereotype spots carry more fidelity than Mermaid annotations.

## Prefer several focused diagrams

Use a package diagram as the map and one class diagram per package for the detail. A package diagram that shows a cycle is reporting a design smell. Name the cycle and recommend the break rather than drawing it as if acceptable.

## Object diagrams validate, they do not duplicate

Draw an object diagram only to validate a class model against a concrete case or to clarify a confusing instance graph. Keep it a true snapshot of one moment. Do not mix instance-level and type-level content in one picture.

## Default to PlantUML

PlantUML natively renders all three types. Use Mermaid only for a standalone class view destined for Markdown, and only after scripts/mermaid-trap-lint.sh passes. State the chosen notation and the reason in the output. Keep the source in version control next to the code, regenerate it on change, and commit the regenerated SVG in the same change as the structure it documents.
