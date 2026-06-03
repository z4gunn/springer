---
name: spgr-write-accessibility-annotations
description: Produce accessibility-annotated screen specs that turn WCAG 2.1 AA conformance into an explicit, per-element implementation contract for developer agents, covering ARIA roles, focus order, keyboard behavior, screen reader announcements, contrast ratios, touch target sizes, alt text, and form field bindings. Use when the Design or Accessibility Agent has approved screen specs and a target WCAG level and must annotate them so developer agents implement accessibility exactly rather than approximately, or when a custom interactive component (date picker, slider, drag-and-drop) needs its ARIA pattern annotation before development picks it up.
---

# write-accessibility-annotations

## Purpose

Accessibility implemented without explicit annotations is inconsistent and usually incorrect, and retrofitting it after development is expensive. Annotate approved screen specs at the spec stage so accessibility is a first-class implementation requirement, not a post-launch audit item. The annotated spec is the accessibility contract for developer agents. Developer agents implement exactly what is annotated. "Figure it out" is not an annotation.

This skill is owned by the Accessibility vertical operating as a consultant to the Design and developer horizontal agents. The annotation set advises another agent's screen spec, so route the recommendation through a consultation artifact rather than editing the screen spec in place.

## Inputs

| Field | Description |
|-------|-------------|
| `screen-specs` | Approved screen specs to annotate, read via spgr-read-artifact or spgr-read-file |
| `wcag-target` | Target conformance level, AA minimum |
| `platform-targets` | Web, iOS, or Android, used to apply stricter platform conventions where they exceed WCAG |
| `color-pairs` | Text and background color values per screen, for contrast verification |

## Outputs

| Artifact | Description |
|----------|-------------|
| `accessibility-annotations` | Annotated screen specs written via spgr-write-artifact, one annotation block per screen, with the per-element coverage listed in the Procedure |
| `consultation` | The recommendation routed to the owning Design or developer agent via spgr-tag-vertical-agent, since this skill advises another agent's screen spec rather than editing it |

## Procedure

1. Read the screen specs and the WCAG target via spgr-read-artifact. If a target level is absent, default to AA and record the assumption in the decision log via spgr-log-decision.
2. For every screen, annotate every interactive element and every dynamic state change, not only the elements that seem complicated. Cover each item below.
   - ARIA roles for all landmark regions, interactive elements, and custom widgets.
   - Focus order as a numbered sequence per screen. Specify it explicitly, never inferred. Logical visual order and DOM order often diverge in complex layouts, so state the intended order.
   - Keyboard behavior for every interactive element, naming the keys it responds to (Enter, Space, Arrow keys, Escape, Tab).
   - Screen reader announcements for every dynamic state change (loading complete, error shown, modal opened).
   - Contrast ratio for every text and background pair, verified at 4.5:1 for body text and 3:1 for large text.
   - Touch target size verified at 44x44pt minimum.
   - Alt text requirements for every meaningful image, and `aria-hidden` for decorative images.
   - Form field labels, error associations, and hint text bindings.
3. For each custom interactive component (date picker, slider, drag-and-drop), write the most detailed annotation and cite the applicable ARIA authoring pattern by name. These components carry the highest implementation risk.
4. Apply platform precedence. Where iOS or Android conventions impose stricter requirements than WCAG AA, annotate the stricter platform requirement and note that it supersedes the WCAG baseline for that element.
5. Verify contrast ratios before annotation review using the automated contrast check (see Notes). Flag every failing pair in the annotation so the Design Agent corrects the color, rather than passing a failing pair downstream.
6. Write the annotated spec via spgr-write-artifact with inline spgr-validate-artifact. Route the recommendation to the owning Design or developer agent through a consultation via spgr-tag-vertical-agent rather than editing their screen spec directly.
7. Escalate via spgr-escalate when the input is incomplete or contradictory rather than filling the gap with an assumption. Triggers: a screen spec missing color values needed for contrast verification, a required interaction whose keyboard model is undefined and cannot be derived from an ARIA pattern, a contrast failure the Design Agent declines to correct, or a platform requirement that conflicts with an approved screen spec. State precisely what is missing and which screen and element it blocks.

## Notes

- Output type is an envelope artifact (accessibility-annotations). Its content schema is registered in a later increment, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, and version).
- Mark each annotation block with a confidence signal. Use confirmed for verified contrast and platform-checked elements, proposed for derived keyboard models awaiting developer confirmation, and needs-human-input for any element an escalation is open on.
- Reuse the annotation template library for common patterns (modals, dropdowns, carousels) to keep annotations consistent across screens. Store templates in `assets/` only when they are reused across runs.
- Version revisions with spgr-version-artifact when a screen spec changes after first annotation.
