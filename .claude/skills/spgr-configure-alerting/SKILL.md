---
name: spgr-configure-alerting
description: Configure alert rules as source code that page on-call when an SLO is at risk, with multi-window burn-rate alerts, severity routing, and a runbook link in every alert annotation. Use when the DevOps agent wires alerting from a confirmed SLO spec, or when the Observability vertical needs the alert layer built before a release.
---

# configure-alerting

## Purpose

Translate an SLO spec into firing alert rules that page only when human action is required. Alerting quality sets on-call quality. Too many pages and operators learn to ignore them, so real incidents are missed. Too few and users find the incident first. Ground every rule in an SLO, a burn rate, or an explicit actionability criterion, and refuse to ship an alert that has no runbook.

This is source or config output owned by the DevOps agent. The Observability vertical provides the SLO spec and runbook stubs and signs off on the result through a consultation, it does not edit the alert config directly.

## Inputs

| Field | Description |
|-------|-------------|
| `slo-spec` | SLO targets and error budget windows from the Observability Agent. Read with `spgr-read-artifact`. |
| `runbook-stubs` | Alert runbook stubs from the Observability Agent. One runbook per intended alert. |
| `monitoring-config` | Existing monitoring infrastructure configuration the alert rules attach to. Read with `spgr-read-file`. |
| `escalation-policy` | On-call rotation and escalation policy that names channels and pagers per severity. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Alert rule definitions | Threshold, evaluation window, severity, and routing per rule, written as source via `spgr-write-file`. |
| Burn-rate alert config | Multi-window multi-burn-rate SLO alerts, fast-burn and slow-burn windows. |
| Alert routing rules | Which alert goes to which team, channel, or pager, from the escalation policy. |
| Dead-man's switch config | Liveness alert per critical background job, firing when an expected heartbeat stops. |
| Alert documentation | Each rule linked to its runbook through an annotation, not a separate document. |

## Procedure

1. Read the SLO spec, runbook stubs, monitoring config, and escalation policy. Use `spgr-read-artifact` for the SLO spec and `spgr-read-file` for config files. Confirm every SLO has at least one runbook stub before writing any rule.
2. Author one fast-burn and one slow-burn alert per SLO using multi-window multi-burn-rate logic. Fast burn pairs a 1h and a 5m window to catch a sudden severe outage. Slow burn pairs a 6h and a 30m window to catch gradual degradation before the error budget is exhausted. Require both windows in a pair to breach before firing, which suppresses single-spike noise.
3. Write every threshold against a symptom, not a cause. A burn-rate breach on a user-facing SLO is a symptom and pages. A resource indicator such as a connection pool nearing capacity is a cause, so set it as a warning, not a page, unless the SLO spec ties it to user impact.
4. Set severity and routing from the escalation policy. Map page-level severities to the pager and warning-level severities to a channel. Do not page on a warning.
5. Add a dead-man's switch for each critical background job named in the SLO spec or runbooks, firing on a missed heartbeat within the job's expected interval.
6. Embed the runbook link in each alert's annotation. An alert with no runbook link is incomplete. Stop and escalate rather than shipping it.
7. Write the alert rules and routing as source files with `spgr-write-file`. Verify the config parses and the rules load by running the monitoring tool's validation through `spgr-run-tests` or the CI check. Do not mark the work done on a config that fails to load.
8. Record any non-obvious choice (window pairing, a cause promoted to a page, a suppressed rule) with `spgr-log-decision`.
9. Validate the output envelope with `spgr-validate-artifact`, then route the build to the Observability vertical for sign-off through a consultation created with `spgr-tag-vertical-agent`. Do not edit the SLO spec or runbook artifacts to record that sign-off.
10. Escalate with `spgr-escalate` when an SLO has no runbook stub, when the escalation policy names no route for a required severity, when the SLO spec and monitoring config disagree on a metric, or when a requested alert has no actionability criterion and would page without a defined human action.

## Notes

- Output type is source or config, verified by `spgr-run-tests` or CI rather than by a content schema. No content schema is registered for this output yet, so `spgr-validate-artifact` applies envelope-only validation (header, confidence map, decision log, version) for now. Its content schema is registered in a later increment.
- Alert fatigue is a tracked signal. When non-actionable pages exceed the agreed threshold for an on-call week (for example more than ten), open a review and tighten the rules. Surface page-to-action ratio, time-to-acknowledge, and per-alert false-positive rate in a monthly alerting health review.
- The Observability vertical operates here as the consultant and gate. Its consultation sign-off is required before the alert config can be marked confirmed.
