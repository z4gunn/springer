---
name: spgr-write-component
description: Implement one UI component that matches the design spec exactly, with every required state, design system tokens exclusively, accessibility annotations as written, Storybook stories, and a typed props contract. Use when the Frontend or Mobile Developer agent must build a component test-first from an approved screen spec.
---

# write-component

## Purpose

Produce one UI component that is visually identical to the approved design spec, accessible per its annotations, and maintainable because it reads every style value from the shared token system rather than hardcoding it. A component that drops a spec state or uses a raw hex, pixel, or font value accumulates as visual debt and fails QA, so the implementation must cover every state and use tokens only. The output is source code, not an envelope artifact.

## Inputs

| Field | Description |
|-------|-------------|
| `screen-spec` | The specific component spec listing every required state and the per-state appearance and behavior. Read existing spec files via spgr-read-file. |
| `design-tokens` | The design system token set for color, typography, and spacing. Every component style value resolves to a token reference from this set. |
| `component-contract` | The props interface and event interface for the component. The typed props contract is generated from this. |
| `accessibility-annotations` | The ARIA roles, focus behavior, keyboard interactions, and screen reader announcements the spec defines for the component. |
| `test-runner` | The project test framework, component test library, and visual regression tool (snapshot or Storybook based) from the tech-stack-decision artifact. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Component file | The component implementation written to disk via spgr-write-file, covering every state in the spec, styled with token references only. |
| Storybook stories | One story per state, documenting default, hover, focus, active, loading, error, empty, disabled, and any spec-defined extra state for design QA. |
| Props contract | TypeScript interfaces or prop-types generated from the component contract, exposing the minimal prop surface and catching incorrect usage at development time. |
| Visual regression test | A snapshot or Storybook-based test covering every state, plus a failing component test written before the implementation. |

## Procedure

1. Read the component spec, the design tokens, the component contract, and the accessibility annotations. Use spgr-read-file for spec and token files and spgr-read-artifact for any upstream design artifact. If the spec omits a state's appearance, the token set lacks a value the spec calls for, or the accessibility annotations are missing, stop and escalate (see Notes). Do not infer the missing detail.
2. Enumerate the full state list from the spec before writing code: default, hover, focus, active, loading, error, empty, disabled, and any additional state the spec names. A state present in the spec but absent from the implementation is a defect.
3. Write the failing component test and the visual regression cases first, asserting each enumerated state, and confirm they fail for the right reason before the implementation exists. The failing test precedes the implementation.
4. Generate the typed props contract from the component contract. Expose the minimal prop surface the contract requires. Do not expose internal implementation details as props.
5. Implement each state. Resolve every style value to a design token reference. Do not write a hardcoded hex value, pixel value, or font size into the component styles. A raw style value is a token violation and fails this skill.
6. Implement the accessibility annotations exactly as written: ARIA roles, focus behavior, keyboard interactions, and screen reader announcements. Do not paraphrase or omit an annotation.
7. Apply YAGNI. Build only the states and props the spec and contract specify. Do not add states, variants, or props the spec does not list.
8. When the component is a form or a form field, hold it to the form rules. Count the fields: three is the baseline for a signup or lead form, four to six costs completions, and seven or more needs a written reason in the spec. Every field has a visible label, never a placeholder standing in for one. Lay fields out in a single column. Set the input type and keyboard that match the data (email, tel, number, url) and leave autofill on with the matching autocomplete attribute. On mobile keep the submit control reachable without scrolling back, sticky at the bottom when the form is longer than the viewport. Write the button copy as the action plus what the user gets, never Submit or Learn more. Build the loading state on the submit control so a double tap cannot send twice. Touch target size, label association, and error association are accessibility annotations and come from spgr-write-accessibility-annotations, so implement them as written rather than re-deriving them here.
9. When the component has an empty state, make it an entry point rather than a notice. Show the exact next action and offer it as one click or one field. Show the action the user can take, not a description of the capability. Where the product allows it, let the user try the feature with sample data before any setup. Empty-state copy comes from the screen spec, and a missing empty-state action is an escalation to the Design agent, not an invention.
10. Write one Storybook story per state so design QA can review every state in isolation.
11. Run the component and visual regression suite via spgr-run-tests. Confirm every state renders as the spec describes and every regression case passes. Then capture the stories or the screen with `.claude/skills/spgr-render-design-comps/scripts/capture-comps.py` when the Playwright CLI is installed, read the captures, and self-critique against the craft floor, the motion standards, and the interface rules in `.claude/references/design-quality.md`. Fix a calibration-cluster hit or a floor miss before the PR opens.
12. Lint and format the component, stories, and contract clean before commit. For TypeScript or JavaScript, conform to `.claude/references/typescript-standards.md` and pass `tsc --noEmit`. Keep the component to one logical change per commit.
13. Write the files via spgr-write-file. Record any consequential implementation choice, such as a token chosen where the spec was ambiguous, via spgr-log-decision.

## Notes

- This skill produces source code. Verification is by spgr-run-tests, the visual regression suite, CI, and the self-critique in step 11, not by an envelope schema. The design bar the Code Reviewer holds the PR to is `.claude/references/design-quality.md`, so clear it here first. For full accessibility conformance against a WCAG target, the component is later audited by spgr-run-accessibility-audit.
- Escalate via spgr-escalate when the spec does not define a required state's appearance or behavior, when a style value the spec calls for has no matching design token, when the accessibility annotations are missing or contradict the component contract, or when the spec and the component contract disagree on props or events. Return the precise list of what is missing rather than guessing.
- When the component touches a vertical concern such as accessibility conformance or an auth-gated state, consult the specialist via spgr-tag-vertical-agent before finalizing.
