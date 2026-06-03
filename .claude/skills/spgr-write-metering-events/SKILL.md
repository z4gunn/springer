---
name: spgr-write-metering-events
description: Produce a metering-events spec artifact that defines, per metered dimension, what constitutes one billable unit, which service emits the event and at which code location, the event properties, the idempotency strategy that guarantees an action is counted exactly once, the aggregation window, the failure handling when an event cannot reach the billing platform, and a monthly reconciliation procedure that compares metering counts against billed amounts. Use when the Billing Agent has a confirmed billing spec with usage-based or hybrid dimensions and must fix how usage is measured and reported before any metering code is written, or when a new metered dimension is added and its counting, idempotency, and reconciliation rules must be specified.
---

# write-metering-events

## Purpose

Define the usage metering events for a usage-based or hybrid billing model so that every billable action is counted exactly once and reported to the billing platform correctly. A metering error translates directly to a billing error, so this spec fixes the billable-unit definition, the emission point, the idempotency guarantee, the aggregation window, the failure path, and the reconciliation check before any code is written. The Billing Agent owns this artifact and operates here as a consultant to the backend agents who implement the emission points and as a gate whose spec the metering code must conform to.

## Inputs

| Field | Description |
|-------|-------------|
| `billing-spec` | The confirmed billing spec naming which dimensions are metered (API calls, seats, storage, messages, etc.). Read via `spgr-read-artifact`. |
| `architecture` | The architecture-decision and system-diagram artifacts identifying which services perform each metered action. Read via `spgr-read-artifact`. |
| `metering-api` | The billing platform metering API in use (Stripe Billing, Lago, Orb, etc.), including its idempotency-key handling and aggregation model. Read via `spgr-read-file` if supplied as reference material. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `metering-events` | A spec artifact carrying one entry per metered dimension. Written via `spgr-write-artifact` with inline `spgr-validate-artifact`. |

Each per-dimension entry records:
- Event name and semantic meaning: what constitutes one billable unit.
- Source: the emitting service and the code location where the event fires.
- Properties: customer ID, subscription ID, quantity, and idempotency key.
- Idempotency strategy: the key derivation and how the platform rejects duplicates.
- Aggregation window: real-time, hourly, or daily, and how the platform consumes the aggregated count.
- Error handling: what happens when an event fails to reach the billing platform.
- Reconciliation: how the dimension's event counts are compared against billed amounts each month.

## Procedure

1. Read the billing spec, the architecture, and the metering API reference. If the billing spec names no usage-based or hybrid dimension, stop and escalate via `spgr-escalate`, because there is nothing to meter.
2. For each metered dimension, write the billable-unit definition in one sentence, then trace it to the service and code location where the action completes. Specify that the event fires after the action succeeds, never before. A failed action is not metered.
3. Define the idempotency key for each event from a stable source already present at the emission point (request ID or event ID). State that the billing platform must reject a duplicate key so a retried emission is counted once. Do not specify an event whose key cannot be derived deterministically. Where no stable key exists at the emission point, escalate via `spgr-escalate` rather than inventing one.
4. Choose the aggregation window per dimension. Use synchronous per-event emission only where a real-time limit check drives soft-limit enforcement. For high-volume dimensions, specify local aggregation reported hourly or daily, which is the more reliable billing-time path. State how the platform consumes the aggregated count.
5. Define the failure path for each event: where a failed report is buffered, the finite retry count, and the dead-letter destination when retries are exhausted. Do not specify infinite retry. Tag the Async Infrastructure Agent via `spgr-tag-vertical-agent` when the failure path needs a durable queue or dead-letter binding.
6. Specify the monthly reconciliation procedure: compare the metering event counts against the amounts the billing platform billed, set the variance threshold that flags a systematic over- or under-count, and name the action when the threshold is breached. This catches drift before it compounds into a significant billing error.
7. Where the spec advises a backend agent on an emission point inside that agent's service code, route the recommendation through a consultation via `spgr-tag-vertical-agent`. Do not edit another agent's artifact directly.
8. Set the per-section confidence on each dimension entry: confirmed where the billing spec and architecture pin it down, proposed where a choice is recommended, and needs-human-input where a dimension's billable-unit definition or pricing intent is ambiguous. Record each material choice with `spgr-log-decision`.
9. Write the artifact with `spgr-write-artifact` and validate inline with `spgr-validate-artifact`. On a validation failure, correct the artifact and revalidate before returning. On a later revision, version it with `spgr-version-artifact`.

## Notes

- Output type is an envelope artifact (`metering-events`, a billing-vertical spec). Its content schema is registered in a later increment, so envelope-only validation applies for now: `spgr-validate-artifact` checks the header, confidence map, decision log, and version.
- Idempotency is not optional. Any dimension whose event lacks a deterministic idempotency key is incomplete and must be escalated, not shipped with a generated key.
- Reference the schema registry for envelope field shape rather than restating it here.
