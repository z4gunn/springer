---
name: spgr-check-color-contrast
description: Produce a color-contrast audit report that measures every text-on-background and UI-component-boundary color pair against WCAG contrast thresholds, recording the calculated ratio and level achieved per pair, listing failures with the components and states affected, and recommending corrected color values that reach AA while preserving brand intent, with a PASS or GATE verdict that blocks a token lock or release on any AA failure. Use when the Accessibility Agent must confirm a design token set or component palette meets contrast requirements before tokens are locked, or when the Frontend Developer or QA agent needs contrast evidence to justify a color token change, or when a design-token CI sweep needs the current contrast posture.
---

# check-color-contrast

## Purpose

Insufficient color contrast is one of the most common WCAG failures and one of the cheapest to fix, because the remedy is a color token change rather than an interaction redesign. Catch failures before the design system tokens are locked to avoid retroactive design work. Operate as the Accessibility vertical in auditor and gate mode. Measure each color pair against the WCAG threshold for its text size and element role, classify the result, and return a verdict that blocks a token lock or release on any unresolved AA failure on a non-exempt element.

This skill produces the report. It does not edit the design token file or the component palette directly. Where a fix belongs to the Design or Frontend agent, route the recommended color values to that agent through a consultation with spgr-tag-vertical-agent rather than editing their artifact.

## Inputs

| Field | Description |
|-------|-------------|
| `color-palette` | Design tokens as hex values, read with spgr-read-file or spgr-read-artifact |
| `component-inventory` | Component list showing each text-on-background combination |
| `element-states` | Interactive element states to cover: default, hover, focus, disabled, error |
| `target-level` | Target WCAG conformance level, AA or AAA, AA when unspecified |

## Outputs

| Artifact | Description |
|----------|-------------|
| `color-contrast-audit` | Audit report written via spgr-write-artifact, carrying per-pair findings, failures by affected component and state, recommended corrected colors, exemption notes, and a PASS or GATE verdict |

The report records, per color pair: foreground hex, background hex, calculated contrast ratio, the threshold applied, and the level achieved (AA, AAA, or Fail). Each failure names the components and states it affects and gives a recommended corrected hex that reaches AA while staying close to brand intent. Large-text pairs (18pt or larger regular, 14pt or larger bold) are flagged so the 3:1 threshold is visibly applied rather than silently.

## Procedure

1. Read the color palette, component inventory, and element states with spgr-read-file or spgr-read-artifact. If any of the three is missing, or a component references a token that is not defined in the palette, stop and raise spgr-escalate with the precise list of what is missing. Do not assume a default color.

2. Enumerate every text-on-background pair and every UI-component-boundary pair across all supplied states. UI-component boundaries include input borders, button borders, focus indicators, and graphical objects that convey information.

3. Compute the contrast ratio for each pair. Apply the threshold for the pair's role and text size:
   - Normal text: 4.5:1 for AA, 7:1 for AAA.
   - Large text (18pt or larger regular, 14pt or larger bold): 3:1 for AA, 4.5:1 for AAA.
   - UI component boundaries and graphical objects (WCAG 2.1 criterion 1.4.11, Non-text Contrast): 3:1. This covers button borders, form input boundaries, and focus indicators.

4. Cross-validate with at least two independent contrast tools before recording a Fail, so a borderline ratio is not mis-flagged. Record the level achieved per pair.

5. Treat disabled-state elements as exempt from contrast requirements under WCAG. Do not fail them. Record each exemption explicitly with a one-line note so a reviewer reads it as intentional rather than an oversight.

6. For each failure on a non-exempt element, compute a corrected color value that reaches the AA threshold for that pair. Adjust lightness toward the nearest brand-consistent value rather than substituting an unrelated color. Record the original hex, the corrected hex, and the ratio each produces.

7. Set the verdict. GATE when any non-exempt pair fails its AA threshold. PASS when every non-exempt pair meets at least AA, or AAA when AAA was the target level. Record the verdict and the blocking failure count in the report header.

8. Write the report via spgr-write-artifact with inline spgr-validate-artifact. Log the verdict and the threshold rationale with spgr-log-decision.

9. On a GATE verdict, route each recommended corrected color to the Design or Frontend agent through spgr-tag-vertical-agent as a consultation. Do not edit the design token file or the component palette directly. If the failure blocks a token lock or a release, surface the gate to the human with spgr-notify-human.

## Notes

- Output type is an audit report, an envelope artifact. The color-contrast-audit content schema is not registered yet, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, version), with its content schema registered in a later increment.
- Blocking threshold is AA. Any non-exempt pair below its AA threshold sets a GATE verdict that blocks the design token lock or the release. AAA shortfalls are advisory unless AAA is the stated target level.
- In the design-token CI sweep, run this check across all defined text-on-background combinations whenever tokens change and fail the pipeline on any combination that regresses below AA.
- A recommendation to a horizontal agent flows through spgr-tag-vertical-agent as a consultation, never as a direct edit of the design token or palette artifact.
