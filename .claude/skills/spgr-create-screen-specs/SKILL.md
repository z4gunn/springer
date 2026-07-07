---
name: spgr-create-screen-specs
description: Produce a developer-ready screen-specs artifact covering every screen and screen-level state (default, loading, error, empty, partial data) with token-based layout, component references, and interaction notes. Use when the Design Agent has approved wireframes and a locked design system and must produce the contract developers implement against.
---

# create-screen-specs

## Purpose

Produce the high-fidelity screen specification that developer agents implement against with no further design judgment. This is the design-to-development handoff contract. A screen state that is not specified gets built inconsistently or not at all, so the artifact is complete only when every screen carries all five screen-level states and the per-screen completeness checklist passes. Specs reference design system tokens and components by name and contain no raw style values, which keeps the spec a single source of truth and prevents drift from the locked token set. Once approved, the artifact is a contract. A developer agent that cannot implement a screen as specified raises a spec change request rather than improvising.

## Inputs

| Field | Description |
|-------|-------------|
| `wireframes` | Approved wireframes for every screen in scope. Read via spgr-read-artifact. |
| `design-system` | Locked design system: token set and component library. The only source of style values and named components. Read via spgr-read-artifact. |
| `interaction-spec` | Optional. Existing interaction or navigation spec, if one was produced. Read via spgr-read-artifact when present. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `screen-specs` | Envelope artifact. One section per screen, each with token-based layout, named component states, all five screen-level states, asset specs, interaction notes, edge-case states, and a completeness checklist. Written via spgr-write-artifact. |

## Procedure

1. Read the inputs with spgr-read-artifact. If wireframes or the design system are missing, not approved, or not locked, stop and raise spgr-escalate with the precise list of what is missing. Do not infer screens or invent tokens.

2. Build the screen inventory from the wireframes. Every screen in the wireframes gets a spec section. Do not drop a screen and do not add a screen that has no wireframe.

3. For each screen, specify the layout using design system spacing, sizing, and color tokens by name. Do not write raw pixel, hex, or font values. If a layout needs a value the token set does not provide, stop and raise spgr-escalate, or tag the design-system owner with spgr-tag-vertical-agent, rather than hardcoding the value.

4. For each screen, reference the design system components by name and specify which component state each instance uses (for example default, hover, focus, disabled, active). Components come from the library. Do not define a new component inline.

5. For each screen, specify all five screen-level states. None may be omitted or deferred to another screen:
   - default: the populated state.
   - loading: the skeleton layout or the loading indicator pattern, named explicitly.
   - error: the exact error message text, whether the user can retry, and the recovery path.
   - empty: designed as a deliberate first-run state, since it is often the first state a new user sees. Not an afterthought.
   - partial data: how the screen renders when some but not all data is present.

6. For each screen, specify every asset (icon, image) with its dimensions and its accessibility label.

7. For each screen, specify interaction notes: what happens on tap or click, hover behavior, and focus behavior. Specify edge-case states: how the screen renders when content runs longer than expected and when expected data is missing.

8. For each screen, run the completeness checklist and record the result in the spec section: loading state specified, error state specified, empty state specified, partial-data state specified, mobile breakpoint specified, tablet breakpoint specified. A screen with any unchecked item is incomplete. Either complete it or raise spgr-escalate naming the gap. Do not mark the artifact confirmed while any screen fails the checklist.

9. Set the confidence map per screen section. Mark a screen confirmed only when its checklist passes. Mark a screen needs-human-input when a wireframe is ambiguous or a required token is absent.

10. Write the artifact with spgr-write-artifact and run spgr-validate-artifact inline. Record each design choice that a developer could question with spgr-log-decision. Version the artifact with spgr-version-artifact. When the artifact is ready for the developer handoff, notify the requester with spgr-notify-human.

## Notes

- Output type is an envelope artifact (screen-specs). The screen-specs type has no registered content schema yet, so spgr-validate-artifact applies envelope-only validation, checking the header, confidence map, decision log, and version. State this in the artifact and treat it as expected until a content schema is registered.
- All style values are token references by name. The artifact must contain no raw pixel, hex, rgb, or font-size literals. A raw value is a validation failure to fix before the artifact is confirmed.
- The artifact is the developer handoff contract. After approval, an implementation deviation requires a spec change request routed through spgr-escalate, not a silent code change.
- "Handle it like the other screens" is not a valid spec. Every state on every screen is specified in full.
- A component prop table per screen, derived from the named component states, is optional and reduces developer lookup time. Generate it from the component references already in the spec rather than restating them.
