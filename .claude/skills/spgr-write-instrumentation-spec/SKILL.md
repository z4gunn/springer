---
name: spgr-write-instrumentation-spec
description: Produce an instrumentation-spec artifact that maps every event from the event taxonomy to the exact code location where it fires, with file path and function, the precise trigger condition, per-property resolution to a concrete source, and a test-coverage requirement per event, plus a CI coverage check that flags taxonomy events not yet fired in the test suite. Use when the Analytics Agent has a confirmed event taxonomy and the application architecture and must remove instrumentation ambiguity before developers wire the events, or when a backend or frontend agent needs the firing location and property mapping for an event it is about to implement.
---

# write-instrumentation-spec

## Purpose

Define where in the codebase each analytics event fires, so developers do not interpret the taxonomy differently from one another. The taxonomy says what to track and which properties to include. This spec says the exact file, function, trigger condition, and property source. Without it, one developer fires `signup_completed` on form submit, another on the API response, another on the confirmation screen render, and the funnel data becomes unreliable. Removing that interpretation is the whole job of this skill.

This skill operates as a consultant and gate for the Analytics vertical. It produces the instrumentation-spec envelope artifact and the CI coverage check. It does not edit another agent's artifact. Where a horizontal developer agent needs an instrumentation decision reflected in its own artifact or code review, route the recommendation through `spgr-tag-vertical-agent`.

## Inputs

| Field | Description |
|-------|-------------|
| `event-taxonomy` | The confirmed taxonomy of events and their properties. Read with `spgr-read-artifact`. The set of events to map comes from here. |
| `application-architecture` | Which components handle which user interactions, so each event maps to a real code location. Read with `spgr-read-artifact` or `spgr-read-file`. |
| `existing-instrumentation` | Any events already fired in the codebase, so the spec separates what exists from what must be added. Read with `spgr-read-file` or `spgr-search-codebase`. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `instrumentation-spec` | Envelope artifact mapping each taxonomy event to file path and function or component, trigger condition, per-property resolution, and a test-coverage requirement. Written with `spgr-write-artifact` and validated inline with `spgr-validate-artifact`. |
| coverage check | A CI check comparing the taxonomy against events fired in the test suite, flagging taxonomy events that are not yet tested. Written as source with `spgr-write-file` and verified by `spgr-run-tests` or CI. |

## Procedure

1. Read the event taxonomy, application architecture, and existing instrumentation with `spgr-read-artifact`, `spgr-read-file`, and `spgr-search-codebase`. If an input is missing, or the architecture has no component that can fire a taxonomy event, stop and raise `spgr-escalate` with the precise list of unmapped events and missing inputs. Do not invent a firing location to close the gap.
2. For each event in the taxonomy, pick the firing layer. Prefer server-side (an API handler) over client-side for critical conversion events (signup, purchase, subscription), because server-side firing is not lost to ad blockers, client JavaScript errors, or dropped network requests. Record the layer choice and its reason.
3. Pin the exact code location per event: the file path and the function or component name where the event fires. Resolve the location against the real architecture, not a guess.
4. State the trigger condition as the precise state or callback, not the user intent. Fire `signup_completed` when the user record is successfully persisted, not when the submit button is clicked. If a button-click moment carries separate meaning, it is a separate event in the taxonomy, not a reinterpretation of this one. If the trigger you need has no corresponding event in the taxonomy, escalate rather than overloading an existing event.
5. Resolve every property to a concrete source. A property entry names the exact variable, API response field, or context value, for example `plan_id` from the `subscriptions.current_plan_id` column of the just-created subscription record. A vague resolution like "include the user's plan" is not a spec and is a finding, not a default to accept.
6. State the test-coverage requirement per event: how a test verifies the event fires once, on the correct trigger, with each property resolved to its source. This requirement is what the CI coverage check measures against.
7. Write the CI coverage check as source with `spgr-write-file`. The check compares the taxonomy event set against the events fired in the test suite and reports every taxonomy event not yet tested. Verify it runs with `spgr-run-tests` or CI.
8. Write the instrumentation-spec artifact with `spgr-write-artifact`, calling `spgr-validate-artifact` inline before the write completes. Record consequential choices (server-side over client-side, separated button events, dropped vague properties) with `spgr-log-decision`, and version with `spgr-version-artifact`.

## Notes

- Output type: a spec envelope artifact (`instrumentation-spec`) plus a CI coverage-check source file. The `instrumentation-spec` content schema is not registered yet, so `spgr-validate-artifact` applies envelope-only validation (header, confidence map, decision log, version) for now. Still call it. The content schema is registered in a later increment.
- The trigger-precision rule (fire on the persisted state, not the click) and the concrete-property-resolution rule are hard rules. Treat a vague trigger or property source as a finding to resolve or escalate, not a value to fill with an assumption.
- This skill is a vertical consultant and gate. To have an instrumentation decision reflected in a developer agent's code or artifact, use `spgr-tag-vertical-agent`, not a direct edit. Notify a human gate only through `spgr-notify-human` when an unmapped critical event requires a judgment call.
