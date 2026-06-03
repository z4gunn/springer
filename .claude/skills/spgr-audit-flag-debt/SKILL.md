---
name: spgr-audit-flag-debt
description: Produce a feature-flag-debt audit report that checks every flag in the feature flag registry against its spec retirement date, rollout state, last-evaluation date, codebase references, and targeting-rule count, classifying each as overdue, orphaned, stale, or a complexity contributor, then returns a prioritized cleanup list ordered by impact-to-effort ratio with a PASS or GATE verdict that flags any release flag past its retirement date. Use when the Feature Flag Agent runs the monthly or sprint-start flag-debt sweep, or when a weekly automated sweep needs the current flag-debt posture so overdue flags do not age out silently.
---

# audit-flag-debt

## Purpose

Every release flag that should have been removed is a live if-branch that tests must cover, that developers must reason about, and that can interact with newer flags in unexpected ways. This audit makes flag debt visible and retirable. Reconcile the feature flag registry against the flag specs and the codebase, classify each debt instance by severity, estimate per-flag removal effort, and emit a prioritized cleanup list. Run as the Feature Flag vertical in auditor mode. Set the gate threshold at any release flag past its planned retirement date.

This skill audits and reports only. It does not delete flags or remove flag-check code. Retirement work is a separate developer task, and the recommendation to a horizontal agent flows through a consultation, not a direct edit of another agent's artifact.

## Inputs

| Field | Description |
|-------|-------------|
| `flag-registry` | All flags in the feature flag platform with creation date, type, current rollout percentage, and last evaluation date. Read with `spgr-read-file`. |
| `flag-specs` | Feature flag specs from `spgr-define-feature-flag`, each carrying the planned retirement date. Read with `spgr-read-artifact`. |
| `codebase` | Source tree, scanned to find which flags are referenced in code versus orphaned in the platform. Read with `spgr-read-file` and `spgr-search-codebase`. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `audit-flag-debt` | Audit-report envelope artifact carrying per-flag findings grouped by category and severity, a prioritized cleanup list with estimated removal effort, and a PASS or GATE verdict. Written with `spgr-write-artifact` and validated inline with `spgr-validate-artifact`. |

## Procedure

1. Read the flag registry, the flag specs, and the codebase. If any of the three is missing, raise `spgr-escalate` with the precise list of what is absent rather than auditing a partial picture.

2. Reconcile each registry flag against its spec and the codebase. For every flag, resolve type, current rollout percentage, last evaluation date, planned retirement date, targeting-rule count, and code-reference count.

3. Classify each flag into the debt categories below. A flag can carry more than one finding.
   - Overdue retirement candidate: a release flag at 100 percent rollout for more than 2 sprints, or a release flag past its spec retirement date. Mark blocking.
   - Orphaned flag: a flag present in the platform with no reference in the codebase. Mark high.
   - Stale flag: a flag not evaluated in the last 30 days. Mark medium.
   - Complexity contributor: a flag with more than 3 targeting rules, likely entangled with other flags. Mark medium.

4. Estimate removal effort per flag from its code footprint. A release flag wrapping a single UI component is roughly one hour. A release flag threading through 10 service layers is roughly a week. Record the effort estimate on each finding.

5. Build the prioritized cleanup list. Order by impact-to-effort ratio, highest first, so the cheapest high-debt removals surface at the top. State on each entry that retirement means removing the flag check, removing the off-path code, and only then deleting the flag from the platform, never deleting the platform flag while the code check remains.

6. Set the verdict. Return GATE when any release flag is past its retirement date or has held 100 percent for more than 2 sprints. Otherwise return PASS. The gate is advisory on cleanup scheduling, not a release blocker on its own. Record the threshold and the verdict in the report.

7. Write the report with `spgr-write-artifact` and validate inline with `spgr-validate-artifact`. Record the audit decision and the chosen priority ordering with `spgr-log-decision`, and version the report with `spgr-version-artifact`.

8. On a GATE verdict, route the cleanup recommendation to the owning developer agent through `spgr-tag-vertical-agent` as a registered consultation. For the weekly automated sweep, send `spgr-notify-human` so overdue flags reach the Feature Flag Agent and do not age out silently.

## Notes

- Output type is an audit report (envelope artifact). Its content schema is not registered yet, so `spgr-validate-artifact` applies envelope-only validation for now (header, confidence map, decision log, version). The content schema is registered in a later increment.
- Cadence is monthly or at sprint-start planning, plus a weekly automated sweep, never annual.
- Do not delete flags or edit another agent's artifact. Findings drive a consultation and a cleanup list, not direct removal.
