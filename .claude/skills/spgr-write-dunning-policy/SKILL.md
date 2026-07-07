---
name: spgr-write-dunning-policy
description: Produce a dunning-policy artifact defining the payment-failure recovery sequence for a SaaS subscription, covering the retry schedule, customer notifications, access degradation, and cancellation triggers. Use when the Billing Agent has a confirmed billing spec and must settle failed-payment recovery before billing goes live.
---

# write-dunning-policy

## Purpose

Define the full payment-failure recovery sequence for a SaaS subscription so failed charges are recovered automatically without cutting off paying customers prematurely. The Billing Agent owns this as a vertical specialist operating in consultant, auditor, and gate modes. The policy is the contract that the billing platform configuration, the transactional email templates, and the entitlement-restriction logic all implement against. A sequence that recovers too aggressively alienates customers, and one that is too permissive delivers service without payment, so the policy fixes the timing, the access degradation, and the cancellation trigger explicitly rather than leaving them to implementation habit.

The dunning policy is a billing envelope artifact. Where the policy needs another agent to restrict a feature during degraded access or to wire a recovery deep link, route that recommendation through a consultation rather than editing the other agent's artifact.

## Inputs

| Field | Description |
|-------|-------------|
| `billing-spec` | Subscription tiers and service-degradation options. Read via `spgr-read-artifact`. |
| `entitlement-map` | Which features can be restricted during dunning. Read via `spgr-read-artifact`. |
| `support-workflow` | How the support team is notified of dunning cases and handles manual outreach. Read via `spgr-read-file` or `spgr-read-artifact`. |
| `platform-capabilities` | Whether the billing platform supports smart retries (Stripe Adaptive Acceptance, Chargebee smart retry). |

## Outputs

| Artifact | Description |
|----------|-------------|
| `dunning-policy` | Billing envelope artifact written via `spgr-write-artifact`. Covers retry schedule, notification sequence, service-access degradation, cancellation and retention trigger, recovery flow, team escalation, and analytics. |

## Procedure

1. Read the billing spec, the entitlement map, and the support workflow. Confirm the subscription tiers, the degradable features, and the support notification channel are all present. If any is missing or contradictory, stop and raise `spgr-escalate` with the precise list of what is needed. Do not assume tiers, degradable features, or grace-period length.

2. Set the retry schedule. When the platform supports smart retries, specify smart retries and record that fixed-interval timing is delegated to the platform's acceptance model. When it does not, specify an explicit fixed schedule (for example first failure on Day 0, retries on Day 3, Day 7, and Day 14). Record the maximum retry count and the final-attempt date.

3. Define the customer notification sequence tied to the retry schedule. Specify an email on the first failure, a reminder before the final retry, and a cancellation notice. Each notification must carry a direct deep-linked path to the payment-update screen. Record the trigger event and timing for each message.

4. Define service access during dunning. Specify the grace period with full access (7 to 14 days is the standard, never terminate on the first failure), then degraded access after N days, then read-only after M days. Map each degradation step to the specific features it restricts, drawn from the entitlement map. Where restricting a feature requires another agent to enforce it, register that through `spgr-tag-vertical-agent` as a consultation rather than editing the entitlement map directly.

5. Define the cancellation trigger and the data-retention countdown. State exactly when the subscription is cancelled (typically after the final failed retry) and what event starts the retention-and-deletion clock.

6. Define the recovery flow. State how a customer updates the payment method, what re-attempt the update triggers, and how access is restored on a successful charge.

7. Define team escalation. State when a dunning case is surfaced to the support team for manual outreach (for example a high-value account reaching the final retry), routed through the support notification channel from the input.

8. Define the dunning analytics. Specify tracking of recovery rate by retry attempt, average time to recovery, and involuntary churn rate, with the targets that signal whether the sequence is correctly tuned.

9. Write the artifact via `spgr-write-artifact` and run `spgr-validate-artifact` inline. Record each policy decision and its rationale through `spgr-log-decision`, and mark each section's confidence as confirmed, proposed, or needs-human-input. Version the result with `spgr-version-artifact`. When platform capabilities are unknown, set the retry-schedule section to needs-human-input rather than guessing.

## Notes

- Output type is a billing envelope artifact (`dunning-policy`). Its content schema is registered in a later increment, so `spgr-validate-artifact` applies envelope-only validation for now (it still checks the header, confidence map, decision log, and version).
- Never specify immediate service termination on a first payment failure. The grace period is mandatory.
- Every customer-facing dunning message must include the deep-linked payment-update path. A policy that lacks it is incomplete and must be flagged as needs-human-input.
- A recommendation that another agent must act on (feature restriction, recovery deep link, email template) flows through `spgr-tag-vertical-agent` as a consultation, not a direct edit of that agent's artifact.
