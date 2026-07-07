---
name: spgr-write-entitlement-map
description: Produce an entitlement-map artifact defining the feature-by-plan matrix for a subscription product, with usage limits, add-ons, per-entitlement enforcement points, and degradation behavior. Use when the Feature Flag Agent must settle the plan-to-feature relationship before enforcement is implemented, or when a pricing change revises the matrix.
---

# write-entitlement-map

## Purpose

Define the entitlement matrix that maps subscription plans to the features and usage limits each plan grants, plus where and how each entitlement is enforced. This is the enforcement layer of the billing model. Without a written map, access decisions scatter across controllers, drift out of sync, and resist change when pricing moves. The map makes the plan-to-feature relationship explicit and queryable from one place, so a pricing change edits the map and not the enforcement code.

The Feature Flag Agent owns this artifact as a vertical specialist. The map advises the Billing Agent's subscription and billing configuration. When the map needs the Billing Agent to act on it, or constrains another agent's artifact section, route that recommendation through a consultation with spgr-tag-vertical-agent rather than editing the other agent's artifact directly.

## Inputs

| Field | Description |
|-------|-------------|
| Subscription plan definitions | Plan names, tiers, pricing model, monthly and annual price, target ICP per plan |
| Feature inventory | The full list of gated features, read from the PRD via spgr-read-artifact |
| Billing model | Per-seat, per-usage, flat rate, or add-on, which sets how usage limits and add-ons are framed |

## Outputs

| Artifact | Description |
|----------|-------------|
| `entitlement-map` | Envelope artifact written via spgr-write-artifact, holding the plan definitions table, the feature-by-plan matrix with per-plan usage limits, the add-on entitlement list, the enforcement-point specification per entitlement, and the graceful-degradation behavior per gate |

## Procedure

1. Read the inputs. Read the feature inventory from the PRD and any existing plan or billing artifacts with spgr-read-artifact. Read source plan or pricing files, if supplied, with spgr-read-file.
2. Build the plan definitions table. One row per plan, with plan name, monthly and annual price, pricing model, and target ICP.
3. Build the feature-by-plan matrix. One row per feature in the inventory, one column per plan. Each cell records whether the feature is included and any usage limit that plan imposes on it, for example a Starter plan capped at 5 projects. Leave no feature unassigned across plans.
4. List add-on entitlements. Record each feature that is available as a paid add-on regardless of plan, with its add-on price and the plans it can attach to.
5. Specify the enforcement point for each entitlement. Name where the check runs: API middleware, service layer, or UI gate. Require a service-layer check on every entitlement, since a UI that hides an upgrade-gated control is UX and the service-layer check is the security boundary. State that checks route through one centralized `hasEntitlement(user, feature)` function that consults the entitlement service, not per-feature ad-hoc checks scattered across controllers.
6. Specify graceful-degradation behavior per gate. Record what a non-entitled user sees: paywall, upgrade prompt, or hidden feature. For every usage limit, specify both a hard enforcement gate that errors when the limit is reached and a soft warning that fires when the user approaches the limit.
7. Derive the enforcement test list. For each feature-by-plan cell, list the tests that an implementer must generate: an entitled user can access the feature, and a non-entitled user receives the gate response specified in step 6. Carry this list in the artifact so the Billing or Feature Flag implementer builds tests from the matrix.
8. Record consequential choices with spgr-log-decision: the rationale for each enforcement point, each usage limit, and each degradation behavior, with alternatives considered.
9. Validate and version. Run spgr-validate-artifact inline before marking the artifact confirmed, then version it with spgr-version-artifact. If the feature inventory has features no plan covers, the billing model contradicts the plan definitions, or a required input is missing, stop and raise spgr-escalate with the precise list of what is missing or contradictory rather than assigning a default. Do not fill gaps with assumptions.

## Notes

- Output type is an envelope spec artifact (`entitlement-map`). Call spgr-validate-artifact regardless. The `entitlement-map` content schema is not registered yet, so envelope-only validation applies for now (header, confidence map, decision log, and version are checked). Its content schema is registered in a later increment.
- The registered content-schema artifact types are listed in the schema registry. Reference the registry rather than restating field lists here.
- A pricing change is a scope change in billing terms. When the map is revised under a pricing change, route the human gate through spgr-notify-human and surface the diff so downstream billing configuration is re-derived.
- A recommendation to the Billing Agent flows through spgr-tag-vertical-agent as a registered consultation, not as a direct edit of the billing artifact.
