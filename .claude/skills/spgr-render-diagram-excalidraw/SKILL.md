---
name: spgr-render-diagram-excalidraw
description: Convert a committed code-first diagram (Mermaid or PlantUML) into an editable .excalidraw file, apply presentation polish, and render a PNG, while the code-first source stays authoritative. Use when the Documentation, Architect, or Design agent needs a human-facing version of a generated diagram for an onboarding deck, a design review, or docs, without forking the diagram away from its committed source. This is the only presentation and rendering skill in the diagram family. It authors no model.
---

# render-diagram-excalidraw

## Purpose

The code-first `generate-*` diagram siblings render inline in GitHub and Obsidian but look generic. Produce a polished, human-facing copy without forking the model. The committed Mermaid or PlantUML source stays the single source of truth, and the `.excalidraw` output is a regenerable presentation copy. Layer on the global excalidraw-diagram skill rather than duplicate it: reuse its argue-not-display methodology, its color palette, and its element templates by absolute path. This skill adds only the conversion front end and the polish gate. It authors no diagram content from scratch and owns no model, so when the source changes, regenerate from the source rather than hand-editing the copy.

## Inputs

| Field | Description |
|-------|-------------|
| `source` | A committed code-first diagram, Mermaid or PlantUML. Read it with spgr-read-file. The diagram-as-code stays authoritative. |
| `purpose-and-audience` | What question the diagram answers and for whom. Drives depth, evidence, and the polish pass. |
| `excalidraw-diagram conventions` | The global skill's methodology, palette, and templates, read by absolute path: ~/.claude/skills/excalidraw-diagram/SKILL.md, references/color-palette.md, references/element-templates.md. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `<name>.excalidraw` | The editable presentation copy, committed next to the source. |
| `<name>.png` | The rendered PNG for docs and presentations, committed next to the source. |
| Unchanged source | The original Mermaid or PlantUML source, still authoritative. |

## Procedure

1. Read the source with spgr-read-file and confirm its type. Read the purpose and audience. If either is missing, stop and raise spgr-escalate with the precise gap rather than guessing the audience or the diagram's question.

2. Route by source type. See [references/source-type-decision-tree.md](references/source-type-decision-tree.md). A Mermaid `flowchart` converts to editable elements. Mermaid `sequenceDiagram` and `classDiagram` convert but are editable-experimental, so verify the output per diagram. All other Mermaid types and all PlantUML re-author from an SVG seed rather than convert.

3. On a convert route, run the converter against the source. It parses the Mermaid in a real DOM (not jsdom, which lacks the `getBBox` layout the library needs), serializes a valid `.excalidraw` file, and renders a first PNG. See [scripts/mermaid_to_excalidraw.py](scripts/mermaid_to_excalidraw.py). Run it with the global skill's Playwright venv interpreter:
   `~/.claude/skills/excalidraw-diagram/references/.venv/bin/python scripts/mermaid_to_excalidraw.py <source.mmd>`
   On the convert-then-verify route, confirm the elements are individually editable using the checks in the decision tree before treating the output as a seed. If the script exits non-zero, read its stderr and act on it. A modules-did-not-load error means the runtime had no network access to esm.sh (see Notes).

4. On a re-author route, render the source to SVG with the family render commands in .claude/references/diagram-standards.md, then build the diagram natively from the global skill's methodology and element templates. The SVG seeds understanding, it does not produce the artifact.

5. Run the mandatory polish pass on the converted or re-authored elements. See [references/conversion-fidelity.md](references/conversion-fidelity.md) for what degrades and [references/polish-checklist.md](references/polish-checklist.md) for the four criteria. Re-apply the semantic palette, re-space the auto-layout, widen containers so labels fit on one line, re-map degraded shapes (hexagon, cylinder, subroutine fall back to rectangle), enforce container discipline under 30 percent of text inside boxes, and add the evidence the source lacks. Satisfy isomorphism, evidence, multi-zoom, and container discipline.

6. Render the polished PNG and read it. This step is mandatory, not a final check. Re-run the converter, or run the global skill's render path for a re-authored file, then Read the PNG. Audit it against the conceptual design and fix overlaps, clipping, wrapped labels, and auto-layout cramping. Iterate the convert-or-polish, render, read, fix loop until the render is balanced and every label reads on one line.

7. Validation gate. The acceptance bar is the excalidraw-diagram quality bars, structure carries meaning and the render is balanced, not merely that the diagram converted. Confirm the source is unchanged and authoritative. Commit the `.excalidraw` and the PNG next to the source in the same commit as any source change they depict. Record the route taken and any experimental-conversion outcome with spgr-log-decision.

## Notes

- The spec line "Register the skill and any new script in README.md" is inherited from the external excalidraw-diagram skill and does not apply here, because Springer's CLAUDE.md forbids skill READMEs.
- This skill is presentation and rendering only. It owns no model. generate-erd, generate-system-diagram, write-infrastructure-diagram, and the UML `generate-*` siblings own their notations, per .claude/references/diagram-standards.md. This skill consumes their output and polishes it.
- The converter and its render template depend on esm.sh at runtime to fetch the pinned conversion libraries. The step needs network access. A missing network surfaces as a modules-did-not-load error from the script.
- Library versions are pinned in [assets/convert_template.html](assets/convert_template.html): `@excalidraw/mermaid-to-excalidraw@1.1.2` and `@excalidraw/excalidraw@0.18.0`. The template is this skill's own, not the global skill's, whose unpinned import is currently broken by an esm.sh transitive 404. Upstream releases on a modest cadence, so revalidate the pins after an upstream upgrade.
- The built-in Excalidraw GUI Mermaid-to-Excalidraw dialog is a manual spot-check only. It is not scriptable and is not the automated path this skill uses.
