# Source-type decision tree

How to route a committed code-first source by type: convert editably, convert and verify, or re-author from an SVG seed. Read this before running the converter, because the route determines whether the converter output is a deliverable or only a reference image.

## Contents
- Routing table
- The three routes
- Verifying an experimental conversion

## Routing table

| Source | Type | Route |
|--------|------|-------|
| Mermaid | `flowchart` (and the `graph` alias) | Convert editably. The converter produces real Excalidraw elements. |
| Mermaid | `sequenceDiagram` | Convert, then verify. Native handler exists, editable-experimental. |
| Mermaid | `classDiagram` | Convert, then verify. Native handler exists, editable-experimental. |
| Mermaid | `stateDiagram-v2`, `erDiagram`, `gantt`, `pie`, `journey`, `mindmap`, any other type | Re-author. Render an SVG seed, rebuild natively. |
| PlantUML | any | Re-author. Render an SVG seed, rebuild natively. |

## The three routes

Convert editably. Run `scripts/mermaid_to_excalidraw.py`. The `.excalidraw` it writes is a true editable seed: every node and edge is a separate element you can move, recolor, and re-shape during the polish pass. This is the only route where the converter output is the starting point of the deliverable.

Convert, then verify. Run the converter the same way, then open the result and confirm the elements are individually editable and the topology is intact. The mermaid-to-excalidraw handlers for sequence and class diagrams are present but evolve between releases, so treat the per-diagram outcome as unverified until you have looked at it. If the elements come back as a single locked image or the topology is wrong, fall back to the re-author route.

Re-author from an SVG seed. The conversion library has no editable handler for these types. Render the source to SVG with the family render commands in the shared diagram standards (see .claude/references/diagram-standards.md), use that image only to understand topology and text, then build the diagram natively with the methodology and element templates from the global excalidraw-diagram skill (see ~/.claude/skills/excalidraw-diagram/SKILL.md, references/color-palette.md, references/element-templates.md). Conversion seeds understanding here, it does not produce the artifact. Embedding the SVG as one locked raster is acceptable only when an editable copy is not needed.

## Verifying an experimental conversion

For the verify route, check three things on the converted `.excalidraw`:
1. The element count matches the node and edge count in the source. A count of one means the library returned a single locked image, so re-author instead.
2. Selecting a node selects one element, not the whole diagram.
3. The edges connect the correct nodes, not a flattened or reordered topology.

Record the verified outcome with spgr-log-decision so the next maintainer does not re-test the same diagram type from scratch.
