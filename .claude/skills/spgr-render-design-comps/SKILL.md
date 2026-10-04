---
name: spgr-render-design-comps
description: Render one or two key screens of a design direction as high-fidelity HTML comps from proposed tokens, capture them at phone, tablet, and desktop widths in light and dark, and critique them against the design-quality bar until they pass. Use after a direction is selected and before tokens lock, or per direction at the selection gate.
---

# render-design-comps

## Purpose

Springer's pipeline moves from gray structural mockups to a token table to screen specs to code, and nobody looks at a rendered high-fidelity surface until production code exists. Visual identity is decided there or nowhere, so this skill renders it early. It builds real HTML comps from the proposed tokens, captures them with a headless browser, and critiques the captures against `.claude/references/design-quality.md` in a bounded loop. The comp is a throwaway selection and verification aid in the same spirit as spgr-render-design-mockups, not a maintained deliverable and not application code. What survives is the token set it validated, the critique record, and the captures the human sees at the next gate.

The skill has two modes. In `direction` mode it renders one hero comp per direction at the selection gate so the human compares identity alongside the structural mockups. In `system` mode it renders the key screens of the selected direction from the proposed design-system tokens and iterates the tokens until the comps pass, before the tokens are locked and before screen specs begin.

## Inputs

| Field | Description |
|-------|-------------|
| `mode` | `direction` or `system`. |
| `design_directions_artifact_path` | The design-directions artifact, read with spgr-read-artifact. In `direction` mode every direction is rendered. In `system` mode only the selected direction or the documented hybrid. |
| `design_system_artifact_path` | `system` mode only. The proposed design-system artifact whose tokens the comps render. |
| `story_backlog_path` | The confirmed backlog, read to pick the one or two screens that carry the most identity, usually the entry screen and the screen where the primary job happens. |
| `brand_constraints` | Optional. Palette, typeface, logo, and tone constraints that fix axes the choice test must not touch. |
| `docs_path` | Optional. The comps root, default `docs/design/comps/`. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `docs/design/comps/<slug>/tokens.css` | The direction's proposed tokens rendered as CSS custom properties. The only file in a comp that carries a raw value. |
| `docs/design/comps/<slug>/<screen>.html` | One self-contained page per key screen, styled through `tokens.css` only. |
| `docs/design/comps/<slug>/shots/` | The capture matrix as PNG files plus `capture-report.json`, written by `scripts/capture-comps.py`. |
| `docs/design/comps/<slug>/critique.md` | The critique record per round: first impression, cluster hits, floor misses, detector findings, what changed, verdict. |
| `comp_report` | Returned to the calling agent: the paths written, the rounds taken, the final verdict per direction, the token changes the loop forced, and which tools were available. |

## Procedure

1. Read the inputs with spgr-read-artifact. In `direction` mode stop and raise spgr-escalate if fewer than three directions are present. In `system` mode stop and escalate if no single direction is selected, if the hybrid is not explicitly scoped, or if the design-system artifact lacks the color, typography, and spacing token sets. Do not fill a missing token with a guess.

2. Read `.claude/references/design-quality.md` in full. It is the bar this skill iterates toward and the critique procedure it runs.

3. Pick the screens. From the backlog choose the entry screen and the screen where the core persona does the primary job. Two screens is the ceiling. One is enough in `direction` mode. These are identity studies, not a screen inventory.

4. Run the choice test from the reference on the direction's visual language before writing markup. Write the plan (palette roles, typefaces and their jobs, the layout concept, the alignment rule, the one memorable element), produce the generic version in your head, and revise every part that survives the substitution. Record what changed with spgr-log-decision. In `system` mode the plan is the proposed token table, and a token the test changes is a proposed change to the design-system artifact.

5. Render `tokens.css` from the token table. Every token becomes a custom property under `:root`, with the dark layer under a `[data-theme="dark"]` selector and a `prefers-color-scheme` fallback. Font families the direction sources are declared here and loaded by a `<link>` in the page head or a self-hosted `@font-face`. Nothing else in the comp carries a raw color, size, or family. The construction rules, the page skeleton, and the token naming are in [references/comp-construction.md](references/comp-construction.md). Read it before writing a page.

6. Write each screen as one complete HTML page that references `tokens.css` and renders real copy from the brief, real structure from the direction's information architecture, and the hover, focus, active, disabled, loading, error, and empty states where the screen has them, each reachable without a build step. Draw the browser surfaces the reference names: selection, caret, focus ring, scrollbar, form accent color. Use labeled placeholder boxes only for imagery the brief does not supply, and name what each stands for.

7. Capture. Run the capture script with the comp directory as the target and the `shots/` folder as the output:

   ```bash
   python3 .claude/skills/spgr-render-design-comps/scripts/capture-comps.py docs/design/comps/<slug> --out docs/design/comps/<slug>/shots
   ```

   It renders every page at phone, tablet, and desktop widths in light and dark, runs the detector on the directory when it is installed, and writes `capture-report.json`. The script opens local pages as file URLs with the CLI's file-access variable set, so the comps need no server. When the report says the Playwright CLI is missing, read each page's markup and computed intent instead, state in the critique that no capture was possible, and still run the detector if present. Neither tool is required for the skill to complete.

8. Critique the captures by the procedure in the reference: first impression, cluster check, floor check, detector findings, motion, copy, verdict. Read the screenshots with the Read tool before reading any comp source. Write the round to `critique.md`.

9. Iterate. On a failing verdict, fix the comp and, in `system` mode, the token that caused the miss, recapture, and critique again. Cap the loop at three rounds. After the third failing round, stop and raise spgr-escalate with the open findings rather than shipping a comp that reads as generated. A contrast failure is fixed before any taste iteration, and a brand constraint that cannot meet contrast is escalated to the human with compliant alternatives, per the Design agent's escalation rule.

10. Write every file with spgr-write-file. In `system` mode, carry each token change the loop forced into the design-system artifact as a versioned revision with spgr-version-artifact and record the rationale with spgr-log-decision. Return `comp_report` so the calling agent can reference the captures at the next gate.

## Notes

- Comps are not typed artifacts. They carry no envelope and no schema and are not routed through spgr-write-artifact. The design-directions and design-system artifacts stay the source of truth, and the critique record is appended to their decision logs.
- The token-only rule holds. `tokens.css` is the one place a raw value appears, because it is the rendered form of the token table. A comp page that carries a raw hex, pixel, or family value outside it fails the skill.
- `direction` mode does not replace the structural mockups. The gray mockups let the human compare information architecture, and the hero comps let the human compare identity. Both are linked from `docs/design/index.html`.
- This skill selects nothing. The human selects a direction, and in `system` mode the Design agent locks the tokens after the comps pass.
- The screen set here is deliberately tiny. Per-screen completeness lives in spgr-create-screen-specs. Usability testing lives in spgr-create-prototype.
- The capture script is deterministic and runs with no model. Dispatch it at the deterministic tier. The critique is judgment and runs at the Design agent's tier.
- This skill has no Phase 1 vault spec. It was authored to the Springer build standards as a net-new capability.
