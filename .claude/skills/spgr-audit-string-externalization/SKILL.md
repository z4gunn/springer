---
name: spgr-audit-string-externalization
description: Produce a string-externalization audit report that finds every hard-coded user-visible string not routed through the i18n system, ranked by user-flow priority, returning a PASS or GATE verdict that blocks localization start while such strings remain. Use when the i18n Agent must confirm the codebase is fully externalized before translation begins.
---

# audit-string-externalization

## Purpose

Find the gap between using an i18n library and routing all user-visible text through it. Hard-coded strings hide in backend error messages returned in API responses, date format strings in utilities, button labels in component props, and email subject-line constants. Finding them by static analysis is faster than discovering them during translation review. This skill produces an audit report (an envelope artifact carrying findings by category and a gate verdict), and it stands up the CI lint rule that prevents regression once externalization is complete. It does not extract the strings, that is the developer agent's work driven from this report.

Operate in the i18n vertical's three modes. As consultant, run the audit on request and route findings. As auditor, run the scheduled sweep and report posture. As gate, return GATE when any user-visible string remains hard-coded, which blocks localization from starting and blocks the release.

## Inputs

| Field | Description |
|-------|-------------|
| `codebase` | Source tree to scan. Read source via spgr-read-file and locate candidates via spgr-search-codebase. |
| `i18n-config` | The i18n library configuration, defining how an externalized string is recognized (translation function call name, string-resource file paths). A string already inside that mechanism is not a finding. |
| `ui-inventory` | Component and template inventory naming all UI-rendering code, plus the email and notification content paths to scan. |
| `user-flow-map` | The primary user-flow list, used to rank a finding's priority. Strings on a primary flow rank highest. Read via spgr-read-artifact if available. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `string-externalization-audit` | Audit report written via spgr-write-artifact. Carries the hard-coded-string findings list (each with file, line, the string, its category, priority, and an extraction-effort estimate), per-category counts, and a PASS or GATE verdict. |
| CI lint rule | Source or config written via spgr-write-file that fails the build when a new hard-coded user-visible string is introduced. Verified by spgr-run-tests or CI before the audit is marked confirmed. |

## Procedure

1. Read `i18n-config` to learn the externalization mechanism. Record the translation-function name and the resource-file paths so the scan can tell an externalized string from a hard-coded one.
2. Scan UI-rendering code, email templates, and notification content for string literals using spgr-search-codebase, scoped by `ui-inventory`. For each candidate, capture the file, line number, and the literal text.
3. Apply the inclusion and exclusion rules to each candidate. Include backend error messages that are returned in API responses and shown to users, even though they originate server-side. Exclude log messages and console output, they are for developers and need no translation. Exclude strings in tests unless the test asserts UI display behavior. Drop any candidate already routed through the i18n mechanism from step 1.
4. Categorize each remaining finding by string type: UI label, error message, email template, notification, or other user-visible text. Note that a log message is never a finding.
5. Rank each finding by priority using `user-flow-map`. A string on a primary user flow is highest priority. Estimate extraction effort per finding (for example small for a single literal, larger for a dynamic string).
6. Flag dynamic strings (concatenated or interpolated at runtime) for manual inspection. Static analysis cannot confirm these, so record them as needs-human-input in the confidence map rather than asserting them as confirmed.
7. Set the verdict. Return GATE when any user-visible string remains hard-coded, which is a blocking condition that prevents localization from starting. Return PASS only when no user-visible string is hard-coded outside the i18n mechanism.
8. Write the report via spgr-write-artifact and validate it inline with spgr-validate-artifact. On a validation failure, fix the artifact and re-validate before proceeding. Version the report with spgr-version-artifact and record the verdict rationale with spgr-log-decision.
9. Stand up the CI lint rule via spgr-write-file so a new hard-coded user-visible string fails the build, preventing regression after the initial externalization. Verify the rule with spgr-run-tests or CI.
10. On a GATE verdict, route the finding set to the owning developer agent through a consultation via spgr-tag-vertical-agent rather than editing that agent's code or artifacts directly. Raise spgr-escalate when an input is missing or contradictory (for example no i18n-config or an empty ui-inventory), and use spgr-notify-human when a gate blocks a release.

## Notes

- Output type is an audit report (envelope artifact) plus a CI source artifact. The audit report has no registered content schema yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) for now. The content schema for this type is registered in a later increment.
- Do not edit another agent's code or artifact to externalize a string. The i18n vertical advises, and the developer agent acts. Route the recommendation through spgr-tag-vertical-agent.
- The gate threshold is exact: any single hard-coded user-visible string makes the verdict GATE. There is no soft pass for a partial surface.
- Carry dynamic, runtime-concatenated strings as needs-human-input, not as confirmed findings, since static analysis cannot verify them.
