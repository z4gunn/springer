---
name: spgr-write-interaction-spec
description: Produce an interaction-spec artifact that documents the trigger, behavior, duration, easing, state transitions, reduced-motion equivalent, and accessibility notes for every interactive element on the approved screens, so developer agents implement motion and behavior consistently. Use when the Design Agent has approved high-fidelity screen specs and must pin down interaction behavior before frontend or mobile implementation begins, or when a developer agent needs the exact timing, easing, and keyboard behavior for an animation it is about to build.
---

# write-interaction-spec

## Purpose

Specify every intentional interaction on the approved screens so that different developer agents implement the same motion and behavior the same way. Unspecified interactions get built inconsistently and motion without purpose confuses users. Make each interaction explicit, give every animation a stated purpose, and pair every animation with an accessible equivalent. Express timing as token references where a motion-principles document exists, not as ad hoc values, so durations and easings stay consistent across the product.

## Inputs

| Field | Description |
|-------|-------------|
| `screen-specs` | Approved high-fidelity screen specifications, the set of screens whose interactive elements need behavior documented |
| `motion-principles` | Design-system-level motion philosophy and named duration and easing tokens, read via spgr-read-artifact if it exists |
| `interaction-pattern-library` | Reference set of common interaction patterns with pre-specified durations and easings, reused so each spec does not re-derive standard motion |

## Outputs

| Artifact | Description |
|----------|-------------|
| `interaction-spec` | Per-interaction record of trigger, behavior, duration in milliseconds, easing curve, from-state to-state transitions with intermediate states, reduced-motion equivalent, and accessibility notes, written via spgr-write-artifact |

## Procedure

1. Read the screen specs with spgr-read-artifact. Read the motion-principles document and the interaction-pattern-library if they exist. If no motion-principles document exists at the design system level, establish the overall animation philosophy and the named duration and easing tokens first, because individual interactions reference those tokens rather than inventing values.
2. Enumerate every interactive element and every triggered behavior on each screen. Cover taps, swipes, hovers, focus changes, scroll thresholds, data-load completion, and any state-driven motion.
3. For each interaction, record the trigger, the behavior in both visual and functional terms, the duration in milliseconds, the easing curve (ease-in, ease-out, ease-in-out, spring, or a custom Bezier), and the state transition from-state to to-state including every intermediate state.
4. State the purpose of every animation: direct attention, communicate a state change, or give feedback. Flag any decorative animation with no functional purpose as a candidate for removal rather than specifying it as required.
5. Write the reduced-motion equivalent for every animation, the behavior when `prefers-reduced-motion` is active. A jump cut, an instant state change with no animation, is the minimum acceptable fallback.
6. Specify interactions that need fixed timing, for example a toast that auto-dismisses after a set interval, with the explicit value and a rationale for that value.
7. For each mobile gesture interaction, specify the trigger threshold, the cancellation behavior, and the conflict resolution against platform gestures.
8. Complete the keyboard and focus path for every interaction, the keyboard equivalent and the screen reader announcement when a state changes. Do not document only the mouse or touch path.
9. Write the artifact with spgr-write-artifact and validate it inline with spgr-validate-artifact. Version it with spgr-version-artifact and record the motion decisions with spgr-log-decision.
10. If any animation has no reduced-motion equivalent, any animation has no stated purpose, any keyboard or focus path is missing, or the screen specs are not approved, stop and raise spgr-escalate with the precise list of what is missing rather than filling the gaps with assumptions. Tag the Accessibility vertical with spgr-tag-vertical-agent for reduced-motion and screen-reader review before the artifact is marked confirmed.

## Notes

- Output type is an envelope artifact. The `interaction-spec` content type has no registered content schema yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered.
- Use token references for durations and easings, not hardcoded style values, consistent with the design-system token model.
- Mark each interaction with a confidence signal of confirmed, proposed, or needs-human-input. An interaction whose timing or behavior the screen specs do not settle is proposed or needs-human-input, not confirmed.
