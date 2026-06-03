---
name: spgr-audit-instrumentation-coverage
description: Produce an instrumentation-coverage audit report that checks every event in the event taxonomy against the code that should fire it and against live analytics data, recording per-event whether it is implemented, missing, or partially implemented, whether its fire location matches the instrumentation spec, whether every required property is present and correctly sourced, and whether production volume matches expectation, then returns a PASS or GATE verdict that blocks release on any taxonomy event that never fires or fires without a required property. Use when the Analytics Agent must confirm a release is fully instrumented before launch, since coverage gaps found after launch cannot be backfilled, or when a continuous sweep needs the current instrumentation posture across the event taxonomy.
---

# audit-instrumentation-coverage

## Purpose

Instrumentation specifications describe intent. This audit verifies implementation. The gap between the two is where analytics debt lives: events that sit in the taxonomy but never fire, events that fire with a required property missing, and events that fire from the wrong trigger such as a button click instead of an API confirmation. The debt accumulates silently until someone runs a funnel analysis and discovers the dataset is incomplete.

Run this skill to operate the Analytics Agent in auditor and gate mode. Generate the coverage report from the event taxonomy, the instrumentation spec, the codebase, and live analytics data rather than from manual assembly, and set a blocking threshold. Coverage gaps found before launch are cheap to fix. The same gaps found after launch force a backfill decision that is usually not feasible, or an accepted hole in historical analysis. That asymmetry is why the gate exists.

## Inputs

| Field | Description |
|-------|-------------|
| `event-taxonomy` | The event taxonomy artifact listing every event the product should emit, each with its required properties. Read with spgr-read-artifact. |
| `instrumentation-spec` | The instrumentation spec naming, per event, the code location and trigger that should fire it and the source of each property. Read with spgr-read-artifact. |
| `codebase` | The application source, read to verify each event is fired from the location and trigger the spec names. Locate fire sites with spgr-search-codebase. |
| `analytics-data` | Production or staging analytics platform data, read to verify events arrive at expected volume and with required properties populated. |
| `release-scope` | Optional. The set of events or features in the pending release, used to scope the gate verdict to what is shipping. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `instrumentation-coverage` | Audit report envelope artifact written via spgr-write-artifact. Carries a per-event status of implemented, missing, or partially implemented, a fire-location verification against the spec, a property-coverage result, a volume sanity-check result, a gap list by severity with owning agent and remediation path, and a PASS or GATE verdict. |

## Procedure

1. Read the inputs. Load the event taxonomy and the instrumentation spec with spgr-read-artifact, then read the analytics data. If the taxonomy is empty, the instrumentation spec is absent, or no analytics data source is reachable, stop and raise spgr-escalate with the precise list of what is missing. Do not infer coverage from an incomplete source set, and do not treat a missing data source as a passing audit.

2. Build the event list. Enumerate every event in the taxonomy with its required properties and its spec-named fire location and trigger. This list is the audit baseline. An event present in code or data but absent from the taxonomy is itself a finding, since taxonomy and implementation have drifted.

3. Verify implementation per event. Use spgr-search-codebase to locate where each event fires. Record implemented when a fire site exists, missing when none exists, and partially implemented when a fire site exists but is incomplete. Confirm the fire location and trigger match the instrumentation spec. An event fired from the wrong trigger, for example on a button click rather than on the API confirmation the spec names, is a mis-fire and is recorded as partially implemented with the trigger discrepancy noted.

4. Verify property coverage per event. For each fired event, confirm every required property from the taxonomy is present and sourced from the field the spec names. A live event missing a required property is high severity, because the property cannot be retroactively added to historical data.

5. Run the volume sanity check per event. Compare the production or staging volume against the expected volume. An event that fires zero or near-zero times when it should fire at meaningful volume signals a code path that is never reached, a bug in the trigger condition, or an event removed from the code without updating the taxonomy. Record the expected-versus-actual volume and flag any event at or near zero.

6. Classify gaps and set the verdict. For every event that is not fully implemented, write a gap entry with the event, the gap kind (missing, mis-fired trigger, missing property, zero volume), the severity, the owning agent, and the remediation path. Apply the blocking threshold: any in-scope taxonomy event that never fires, or that fires without a required property, is a release blocker. A mis-fired trigger and a zero-volume regression on an expected high-volume event are also blocking. If `release-scope` is supplied, score the verdict against only the events in scope. The verdict is GATE if any blocking gap exists, otherwise PASS.

7. Write and validate the report. Write the `instrumentation-coverage` artifact via spgr-write-artifact with inline spgr-validate-artifact. Record the verdict rationale and the blocking-threshold call with spgr-log-decision. Version a re-run of the audit with spgr-version-artifact rather than overwriting the prior report.

8. Route remediation, do not patch other artifacts. For each gap owned by another agent, for example a missing fire site owned by a developer agent or a taxonomy correction owned by the PM, route the recommendation through a consultation with spgr-tag-vertical-agent rather than editing that agent's artifact directly. On a GATE verdict for a pending release, surface the decision to the human gate with spgr-notify-human.

## Notes

- Output type is an audit report (envelope artifact). Its content schema is registered in a later increment, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, version).
- Blocking threshold: an in-scope taxonomy event that never fires, fires without a required property, fires from the wrong trigger, or drops to zero volume when high volume is expected yields a GATE verdict. Out-of-scope or low-volume informational gaps are reported but do not gate.
- The launch asymmetry drives severity. A pre-launch gap is a cheap fix. A post-launch missing property is unrecoverable history, so live events missing a required property are always high severity.
- For continuous regression detection, register a monitor that alerts when an expected high-volume event drops to zero or near-zero for more than one hour, catching instrumentation regressions introduced by code changes before they reach analysis. The monitor reuses this audit's volume sanity check on a recurring schedule.
- This audit reads and reports only. It does not edit the taxonomy, the instrumentation spec, or application code. Recommendations to other agents flow through spgr-tag-vertical-agent.
