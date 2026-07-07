---
name: spgr-write-event-taxonomy
description: Produce an event-taxonomy artifact defining the product's complete analytics event schema, with per-event triggers, typed properties, prohibited PII, and a generated type-safe tracking SDK. Use when the Analytics Agent must settle the event contract before any instrumentation is written, or when a new user journey extends the taxonomy.
---

# write-event-taxonomy

## Purpose

Define the analytics event schema before instrumentation begins, not by reading back what code already emits. The taxonomy is the contract between what the product does and what the data team can analyze. Without it, events are named inconsistently, carry inconsistent properties, and need reverse-engineering to interpret. A settled taxonomy makes funnels, engagement metrics, and attribution reliable. This skill is run by the Analytics vertical as a consultant to product and developer agents and as the gate that instrumentation work depends on.

## Inputs

| Field | Description |
|-------|-------------|
| `user-journeys` | Core user journeys from the product spec, the actions and state changes worth tracking |
| `business-questions` | The funnels, engagement metrics, and retention signals the product team needs to answer |
| `analytics-platform` | The platform in use (Segment, Amplitude, Mixpanel, PostHog), which sets the SDK codegen target |
| `data-classification` | The classification artifact, read to confirm which fields are PII and must not appear in events |

## Outputs

| Artifact | Description |
|----------|-------------|
| `event-taxonomy` | Envelope artifact listing every event with name, trigger, typed properties, context properties, prohibited properties, and a daily volume estimate. Written via spgr-write-artifact |
| type-safe tracking SDK | Generated tracking code (Typewriter for Segment, or custom codegen for the platform) written via spgr-write-file, giving developers compile-time errors on misnamed events or missing required properties |

## Procedure

1. Read the user journeys, business questions, and platform with spgr-read-file or spgr-read-artifact. For each business question, work backward to the events and properties that must exist to answer it. Do not invent events that no question needs.
2. Name each event with the `object_action` convention: the noun (what was acted on) first, the verb (what happened) second, in snake_case. `signup_completed` is correct, `completed_signup` is not.
3. Write a precise trigger for each event, naming the exact user action and state change that fires it. Ambiguous triggers produce inconsistent instrumentation.
4. Type every property as string, number, boolean, or timestamp, and mark each required or optional. Untyped or inconsistently typed properties break tooling that relies on schema inference.
5. Record the context properties auto-included on every event (user_id, session_id, timestamp, platform, app_version). Record prohibited properties: no PII in events. Opaque user_id is acceptable. Email, full name, and address are not.
6. Design events as immutable after they are sent. Do not design an event that needs later correction. When a state change can be reversed (item added to cart, then removed), track each direction as its own event.
7. Add a per-day volume estimate to each event so the data team can size storage and sampling.
8. Generate the type-safe tracking SDK from the finished taxonomy using the platform codegen tool, and write it with spgr-write-file. Verify it builds via spgr-run-tests or CI so a misnamed event or missing required property is a compile-time failure.
9. Write the taxonomy with spgr-write-artifact and run spgr-validate-artifact inline. Record consequential naming or property choices with spgr-log-decision.
10. When a journey or business question is missing, contradictory, or implies tracking a field the classification marks as PII, stop and raise spgr-escalate rather than inventing the event or emitting the PII. Route the PII justification and any privacy sign-off to the Compliance vertical through spgr-tag-vertical-agent rather than approving it inside this artifact.

## Notes

- Output type: envelope artifact (event-taxonomy) plus generated source (tracking SDK). The event-taxonomy content schema is registered in a later increment, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, version).
- A PII exception in an analytics event is never granted inside this skill. It requires explicit justification and Compliance privacy review, routed as a consultation via spgr-tag-vertical-agent.
- Version revisions to an existing taxonomy with spgr-version-artifact so additive event changes stay traceable.
