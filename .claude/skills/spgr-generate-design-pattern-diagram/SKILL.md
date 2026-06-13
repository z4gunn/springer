---
name: spgr-generate-design-pattern-diagram
description: Produce a paired view of how one Gang of Four design pattern is applied to real code, a structure class diagram (abstract roles plus the concrete classes bound to each role via a stereotype) and a collaboration sequence diagram of the pattern's signature runtime scenario, with an intent-and-consequences note, in PlantUML by default or reduced-fidelity Mermaid for Markdown embed. Use when the Architect, Code Reviewer, or Backend Developer agent must document or review a named GoF pattern as it is used in the system, not for a generic class or sequence diagram and not when the code does not actually exhibit the pattern's forces.
---

# generate-design-pattern-diagram

## Purpose

Make one Gang of Four pattern's application to a specific problem legible and reviewable. Emit two paired views: a structure class diagram and a collaboration sequence diagram. Bind every canonical role (Context, Strategy, Subject, Component, and so on) to the real class that plays it, so a reader recognizes the pattern on sight and can trace it to code. Carry the intent the pattern resolves and the tradeoff it incurs onto the diagram, so a pattern is documented only when the code exhibits its defining forces, not because the shape looks familiar. This builds on the class-diagram and sequence-diagram notations and adds pattern awareness: canonical role vocabulary, the anti-cargo-cult force check, and the intent caveat.

## Inputs

| Field | Description |
|-------|-------------|
| `pattern` | One of the 23 GoF patterns by name. Drives role vocabulary and sequence shape via the catalog. Read with spgr-read-file. |
| `concrete-classes` | The real classes in the system that play the pattern's roles, with the source file each lives in. Cite these on the diagram. |
| `intent-and-forces` | The problem the pattern resolves, its defining forces, and the known tradeoffs the application incurs. The force list feeds the pre-generation guard. |
| `notation` | `plantuml` (default) or `mermaid` (reduced-fidelity Markdown fallback). Mermaid only when the pair must embed inline in a README or Obsidian note. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Structure view (abstract) | A class diagram using only canonical GoF role names, showing only the members that explain the mechanics. Committed source plus rendered SVG. |
| Structure view (concrete) | The same class diagram with each real class bound to its role via a stereotype, for example `OrderValidator <<ConcreteStrategy>>`. Committed source plus rendered SVG. |
| Collaboration view | A sequence diagram of the pattern's signature scenario from the catalog, for example Observer `notify()` looping `update()` over observers. Committed source plus rendered SVG. |
| Intent and consequences note | A note or legend on the structure view stating the problem solved and the cost incurred. |

These are committed diagram-as-code (`.puml` or `.mmd`) plus their rendered `.svg`, kept in version control next to the code they document. This skill does not emit a JSON envelope artifact and does not call spgr-write-artifact.

## Procedure

1. Read the shared diagram standards at `.claude/references/diagram-standards.md` and the tool selection table at `.claude/references/tool-selection.md`. Follow the family quality rules and the render-and-validate loop. Do not restate them.

2. Look up the named pattern in [references/pattern-catalog.md](references/pattern-catalog.md). Take its GoF category, its canonical role list, and its signature collaboration scenario. Use this vocabulary exactly. Do not invent role names. If the requested pattern is not one of the 23 GoF patterns, stop and raise spgr-escalate naming the unknown pattern, since this skill owns GoF patterns only.

3. Run the anti-cargo-cult guard before generating anything. See [scripts/check-pattern-forces.sh](scripts/check-pattern-forces.sh). It takes the pattern name and the supplied force descriptions and confirms the pattern's defining forces are present. If a defining force is missing, the guard exits non-zero and names the missing force. Do not generate the diagram. Raise spgr-escalate with the guard output, since a pattern diagram over needless indirection teaches the wrong lesson.

4. Select the notation. Default to PlantUML for native `<<Role>>` stereotype spots, abstract and interface keywords, and full relationship arrows. Use Mermaid only when the pair must embed inline in Markdown, and state the reduced stereotype fidelity in the output. For the per-glyph syntax see [references/plantuml-syntax.md](references/plantuml-syntax.md) or [references/mermaid-syntax.md](references/mermaid-syntax.md).

5. Generate the structure view (abstract). Copy the matching golden example under [assets/](assets/) for the pattern's category and adapt it. Import the shared preamble [assets/pattern-preamble.iuml](assets/pattern-preamble.iuml) at the top of every PlantUML structure diagram so all patterns render uniformly. Use the canonical role names from the catalog as the class names. Pick the relationship glyph by meaning: inheritance `<|--`, realization `<|..` (dashed), composition `*--` only when the whole owns the part's lifecycle, aggregation `o--` for shared parts, dependency `-->` or `..>`. Show only the members that teach the pattern.

6. Generate the structure view (concrete) from the abstract view. Replace each abstract role class with the real class from `concrete-classes`, bind it to its role with a stereotype (`RealClass <<RoleName>>`), and cite the source file. Keep the same relationships.

7. Generate the collaboration view as a sequence diagram of the catalog's signature scenario for this pattern. Name the lifelines with the concrete classes. Show the messages that carry the pattern's mechanics, for example the invoker calling `execute()` then the receiver `action()` for Command. Reserve the async open arrow for genuinely non-blocking calls.

8. Add the intent-and-consequences note to the structure view: one line for the problem solved, one line for the cost incurred.

9. Render and validate every view. See [scripts/render-pattern.sh](scripts/render-pattern.sh), which renders both the structure diagram and the collaboration sequence to SVG and fails on a non-zero exit, an error annotation in the image, or a dropped element. Fix the source and re-render until clean. A view that has not rendered cleanly is not done.

10. Commit the diagram-as-code and the rendered SVG next to the code they document, in the same commit as any refactor that changed the pattern. Record the pattern, the role-to-class bindings, and the force check with spgr-log-decision so the reasoning is traceable.

## Notes

- Always emit both views. A structure diagram alone hides how the pattern behaves, which is the most common documented omission.
- One pattern, one applied problem, one diagram pair. If a second pattern is in play, draw a second pair.
- Boundary: this owns design-pattern application. The data model is spgr-generate-erd, high-level system structure and C4 is spgr-generate-system-diagram, deployment topology is spgr-write-infrastructure-diagram, and a generic class or sequence view is spgr-generate-uml-class-diagram or spgr-generate-sequence-diagram.
- Regenerate from source on change. Do not hand-edit the rendered SVG.
- The output is committed source and SVG verified by the render script and by review, not by a JSON schema.
