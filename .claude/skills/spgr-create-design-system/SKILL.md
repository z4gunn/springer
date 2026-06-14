---
name: spgr-create-design-system
description: Produce a design-system artifact from the selected design direction, defining named color, typography, and spacing tokens (with a dark mode token layer), a component library where every component documents all eight states, a pattern library, and accessibility guidelines, so design and development share one token-based visual contract. Use when the Design Agent has an approved design direction and must settle the shared visual language before per-screen specs or component implementation begin, or when a developer agent needs the token set and component states to implement against.
---

# create-design-system

## Purpose

Define the complete design system that becomes the shared contract between the Design Agent and every developer agent. This artifact prevents each screen from being designed independently, which produces visual inconsistency and duplicated implementation. The contract is token-based, meaning every value carries a name and no raw hex, px, or font-size value appears in any component spec or downstream per-screen spec. Developer agents implement these tokens as CSS custom properties, design tokens, or platform equivalents (iOS SwiftUI tokens, Android Material tokens), so the names defined here are the integration surface.

## Inputs

| Field | Description |
|-------|-------------|
| `design-direction` | The approved design direction artifact selected by the human. The single source for brand palette, type personality, and visual tone. Read it with spgr-read-artifact. |
| `ui-ux-pro-max catalog` | Optional. The third-party catalog of palettes and font pairings, read by absolute path `~/.claude/skills/ui-ux-pro-max/`. When the approved direction references a catalog palette or pairing, this is the source whose raw values are translated into named tokens here. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `design-system` | One envelope artifact written with spgr-write-artifact. Contains color tokens (brand, semantic, surface, text, border) with a parallel dark mode layer, a typography scale (family, weights, sizes, line heights as named levels heading-1 through body-sm), a spacing scale (space-1 through space-16 or equivalent), a component library covering every state per component, a pattern library, accessibility guidelines, and the process for adding new components. |

## Procedure

1. Read the approved design direction with spgr-read-artifact. If no direction is approved, or more than one is marked selected, or the direction lacks the brand palette and type personality this system depends on, stop and raise spgr-escalate with the precise list of what is missing. Do not fill gaps with assumptions.
2. Define color tokens as names, not values. Cover brand, semantic (success, warning, error, info), surface, text, and border. Every token is a named reference, no raw hex appears in any component spec. When the approved direction references a ui-ux-pro-max palette, translate its raw values into this named token set rather than carrying the hex through.
3. Define a dark mode token layer in the same pass. Each light token has a dark counterpart so the two layers stay one-to-one. Do not defer dark mode, retrofitting it later is expensive.
4. Define the typography scale as named levels (heading-1 through body-sm), each fixing font family, weight, size, and line height. Define the spacing scale as named values (space-1 through space-16 or equivalent). When the approved direction references a ui-ux-pro-max font pairing, translate it into the named typography levels here. The token names stay the integration surface and no raw font name appears in any component spec.
5. Build the component library. Every component documents all eight states: default, hover, focus, active, disabled, loading, error, and empty. A component that omits a state is incomplete, because unspecified states get implemented inconsistently and often incorrectly.
6. Build the pattern library covering form patterns, list patterns, modal patterns, and navigation patterns.
7. Write the accessibility guidelines: minimum contrast ratios, focus indicator requirements, and touch target sizes. Tag spgr-tag-vertical-agent for the accessibility vertical so the contrast and focus rules are reviewed against the token set before tokens are treated as locked.
8. Document the process for adding new components, since the design system grows over time rather than being a one-time artifact.
9. Record each token-set and component decision in the artifact decision log via spgr-log-decision, and mark every section with its confidence signal (confirmed, proposed, needs-human-input).
10. Validate the artifact inline with spgr-validate-artifact, then write it with spgr-write-artifact. Version it with spgr-version-artifact when revising an existing design system.

## Notes

- Output type is an envelope artifact (design-system). The design-system content type is not in the schema registry yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered.
- No raw style values anywhere. Color, typography, and spacing in component and pattern specs reference tokens by name only. This is the rule that makes the artifact a usable contract for developer agents.
- Evaluate Storybook or an equivalent living-documentation tool so the design system stays in sync with the implementation rather than drifting. Record the choice in the decision log.
- Do not duplicate per-screen layout here. This artifact defines the shared language. Screen-level composition belongs to the per-screen design specs that consume these tokens.
- The ui-ux-pro-max catalog is an optional external skill. Its palettes and pairings are source material translated into named tokens, not a values shortcut. This skill runs fully without it.
