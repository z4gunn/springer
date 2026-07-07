---
name: spgr-check-rtl-support
description: Produce an RTL-support audit report that verifies layout mirroring, icon direction, text alignment, and interaction patterns for right-to-left languages, with a PASS or GATE verdict that blocks release on any core function broken under RTL. Use when the i18n Agent must confirm a release or component library renders correctly under an RTL locale.
---

# check-rtl-support

## Purpose

RTL support is not a single mirror operation. A layout can be technically flipped and still be semantically wrong. Correct RTL means mirroring directional icons (back arrow, forward chevron, progress) while leaving conceptual icons unmirrored (checkmark, warning, star, logo), reversing reading order in compound components, keeping numbers, prices, and dates in LTR runs, and matching cursor and gesture direction to RTL convention. Products that bolt RTL on late ship layouts that flip but read wrong. Run this audit to make RTL correctness a tested, reviewable property rather than an assumption.

This skill operates the i18n Agent in auditor and gate mode. The audit is behavioral and code-level. It renders the app under an RTL locale and inspects the rendered result, and it reads the style logic to find physical properties that defeat automatic mirroring. It sets a blocking threshold. Any core function that a user can complete in LTR but cannot complete or read under RTL is a release blocker.

## Inputs

| Field | Description |
|-------|-------------|
| `application-ui` | The screens, components, and icons under audit. Located with spgr-search-codebase and read with spgr-read-file, or rendered under an RTL locale for inspection. |
| `style-logic` | The CSS or platform style source, read to distinguish physical properties (`margin-left`, `text-align: left`, `padding-right`) from logical properties (`margin-inline-start`, `text-align: start`, `padding-inline-end`). Read with spgr-read-file. |
| `rtl-locale-config` | The RTL locale test configuration used to render the app with `dir="rtl"` on web, or the platform layout-direction override on iOS and Android. Read with spgr-read-file. |
| `i18n-spec` | Optional. The confirmed i18n spec naming target RTL locales and supported scripts. Read with spgr-read-artifact. |
| `release-scope` | Optional. The screens or components in the pending release, used to scope the gate verdict to what is shipping. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `rtl-support-audit` | Audit report envelope artifact written via spgr-write-artifact. Carries per-category findings (layout mirroring, icon direction, text alignment, interaction, logical-property gap) with the affected components and states, gaps by severity, the blocking findings, and a PASS or GATE verdict. |

## Procedure

1. Read the inputs. Confirm the RTL locale configuration and the target RTL locales before inspecting anything, because the audit renders against them. If the RTL locale config, the application UI, or the style source is missing, stop and raise spgr-escalate with the precise list of what is absent. Do not infer the RTL mechanism from habit.

2. Render the app under RTL. On web, apply `dir="rtl"` to the root element. On iOS and Android, apply the platform's RTL layout-direction override. Walk every in-scope screen and component in this rendered state, comparing it against the LTR rendering.

3. Audit layout mirroring. Flag elements that do not mirror correctly under RTL: containers, navigation, and compound components whose reading order does not reverse, and elements pinned to a physical side that stay on the wrong side. Record the component and the state where the mismatch appears.

4. Audit icon direction. Classify each icon as directional or conceptual. A directional icon (back arrow, forward chevron, next or previous control, progress indicator) must mirror under RTL. A conceptual icon (checkmark, warning, star, logo) must not mirror. Flag any directional icon that stays unmirrored, and any conceptual icon that is mirrored.

5. Audit text alignment. Flag hard-coded physical alignment that should be logical: `text-align: left` that should be `text-align: start`, and any alignment that does not follow the locale direction. Confirm numbers, prices, and dates stay in LTR runs even inside RTL text, and flag where an explicit `dir="ltr"` on a number or price element is needed to prevent a bidirectional edge case.

6. Audit interaction. Flag gestures, swipe directions, and cursor behavior that do not follow RTL convention: a swipe-to-go-back that does not reverse, a carousel that advances the wrong way, or text-input cursor behavior that does not match RTL.

7. Audit the logical-property gap. Read the style source and list physical properties that should be logical: `margin-left` and `margin-right` to `margin-inline-start` and `margin-inline-end`, `padding-left` and `padding-right` to the inline equivalents, and physical `left` and `right` offsets. Converting physical properties to logical properties is the highest-value fix because it lets the platform mirror automatically, so call out the conversion explicitly per finding.

8. Add RTL screenshot tests to CI. Recommend rendering each in-scope screen with `dir="rtl"` and comparing against an expected RTL screenshot, so a new RTL regression is caught automatically. Note the screens that lack RTL screenshot coverage as findings.

9. Classify findings by severity. A core function that is broken or unreadable under RTL (a control that lands off-screen, a reversed destructive gesture, an unreadable compound component) is highest severity and blocking. A directional icon that does not mirror is blocking when it changes the meaning of an action. A physical-property usage behind otherwise correct mirroring is reported but does not block on its own.

10. Set the verdict. The blocking threshold is any core function that works under LTR but is broken or unusable under RTL on an in-scope screen. If `release-scope` is supplied, score the verdict against only the screens in scope. The verdict is GATE if any blocking finding exists, otherwise PASS.

11. Write and validate the report. Write the `rtl-support-audit` artifact via spgr-write-artifact with inline spgr-validate-artifact. Record the verdict rationale and each blocking finding with spgr-log-decision.

12. Route remediation, do not patch other artifacts. For each finding owned by another agent (a frontend component, a style token, a mobile layout, an icon set), route the recommendation through a consultation with spgr-tag-vertical-agent rather than editing that agent's code or artifact directly. On a GATE verdict for a pending release, surface the decision to the human gate with spgr-notify-human.

## Notes

- Output type is an audit report (envelope artifact). Its content schema is registered in a later increment, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, version).
- Blocking threshold: any core function usable under LTR but broken or unusable under RTL on an in-scope screen yields a GATE verdict. A physical-property usage behind otherwise correct mirroring is reported but does not gate on its own.
- This audit renders, inspects, and reports only. It does not convert physical properties to logical, mirror icons, or change gesture handlers. Recommendations to other agents flow through spgr-tag-vertical-agent.
- Logical properties on web, plus `dir="rtl"` on the root, mirror most layout automatically. On iOS and Android the platform mirrors automatically when the app respects the layout direction. Treat a physical-property dependency as the root cause behind most layout findings.
