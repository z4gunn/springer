# Polish checklist

The four mandatory criteria a presentation copy must meet before it is delivered. Run every criterion. A converted diagram that skips the polish pass fails the acceptance bar even when the conversion was clean. The full design methodology behind these criteria lives in /Users/gunderer/.claude/skills/excalidraw-diagram/SKILL.md, the argue-not-display skill. This file is the four-point gate for the presentation copy.

## 1. Isomorphism

The visual structure mirrors the concept's behavior. If you removed all text, the structure alone would still communicate the argument. A converted flowchart arrives as uniform boxes connected by uniform arrows, which displays the steps but argues nothing. Re-shape so the structure carries the meaning: fan-out for a source, convergence for a funnel, a timeline line for a sequence, a cycle for a loop. Use the visual pattern library in the global skill.

## 2. Evidence

A technical diagram carries concrete artifacts, not just labeled boxes. Conversion strips all evidence, so add what the audience needs: real event or method names, a code snippet, a sample data payload, a UI mockup. Use the evidence-artifact colors from /Users/gunderer/.claude/skills/excalidraw-diagram/references/color-palette.md. Skip this only for a purely conceptual diagram where the concept is the abstraction.

## 3. Multi-zoom

A comprehensive diagram works at three zoom levels at once: a summary flow that gives context, labeled section boundaries that group related elements, and detail inside each section that teaches. A flat converted diagram has none of these. Add the summary and the section boundaries during polish.

## 4. Container discipline

Default to free-floating text. Add a container only when the shape carries meaning, arrows must bind to it, or it is a section focal point. Conversion puts a box around every node, so this is the single most common defect to correct. Target under 30 percent of text elements inside containers. For each boxed element ask whether it would read as well as free-floating text, and if so, remove the box.

## Apply, then render

The polish pass is judgment work on the converted elements: re-apply the semantic palette, re-space the auto-layout, re-map the degraded shapes from references/conversion-fidelity.md, then satisfy the four criteria above. Polish is not done until the render-view-fix loop confirms it. The render step in SKILL.md is mandatory and follows this pass.
