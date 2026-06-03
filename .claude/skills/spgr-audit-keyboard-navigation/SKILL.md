---
name: spgr-audit-keyboard-navigation
description: Produce a keyboard-navigation audit report that verifies every interactive element and user flow is reachable, operable, and focus-managed by keyboard alone, with a per-section Tab order trace, reachability and operability findings, focus-trap and focus-restoration checks for overlays, a custom-shortcut inventory, and a PASS or GATE verdict that blocks release on any core function that a mouse can reach but a keyboard cannot. Use when the Accessibility Agent must confirm a release or component library is fully keyboard-operable before it ships, or when the QA or Frontend Developer agent needs keyboard operability checked against the ARIA spec and the interactive-flow list before review.
---

# audit-keyboard-navigation

## Purpose

Keyboard operability is the prerequisite for users with motor disabilities, screen reader users who navigate by keyboard out of necessity, and power users who prefer it. A product that requires a pointing device for any core function excludes this population entirely, so this is a barrier, not a quality preference. Automated tools can simulate Tab order but cannot judge whether focus management is correct, so this skill pairs a scripted Tab order trace with a manual keyboard-only pass and consolidates both into one audit report. Any core function that a mouse can reach but a keyboard cannot is a hard release gate.

## Inputs

| Field | Description |
|-------|-------------|
| `interactive_flows` | The complete list of interactive UI flows from the product spec, the set this audit must cover end to end |
| `running_ui` | The rendered application or component library, reachable on staging, a device, or an emulator |
| `aria_spec` | The ARIA spec artifact, which fixes the expected keyboard interaction pattern for each composite widget role |
| `audit_scope` | The pages, screens, or components to audit, scoped to the release when a full sweep is not feasible |

## Outputs

| Artifact | Description |
|----------|-------------|
| `keyboard-navigation-audit` | Report with a per-section Tab order trace, reachability and operability findings per interactive element, focus-management findings for overlays, a custom-shortcut inventory, severity-ranked violations with remediation, and a PASS or GATE verdict |
| Tab order test files | Source-code tests that drive Tab and Shift-Tab and assert the focus sequence per layout section, run in the E2E suite and in CI |

## Procedure

1. Read the `aria_spec` and `interactive_flows` through spgr-read-artifact, and the in-scope page or component source through spgr-read-file. Confirm the UI named in `running_ui` is reachable before auditing. If the interactive-flow list or the ARIA spec is missing, or the UI is not running, stop and raise spgr-escalate with a precise list rather than auditing a partial flow set or a stale build.
2. Trace the Tab order for each major layout section. Press Tab from the document or screen start and record every element that receives focus in sequence, then press Shift-Tab and confirm the reverse order is the mirror. A Tab order that does not follow the visual and logical reading order is a finding. An element that is visually hidden but still in the DOM and still in the Tab order is a finding, since it must carry `tabindex="-1"` or be removed with `display: none`.
3. Write the Tab order test files as source code through spgr-write-file, following the test-first rule, so the failing focus-sequence assertion exists before any remediation. Drive the Tab key with Playwright or the equivalent, assert focus lands on the expected element sequence, and integrate the tests into the E2E suite so the assertion runs on every nightly build, not only during a dedicated audit.
4. Run the manual keyboard-only pass. Use a physical keyboard and do not touch the mouse or trackpad for the duration of the pass, since shortcut and focus behavior must be tested as a keyboard user experiences it. For every interactive element, record reachability, whether Tab brings focus to it, and operability, whether Enter or Space activates buttons and links and arrow keys operate composite widgets once focused.
5. Check focus management for every dialog, drawer, tooltip, and overlay. Confirm the modal traps focus, Tab cycles within it and Shift-Tab does not escape it, and confirm focus returns to the triggering element when the modal closes. A modal that leaks focus to the page behind it, or that drops focus to the document start on close, is a finding.
6. Check each custom composite widget, tabs, trees, menus, listboxes, against the keyboard interaction pattern its role requires in the `aria_spec` and the WAI-ARIA Authoring Practices Guide. Record the keys the widget accepts against the keys the pattern requires, and file any divergence as a finding.
7. Build the custom-shortcut inventory. List every custom keyboard shortcut the application defines, the action it triggers, and how the shortcut is disclosed to the user. An undisclosed shortcut, or one that collides with an assistive-technology or browser shortcut, is a finding.
8. Normalize each violation into a finding with the affected component or flow, the failure class (unreachable, inoperable, broken focus trap, lost focus restoration, wrong widget keys, undisclosed shortcut), steps to reproduce by keyboard, a severity, and remediation. Write remediation as a specific action that names the code location and the exact change, for example "the close control at line 47 of Dialog.tsx is a div with an onClick, replace it with a button so Enter and Space activate it", not "the control is not operable". Reject and rewrite any remediation that does not name what to change and to what.
9. Set severity. A core function reachable by mouse but not by keyboard, an inoperable interactive element, or a broken focus trap on a modal is the highest severity and blocking. A wrong-key composite widget or a lost focus restoration is high. An undisclosed shortcut or a non-blocking Tab order ordering issue is medium. Track non-blocking findings as bugs through a spgr-write-bug-report handoff rather than as hard gates.
10. Compute the release gate. The gate is GATE when any blocking finding is open, a core function that a mouse can reach and a keyboard cannot, regardless of automated or manual source. The gate is PASS only when no blocking finding remains. Record the verdict as the first scannable line of the summary, with violation counts by severity and the blocking count.
11. Produce the keyboard-navigation-audit report through spgr-write-artifact, which stamps the shared envelope, records per-section confidence, initializes the decision log, and runs spgr-validate-artifact inline before write. Stamp the report with spgr-version-artifact so each release retains its own audit. Log each consequential judgment, a severity call or a deferral, with spgr-log-decision.
12. When the gate is GATE, route the report to the human through spgr-notify-human, because a keyboard barrier ships a documented exclusion. For an ambiguous widget pattern or a contested severity, advise the owning Frontend or Mobile Developer agent through a spgr-tag-vertical-agent consultation rather than editing their component or its test directly. If sources conflict, for example the Tab order test asserts a sequence the manual pass found broken, stop and raise spgr-escalate rather than issuing a PASS on conflicting evidence.

## Notes

- This output is an audit report (envelope artifact). Its content schema is not yet registered, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, version). The registered content schema is added in a later increment.
- The Tab order test files are source code, verified by spgr-run-tests and CI rather than by an envelope schema. They must lint and format clean before commit, with one logical change per commit.
- A GATE verdict is a correct output, not a failure of this skill. The failure is a PASS issued without the manual keyboard-only pass, since a scripted Tab trace alone does not verify focus trapping, focus restoration, or per-widget operability.
- Recommendations to a horizontal agent flow through a spgr-tag-vertical-agent consultation. Do not edit another agent's component or its tests from this audit.
- The report is release-scoped and immutable once stamped. Never edit a prior release's report to reflect a later fix.
