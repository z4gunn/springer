---
name: spgr-write-webhook-spec
description: Produce a webhook-spec artifact defining inbound billing-platform webhook handling per event, covering the application state change, idempotency, signature verification, retry behavior, ordering tolerance, and replay. Use when the Billing Agent must fix webhook requirements before the Async Infrastructure Agent implements the endpoint.
---

# write-webhook-spec

## Purpose

Billing-platform webhooks are how the application learns about subscription and payment state changes. A missing handler lets application billing state diverge from the platform (a subscription cancelled in Stripe still reads active locally). A handler without idempotency or signature verification produces either data corruption or an unauthenticated endpoint anyone can call. Produce the webhook-spec that makes these requirements explicit before the Async Infrastructure Agent builds anything.

This is a Billing vertical artifact. The implementation belongs to the Async Infrastructure Agent. Where this spec constrains another agent's work (the webhook endpoint, the delivery infrastructure), route the recommendation as a consultation through spgr-tag-vertical-agent rather than editing that agent's artifact directly.

## Inputs

| Field | Description |
|-------|-------------|
| `billing-spec` | The confirmed billing spec, read via spgr-read-artifact. Source of which billing events affect application state and what the target state is. |
| `webhook-event-catalog` | The billing platform's published webhook event catalog (for example the Stripe event-type list), read via spgr-read-file. |

If the billing spec is missing, unconfirmed, or does not state the application state change for an event in scope, stop and raise spgr-escalate rather than guessing the mapping.

## Outputs

| Artifact | Description |
|----------|-------------|
| `webhook-spec` | Envelope artifact written via spgr-write-artifact. Per event in scope: event name, required application state change, idempotency handling, signature verification requirement, error and retry behavior, ordering tolerance. Plus a webhook replay procedure. |

## Procedure

1. Read the billing spec via spgr-read-artifact and the platform webhook event catalog via spgr-read-file. List every event whose delivery changes application state. An event in the billing spec with no matching catalog entry, or a catalog entry the billing spec does not account for, is a gap to escalate, not to fill.

2. For each in-scope event, record the event name exactly as the platform emits it (for example `customer.subscription.updated`, `invoice.payment_failed`).

3. For each event, state the required application state change in concrete terms (for example set `subscription.status` to `past_due`). Trace it back to the billing spec so the mapping is auditable.

4. Specify idempotency handling for every event. The handler stores processed platform event IDs and checks the store before processing, because the platform can deliver the same event more than once and the handler must be safe to re-run.

5. Specify signature verification as mandatory for every inbound webhook. The endpoint verifies the platform signature before any processing. Record this as a non-negotiable requirement, not an option. An unverified endpoint is an unauthenticated endpoint.

6. Specify error and retry behavior. The endpoint acknowledges receipt with HTTP 200 before processing, then processes asynchronously. Enqueue the event, return 200, process in the background. For a transient processing failure the background worker signals the platform to retry (return 500 on the synchronous path only if processing has not been deferred). State the response code contract per event so the implementer cannot improvise it.

7. Specify ordering tolerance. Events may arrive out of order. Require every state-machine transition to be idempotent and order-tolerant so a late or duplicate event cannot move application state backward.

8. Specify the webhook replay procedure: how to re-process historical webhook events for a specific subscription or customer, for data recovery after an application-side bug. Replay reuses the same idempotency and ordering guarantees so re-running an already-processed event is a no-op.

9. Write the artifact via spgr-write-artifact with inline spgr-validate-artifact. Set the confidence map per section (confirmed where the billing spec is confirmed, proposed where you inferred a mapping the billing spec did not state explicitly). Record each non-obvious mapping decision with spgr-log-decision, then version with spgr-version-artifact.

10. Tag the Async Infrastructure Agent via spgr-tag-vertical-agent so the implementation consultation is registered. Where signature verification or idempotency touches a security boundary, tag the Security Agent the same way. On any blocking gap surfaced above, raise spgr-escalate and stop rather than emitting a partial spec.

## Notes

- Output type is an envelope spec artifact. The `webhook-spec` content schema is not registered yet, so spgr-validate-artifact applies envelope-only validation for now (it checks the header, confidence map, decision log, and version). Its content schema is registered in a later increment. Still call spgr-validate-artifact.
- A vertical recommendation to a horizontal agent flows through the registered consultation artifact (spgr-tag-vertical-agent). Do not edit the Async Infrastructure Agent's endpoint artifact directly.
- Signature verification and idempotency are gate conditions for this vertical. A spec that marks either as optional fails the gate.
