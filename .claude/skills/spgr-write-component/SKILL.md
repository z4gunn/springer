---
name: spgr-write-component
description: Implement one UI component that matches the design spec exactly, with every required state (default, hover, focus, active, loading, error, empty, disabled, plus any spec-defined states), using design system tokens exclusively and the accessibility annotations as written, with Storybook stories and a typed props contract. Use when the Frontend Developer or Mobile Developer agent has an approved screen spec, design tokens, and a component contract and must build the component test-first before it is integrated into a screen.
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
8. Write one Storybook story per state so design QA can review every state in isolation.
9. Run the component and visual regression suite via spgr-run-tests. Confirm every state renders as the spec describes and every regression case passes.
10. Lint and format the component, stories, and contract clean before commit. Keep the component to one logical change per commit.
11. Write the files via spgr-write-file. Record any consequential implementation choice, such as a token chosen where the spec was ambiguous, via spgr-log-decision.

## Notes

- This skill produces source code. Verification is by spgr-run-tests, the visual regression suite, and CI, not by an envelope schema. For full accessibility conformance against a WCAG target, the component is later audited by spgr-run-accessibility-audit.
- Escalate via spgr-escalate when the spec does not define a required state's appearance or behavior, when a style value the spec calls for has no matching design token, when the accessibility annotations are missing or contradict the component contract, or when the spec and the component contract disagree on props or events. Return the precise list of what is missing rather than guessing.
- When the component touches a vertical concern such as accessibility conformance or an auth-gated state, consult the specialist via spgr-tag-vertical-agent before finalizing.
