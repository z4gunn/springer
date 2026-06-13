---
name: spgr-write-alert-runbook
description: Produce an alert-runbook artifact per alert, the step-by-step investigation and remediation guide an on-call engineer follows when the alert fires, covering what the alert means, severity and response time, immediate triage steps, common causes with symptoms, per-cause remediation, the escalation path, and required post-incident follow-up. Use when the Observability Agent has confirmed alert definitions from spgr-configure-alerting and an SLO spec and must write the runbook at alert-design time before the alert goes live, or when a post-incident review surfaces a new cause or remediation step that the existing runbook must absorb.
---

# write-alert-runbook

## Purpose

Write the runbook for one alert so the on-call engineer who is paged does not have to invent the investigation procedure during an active incident. The runbook is authored when the alert is designed, while the system's current state and failure modes are understood, not at 2 AM under pressure. A runbook that names the exact dashboards to open, the exact queries to run, the symptoms that separate one cause from another, and the remediation per cause reduces mean time to resolution and reduces the skill variance between on-call engineers. Every step must be specific and executable. "Check the database" is not a step. "Run `SELECT count(*) FROM pg_stat_activity WHERE state = 'idle in transaction'` and compare to the baseline panel in the connection-pool dashboard" is a step.

## Inputs

| Field | Description |
|-------|-------------|
| `alert-definitions` | The confirmed alert definitions from spgr-configure-alerting. One runbook is produced per alert. |
| `slo-spec` | The SLO the alert protects, for context on what threshold the alert defends and what breach means to users. |
| `system-architecture` | Service dependencies and known failure modes, used to enumerate the common causes and their symptoms. |
| `historical-incident-data` | Past incidents for this alert, if available. Common causes and proven remediation steps inform the runbook content. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `alert-runbook` | One runbook per alert. Each runbook states the alert description (what the alert measures and what it means when it fires), severity and expected response time (Critical 5 min, High 30 min, Medium next business day), immediate triage steps (which dashboards to open, which queries to run, what the alert graph should look like), common causes each with specific symptoms to look for, remediation steps per cause, the escalation path when the runbook does not resolve the issue, and the post-incident follow-up expected after resolution. |

## Procedure

1. Read the inputs with spgr-read-artifact. Read the alert definitions, the SLO spec, the system architecture, and any historical incident data. Produce one runbook per alert so no live alert is left without one.
2. Write the alert description from the alert definition and the SLO it protects. State what the alert measures, what the firing condition is, and what a firing alert means for users. Tie it to the SLO so the engineer knows the user-facing stakes.
3. Set severity and expected response time from the alert definition. Use the Springer bands: Critical 5 minutes, High 30 minutes, Medium next business day. The severity must match the alert definition's severity, not be reassigned here.
4. Write the immediate triage steps as concrete actions. Name the specific dashboard, the specific panel, and the specific query. State what the alert graph should look like in the firing state versus a healthy state so the engineer can confirm the alert is real and not noise.
5. Enumerate the common causes from the system architecture failure modes and historical incident data. For each cause, write the specific indicators that distinguish it from the other causes. A cause without distinguishing symptoms is not actionable and forces guesswork during the incident.
6. Write the remediation steps for each cause as executable instructions. Each step is a command, a query, a config change, or a navigation path, not a vague directive. Order the causes by likelihood where historical data supports an ordering.
7. Write the escalation path: who to page, in what order, and the condition that triggers escalation when the runbook steps do not resolve the issue. The condition must be observable, not "if it still seems broken".
8. Write the post-incident follow-up: the actions expected after resolution, including the requirement that this runbook is reviewed and updated with any new cause or remediation step discovered during the incident. Runbooks are living documents.
9. State that the runbook is linked from the alert annotation so the alert notification carries a direct URL to it. If the alert definition has no runbook-URL annotation slot, that is an alerting gap. Record it and route it to the spgr-configure-alerting owner rather than shipping an unlinked runbook.
10. Set the runbook-usage tracking the alert should emit: consultation frequency per runbook, incidents resolved without consulting the runbook, and alerts that fired with no runbook access (which signals an unlinked runbook or a non-actionable alert). Record these as required observability outputs of this runbook.
11. Record consequential choices with spgr-log-decision, in particular a chosen severity band, a cause-ordering call, and any escalation-path decision.
12. The Observability vertical advises on the alert definition and SLO sections but does not edit them. Where the runbook reveals that an alert is not actionable, a threshold is wrong, or an SLO is mis-set, route the recommendation to the owning agent through spgr-tag-vertical-agent rather than editing the alert definition or SLO spec directly.
13. Write the artifact with spgr-write-artifact, then confirm it with spgr-validate-artifact. If any input is missing, if an alert has no SLO or no defined failure modes to draw causes from, or if validation fails, raise spgr-escalate with a precise list of what is missing rather than filling the gap with an assumption.

## Notes

- This skill produces an envelope artifact (alert-runbook). Write it through spgr-write-artifact and confirm it inline with spgr-validate-artifact. The alert-runbook content schema is not yet in the registry at `schemas/`, so envelope-only validation applies for now (header, confidence map, decision log, and version are checked). Its content schema is registered in a later build increment.
- This skill writes the runbook only. It does not define alerts (spgr-configure-alerting) and it does not set SLOs (spgr-write-slo-spec). A runbook for an alert that does not exist, or that defends no SLO, is not confirmable and must be escalated to the owning agent.
- A runbook step is acceptable only if it is executable as written. Any step that requires the engineer to invent the procedure is incomplete and the runbook must not be marked confirmed until it is replaced with a concrete action.
- A runbook is a living document. After every incident on this alert, the runbook is reviewed and updated. A new version is stamped with spgr-version-artifact when it changes after first write.
