---
name: spgr-audit-billing-accuracy
description: Produce a billing-accuracy audit report that reconciles application billing state against Stripe as source of truth, recording subscription, entitlement, and metering discrepancies, with a PASS or GATE verdict that escalates any discrepancy over the revenue threshold. Use when the Billing Agent runs a scheduled reconciliation sweep.
---

# audit-billing-accuracy

## Purpose

Billing carries a class of bugs that unit tests do not catch and that surface only when a customer complains or finance runs a reconciliation. Customers get charged the wrong amount. A subscription that should have cancelled stays active. Usage-based charges double-count or miss metering events. These drift silently and compound. This audit runs the reconciliation proactively, before the discrepancy reaches an invoice.

This skill operates the Billing Agent in auditor and gate mode. The audit treats the billing platform as the source of truth for payment and subscription state. The application must reflect the platform, never the reverse, so every divergence is read as an application defect to remediate, not a platform record to overwrite. The audit is idempotent and read-only. It queries and compares. It does not modify either system. Remediation is a separate, human-confirmed action.

## Inputs

| Field | Description |
|-------|-------------|
| `application-billing-state` | Subscription records and entitlement records from the application database. Read with spgr-read-file. |
| `billing-platform-data` | Stripe customers, subscriptions, and invoices, queried read-only through the platform API. Read with spgr-read-file. |
| `metering-event-logs` | The recorded usage events, sampled to compare event count against billed usage. Read with spgr-read-file. |
| `entitlement-map` | The map of which features each plan grants, used to check entitlement records against the subscribed plan. Read with spgr-read-artifact. |
| `revenue-impact-threshold` | The per-finding revenue threshold (default 100 dollars per month in either direction) above which a finding escalates to the human. |
| `audit-scope` | Optional. The cycle window or customer subset under audit, used to scope the verdict. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `billing-accuracy` | Audit report envelope artifact written via spgr-write-artifact. Carries application-versus-platform state discrepancies (subscriptions in differing states, mismatched plan IDs), entitlement-versus-subscription mismatches, the metering accuracy assessment (sampled event count versus billed usage), a revenue-impact estimate per finding, remediation steps per finding, and a PASS or GATE verdict. |

## Procedure

1. Read the inputs. Load the application billing state, the billing platform data, and the metering event logs with spgr-read-file, and the entitlement map with spgr-read-artifact. If any of the three primary sources is absent, stop and raise spgr-escalate with the precise list of what is missing. Do not infer platform state from the application records, since the platform is the source of truth.

2. Reconcile subscription state against the platform. For each customer compare the application subscription record against the Stripe subscription. Record any state divergence (for example active in the application but cancelled or past-due in Stripe) and any mismatched plan ID. The platform value is correct in every case, so each divergence is an application defect.

3. Reconcile entitlements against the subscribed plan. For each user compare entitlement records against the features the subscribed plan grants per the entitlement map. Record every user holding an entitlement to a feature their subscription does not include, and every user missing an entitlement their plan grants.

4. Assess metering accuracy. Sample the metering event logs over the audit window and compare the sampled event count against the usage billed by the platform. Record under-billing (events recorded but not billed) and over-billing (usage billed beyond recorded events, including any double-count).

5. Estimate revenue impact per finding. For each discrepancy compute the dollar impact per month and its direction. Over-charging the customer is one direction, under-charging is the other. Both directions count against the threshold.

6. Set the verdict and the escalation flag. The blocking threshold is any single finding whose revenue impact exceeds `revenue-impact-threshold` in either direction. Over-charging is a legal risk. Under-charging is a financial loss. The verdict is GATE if any finding crosses the threshold, otherwise PASS. If `audit-scope` is supplied, score the verdict against only the customers and window in scope.

7. Attach remediation steps per finding. For each discrepancy state the corrective action that reconciles the application to the platform. Mark every remediation step as a separate, human-confirmed action. This audit does not apply them.

8. Write and validate the report. Write the `billing-accuracy` artifact via spgr-write-artifact with inline spgr-validate-artifact. Record the verdict rationale and the threshold-crossing findings with spgr-log-decision.

9. Escalate and route. For any finding crossing the revenue-impact threshold, escalate immediately to the human with spgr-notify-human. Route each remediation owned by another agent (a backend developer fix to the application sync, a data correction) through a consultation with spgr-tag-vertical-agent rather than editing that agent's code or artifact directly.

## Notes

- Output type is an audit report (envelope artifact). Its content schema is registered in a later increment, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, version).
- Blocking threshold: any finding whose revenue impact exceeds the threshold (default 100 dollars per month) in either direction yields a GATE verdict and an immediate human escalation. Over-charging is a legal risk, under-charging is a financial loss, so both directions gate.
- The billing platform is the source of truth for subscription and payment state. Every application-versus-platform divergence is an application defect to remediate, never a platform record to overwrite.
- This audit is idempotent and read-only. It queries and compares both systems and writes only the report. Remediation steps are separate, human-confirmed actions routed through spgr-tag-vertical-agent.
- Run cadence is monthly in production and before each billing cycle closes. The Phase 2 build target is to automate this as a nightly reconciliation job that alerts on any threshold-crossing discrepancy rather than waiting for the monthly run.
