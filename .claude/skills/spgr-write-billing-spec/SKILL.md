---
name: spgr-write-billing-spec
description: Produce a billing-spec artifact that defines the complete billing model for a subscription product, covering the plan catalog with platform price IDs, trials, proration, cancellation, tax, webhook events, and dunning entry points. Use when the Billing Agent must settle the billing model before any subscription or payment code is implemented.
---

# write-billing-spec

## Purpose

Define the billing model for a subscription product as one written contract: the plans, their prices and intervals, trial mechanics, upgrade and downgrade behavior, cancellation behavior, invoicing, the platform webhook events the system must handle, and payment-failure handling. Billing is one of the highest-risk areas to build ad hoc, because errors move real money. Overcharging a customer damages trust and undercharging damages the business. A written spec makes the intended behavior explicit so implementation is verified against the contract, not against intuition.

The Billing Agent owns this artifact as a vertical specialist. The spec depends on the entitlement map produced by the Feature Flag Agent and advises the backend and DevOps agents that implement subscription, payment, and webhook handling. When the spec needs another agent to act on it, or constrains another agent's artifact section, route that recommendation through a consultation with spgr-tag-vertical-agent rather than editing the other agent's artifact directly.

## Inputs

| Field | Description |
|-------|-------------|
| Entitlement map | The feature-by-plan matrix, read via spgr-read-artifact, which fixes which features each plan grants |
| Pricing model | Flat rate, per-seat, usage-based, or hybrid, which sets how prices and proration are framed |
| Trial mechanics | Trial length, whether a card is required up front, and the intended conversion flow |
| Billing platform | Stripe, Paddle, Chargebee, or equivalent, which sets the product and price ID mapping and the webhook event names |

## Outputs

| Artifact | Description |
|----------|-------------|
| `billing-spec` | Envelope artifact written via spgr-write-artifact, holding the plan catalog, trial configuration, upgrade and downgrade behavior with proration rules, cancellation behavior, invoice and tax configuration, the webhook event handling list, payment-failure and dunning entry points, and the billing scenario test suite |

## Procedure

1. Read the inputs. Read the entitlement map and any existing plan or pricing artifacts with spgr-read-artifact. Read source pricing or platform config files, if supplied, with spgr-read-file. If the entitlement map is missing, the pricing model contradicts the entitlement map, or the billing platform is unspecified, stop and raise spgr-escalate with the precise list of what is missing or contradictory. Do not assign a default platform or pricing model.
2. Build the plan catalog. One row per plan, with plan name, price, billing interval, and the platform product and price ID mapping (for example the Stripe product and price ID for each interval). Annual and monthly intervals of the same plan are separate price IDs.
3. Specify the trial configuration. Record trial length, whether a card is required at signup, and what happens at trial end: auto-convert to paid, require a card before conversion, or downgrade to a free tier. Trial-to-paid conversion is a high-stakes flow, so define exactly what triggers the conversion, what happens if the card fails at conversion, and how the user is notified at each step.
4. Specify upgrade and downgrade behavior. State when the change takes effect (immediate or end-of-period) and the proration rule explicitly. The platform supports immediate proration, metered proration, and no proration. Choose against the commercial model and what customers expect, and record the choice. Never leave proration implicit.
5. Specify cancellation behavior. State whether cancellation is immediate or end-of-period, and the post-cancellation data retention behavior. Coordinate the retention window with the Compliance Agent through a consultation rather than setting it here in isolation.
6. Specify invoice and tax configuration. Record invoice items, line-item descriptions, and tax handling (for example platform tax automation versus a tax service versus none).
7. List the webhook events the system must handle. At minimum cover payment succeeded, payment failed, subscription updated, and subscription cancelled, named with the platform's event identifiers. For each event, state the system action the handler performs.
8. Specify payment-failure handling. Record the dunning sequence entry points: what fires on first failure, on retry, and on final failure, and where each enters the dunning flow.
9. Record the no-card-storage rule. State that the application never stores card numbers. The platform stores cards. The application stores only the platform customer ID and payment method ID. Carry this as a constraint in the artifact for the implementer and the Security Agent.
10. Define the billing scenario test suite. List the automated tests an implementer must generate against the platform test environment: plan creation, upgrade, downgrade, cancellation, failed payment, and trial conversion. Carry this list in the artifact so the implementer builds the suite from the spec, not from memory.
11. Record consequential choices with spgr-log-decision: the proration rule per plan change, the trial-end behavior, the cancellation and retention behavior, and the tax-handling choice, each with alternatives considered.
12. Validate and version. Run spgr-validate-artifact inline before marking the artifact confirmed, then version it with spgr-version-artifact.

## Notes

- Output type is an envelope spec artifact (`billing-spec`). Call spgr-validate-artifact regardless. The `billing-spec` content schema is not registered yet, so envelope-only validation applies for now (header, confidence map, decision log, and version are checked). Its content schema is registered in a later increment.
- The registered content-schema artifact types are listed in the schema registry. Reference the registry rather than restating field lists here.
- A pricing or plan change is a scope change in billing terms. When the spec is revised under such a change, route the human gate through spgr-notify-human and surface the diff so downstream subscription and webhook configuration is re-derived.
- The no-card-storage constraint is a security gate item. Route it to the Security Agent through spgr-tag-vertical-agent as a registered consultation, and route the post-cancellation retention window to the Compliance Agent the same way, rather than editing those agents' artifacts directly.
