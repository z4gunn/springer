# Conversion fidelity

What survives a Mermaid-to-Excalidraw conversion and what degrades. Read this before the polish pass so you know which generic defaults to correct and which shapes to re-map. The conversion recovers topology and text only. Treat its output as a seed, never the deliverable.

## What survives

| Property | Outcome |
|----------|---------|
| Topology | Preserved. Nodes and the edges between them come through intact. |
| Node text | Preserved as readable words, one text element per node. |
| Edge labels | Preserved (for example the `Yes` and `No` branch labels on a flowchart). |
| Decision shape | A flowchart `{...}` decision node converts to an Excalidraw diamond. |
| Editability | Each node and edge is a separate, movable element on the convert and convert-then-verify routes. |

## What degrades

| Property | How it degrades | Polish action |
|----------|-----------------|---------------|
| Color | Returns generic Mermaid colors, not the semantic palette. | Re-apply the fill and stroke pairs from ~/.claude/skills/excalidraw-diagram/references/color-palette.md by each node's semantic purpose. |
| Layout | Returns Mermaid default auto-layout, often cramped, with wrapped labels (for example `Authenticate` and `d?` on two lines). | Re-space by hand, widen containers so labels fit on one line, balance whitespace. |
| Containers | A box is drawn around every node, including ones that read better as free-floating text. | Apply container discipline. Target under 30 percent of text inside boxes. |
| Hexagon `{{...}}` | Falls back to a rectangle. | Re-map to the intended shape or to free-floating text if the shape carried no meaning. |
| Cylinder `[(...)]` | Falls back to a rectangle. | Re-map, typically to a database or store representation per the element templates. |
| Subroutine `[[...]]` | Falls back to a rectangle. | Re-map to the intended call-out shape. |
| Evidence | None. The source carries no code snippets, data samples, or real event names. | Add the evidence artifacts the diagram needs for its audience. |

## The implication

Because color, layout, container choice, and shape vocabulary all degrade, a converted file that has not been through the polish pass fails the acceptance bar even though it converted cleanly. The acceptance criteria are the excalidraw-diagram quality bars, structure carries meaning and the render is balanced, not merely that the diagram converted.
