---
name: spgr-run-accessibility-audit
description: Scan a built UI for WCAG violations with axe-core, supplement with manual keyboard and screen reader testing, and produce a prioritized accessibility-audit report plus reusable axe-core test scaffolds, with Level A violations set as a hard release gate. Use when the QA, Accessibility, or Frontend Developer agent has a running UI and a target WCAG level and must confirm conformance and document remediation before a release proceeds, or when a new design-system component needs an accompanying accessibility test before it is published.
---

# run-accessibility-audit

## Purpose

WCAG conformance is a legal obligation in many jurisdictions and a basic requirement for users on assistive technology, not an optional quality attribute. Automated scanners catch only a fraction of WCAG issues, so this skill pairs an axe-core scan with manual keyboard and screen reader testing and consolidates both into one accessibility-audit report with a clear remediation order. Level A violations are barriers that prevent some users from using the product at all, so a Level A finding is a hard release gate, not a soft recommendation.

## Inputs

| Field | Description |
|-------|-------------|
| `running_ui` | Built and running UI, a web app on staging or a mobile app on a device or emulator |
| `target_wcag_level` | The conformance target from the accessibility spec, one of A, AA, or AAA |
| `audit_scope` | The list of pages or screens to audit, scoped to the release when a full audit is not feasible |
| `component` | A single design-system component, when the call is to scaffold a component-level accessibility test rather than run a full audit |

## Outputs

| Artifact | Description |
|----------|-------------|
| `accessibility-audit` | Report with a conformance summary, a per-finding table, the raw axe-core JSON, manual keyboard and screen reader results, and a remediation priority order |
| axe-core test files | Source-code accessibility tests that run inside the E2E suite per page and per component, and assert zero violations at the target level |

## Procedure

1. Read the accessibility spec and `target_wcag_level` through spgr-read-artifact, and the in-scope page or component source through spgr-read-file. Confirm the UI named in `running_ui` is reachable before scanning. If the target level is unstated or the UI is not running, stop and raise spgr-escalate rather than guessing the level or auditing a stale build.
2. Run axe-core against every page in `audit_scope`. For web, run it as a Playwright plugin inside the E2E accessibility job so the same assertion runs in CI on every page in scope. WAVE and Lighthouse may supplement axe-core but do not replace it. For mobile, scan with @axe-core/react-native or accessibility-checker-android where applicable.
3. Write the axe-core test files as source code through spgr-write-file, following the test-first rule, so the failing accessibility assertion exists before any remediation is implemented. Integrate the page-level tests into the E2E suite so they run on every nightly build, not only during a dedicated audit cycle. When the call is component-scoped, write one axe-core test for the component so it carries an accessibility test before it is published. Keep the tests to what the target level requires and do not add assertions beyond it.
4. Run the manual keyboard pass. Confirm every interactive element, button, link, form field, modal, and dropdown, can be reached with Tab and Shift-Tab and activated with Enter or Space, that focus never disappears into a void, and that focus returns to a logical location after a modal closes. Record the coverage, not a pass or fail alone.
5. Run the manual screen reader pass for every component that uses an ARIA pattern, modal, carousel, tabs, accordion, or live region. Test with a real screen reader, VoiceOver on macOS or iOS or NVDA on Windows, not a check that ARIA attributes are present. Record what the screen reader announced against what the pattern requires.
6. Normalize each violation into a finding with the WCAG criterion ID and title, its level (A, AA, or AAA), the affected component or page, a description, steps to reproduce, and remediation guidance. Write remediation as a specific action that names the code location and the exact change, for example "the button at line 47 of CheckoutForm.tsx contains only an SVG icon, add aria-label with the value Close dialog", not "the button is missing a label". Reject and rewrite any remediation that does not name what to change and to what.
7. Set the remediation priority order. Level A violations come first as blocking, Level AA second as high priority, Level AAA third as scope-dependent. Track non-blocking Level AA findings as P1 bugs through a spgr-write-bug-report handoff rather than as hard gates, while Level AA findings that block core functionality stay on the gate.
8. Compute the release gate. The gate is BLOCK when any open Level A violation exists, regardless of automated or manual source. The gate is PASS only when no open Level A violation remains. Record the gate as the first scannable line of the summary, with total violations by level and the blocking count.
9. Produce the accessibility-audit report through spgr-write-artifact, which stamps the shared envelope, records per-section confidence, initializes the decision log, and runs validation inline before write. Attach the raw axe-core JSON alongside the human-readable findings. Stamp the report with spgr-version-artifact so each release retains its own audit for the trail. Log each consequential judgment, a severity call or a deferral, with spgr-log-decision.
10. When the gate is BLOCK, route the report to the human through spgr-notify-human, because a Level A barrier ships documented exclusion. For a complex ARIA remediation or an ambiguous criterion interpretation, consult the Accessibility Agent through spgr-tag-vertical-agent before finalizing the finding. If a required input is missing or sources conflict, for example axe-core reports a finding the manual pass marks fixed, stop and raise spgr-escalate with a precise list rather than issuing a PASS on incomplete evidence.

## Notes

- The axe-core test files are source code, verified by spgr-run-tests and CI rather than by an envelope schema. They must lint and format clean before commit, with one logical change per commit.
- The accessibility-audit report is written via spgr-write-artifact, and its registered schema is added to the schema registry at `schemas/` in a later build increment. Until then, validate structure through spgr-write-artifact and spgr-validate-artifact rather than inlining field lists here.
- A BLOCK gate is a correct output, not a failure of this skill. The failure is a PASS issued without the manual keyboard and screen reader passes, since automated scanning alone does not cover the criteria those passes exist to check.
- The report is release-scoped and immutable once stamped. Never edit a prior release's report to reflect a later fix.
