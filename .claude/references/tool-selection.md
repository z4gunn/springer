# Diagram tool selection

Per-diagram-type guidance for choosing Mermaid or PlantUML, with the Mermaid limitation list. Shared by the Springer diagram skill family. Escalate from the default on the triggers below and record the notation and reason in the output.

## Contents
- Decision table
- Mermaid limitation list

## Decision table

| Diagram | Default | Use the other notation when |
|---------|---------|------------------------------|
| Class, object, package | PlantUML | Mermaid `classDiagram` is acceptable only for a standalone class view destined for Markdown. Stay on PlantUML for object diagrams, nested packages or namespaces, package annotations, association classes, custom stereotype spots, precise per-edge layout, and comma-separated generics. |
| Sequence | Mermaid `sequenceDiagram` | richer fragments, a true communication or object view, `autoactivate`, object creation, or finer styling Mermaid cannot express. |
| State | Mermaid `stateDiagram-v2` | history pseudostates, entry, exit, or do behaviors, internal transitions, or orthogonal regions. |
| Activity | Mermaid `flowchart` | true swimlanes by responsibility, or formal fork and join concurrency. |
| Design pattern | PlantUML | Mermaid `classDiagram` plus `sequenceDiagram` only as a reduced-fidelity Markdown fallback. |

## Mermaid limitation list
- No object diagram type. Use the PlantUML `object` keyword.
- Fragile nested namespace support and no package annotations.
- Breaks on comma-separated generics such as `List~K,V~`.
- No communication diagram type. Approximate with a numbered flowchart or switch to PlantUML.
- `stateDiagram-v2` silently drops history (`[H]`, `[H*]`), entry, exit, and do behaviors, internal transitions, and orthogonal regions. The semantics vanish with no error.
- `subgraph` groups but does not partition by responsibility. Swimlane support is experimental.
- `classDiagram` carries reduced stereotype fidelity versus PlantUML spots.

When you escalate, state the notation and the trigger in the output. Example: `PlantUML: model uses shallow history, unsupported by Mermaid stateDiagram-v2`.
