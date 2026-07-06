---
name: spgr-write-aria-spec
description: Produce an aria-spec artifact that assigns each interactive component its ARIA role, properties, state transitions, live-region configuration, and focus-management rules, plus a generated Storybook a11y-addon config. Use when the Accessibility Agent must define the screen-reader contract before a component is built.
---

# write-aria-spec

## Purpose

Define the screen-reader contract for interactive and dynamic components before they are built. A control that reads as a button to a sighted user can be invisible or misidentified to a screen-reader user without the correct role, state, and property assignments. Produce one aria-spec artifact that developers implement against, so the accessibility semantics are part of the design rather than a later patch.

This is an Accessibility vertical skill. The aria-spec is a recommendation to the frontend or mobile horizontal agent. Deliver it as a consultation through spgr-tag-vertical-agent rather than editing the component code or another agent's artifact. The vertical operates here as consultant (answering a tagged request for a component contract) and as gate input (the spec is the source that spgr-check-wcag-compliance and the accessibility audit verify against).

## Inputs

| Field | Description |
|-------|-------------|
| `design-spec` | Design spec or component description, read with spgr-read-file or spgr-read-artifact. |
| `interaction-model` | How each component changes state and what it communicates to the user. |
| `component-library` | Existing component library, to determine whether ARIA is already handled by a library primitive. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `aria-spec` | Envelope artifact written with spgr-write-artifact, one entry per component covering role, required and optional properties, state transitions, live-region config, and focus management. |
| `storybook-a11y-config` | Storybook a11y-addon config source generated from the spec, written with spgr-write-file and verified in CI so story-level checks are pre-configured. |
| `consultation` | spgr-tag-vertical-agent record routing the aria-spec to the consuming frontend or mobile agent. |

## Procedure

1. Read the design spec, interaction model, and component library with spgr-read-file or spgr-read-artifact. List every interactive or dynamic component in scope.
2. For each component, check the native-element rule first. If a native HTML element (for example `<button type="button">`, `<dialog>`, `<select>`) or an existing library primitive already carries the correct semantics, specify that element and add no custom ARIA. Reserve `role` plus ARIA, keyboard handling, and focus management for the case where no native element fits.
3. Assign one role per component from the WAI-ARIA roles taxonomy (button, dialog, listbox, combobox, and so on). Record the rationale for any non-native role.
4. List required and optional ARIA properties. For naming, prefer a visible label referenced by `aria-labelledby`. Specify `aria-label` only to disambiguate, and note that `aria-label` overrides the visible text, so it must not be used to hide the visual label.
5. Define state attributes and their transitions (`aria-selected`, `aria-checked`, `aria-pressed`, `aria-expanded`), naming the exact interaction that flips each state.
6. For dynamic content, configure the live region. Use `aria-live="polite"` by default so announcements wait for the user to finish, and reserve `aria-live="assertive"` for critical alerts only. Record `aria-atomic` and `aria-relevant` where the spec needs them.
7. Define focus management: where focus lands when the component opens, closes, or changes state, and how focus returns to the trigger on dismiss.
8. Generate the Storybook a11y-addon config from the finished spec and write it with spgr-write-file. Confirm it parses and runs in CI.
9. Write the aria-spec with spgr-write-artifact and run spgr-validate-artifact inline. Record consequential choices (a non-native role, an assertive live region) with spgr-log-decision. Route the finished spec to the consuming agent with spgr-tag-vertical-agent.
10. If the design spec or interaction model is missing, contradictory, or leaves a component's state model undefined, stop and raise spgr-escalate with the precise list of what is missing rather than inventing the semantics. Do not guess a role or a state transition.

## Notes

- Output type: aria-spec is an envelope artifact and storybook-a11y-config is source output. aria-spec has no registered content schema yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) for now, and its content schema is registered in a later increment.
- Native first. Every custom `role` plus ARIA assignment carries a keyboard-handling and focus-management obligation. Record that obligation in the same component entry so the developer cannot ship the role without it.
- Mark each component entry with its confidence signal (confirmed, proposed, needs-human-input) in the artifact confidence map.
- Version any revision with spgr-version-artifact, and route changes back to the tagged consuming agent through the consultation rather than editing component code directly.
