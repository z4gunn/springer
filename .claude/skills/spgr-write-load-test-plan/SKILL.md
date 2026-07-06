---
name: spgr-write-load-test-plan
description: Produce a load-test-plan artifact specifying the scenarios, load profiles, virtual-user models, and pass/fail criteria to verify the performance budget under expected and peak traffic, plus capacity planning for growth. Use when the Performance Agent must define the load test specification before a launch, scaling event, or feature spike.
---

# write-load-test-plan

## Purpose

Specify how the system will be load tested so the team learns where it degrades before a launch spike, a viral moment, or a feature announcement forces that discovery in production. This skill produces the plan, not the scripts. The performance budget supplies the pass/fail thresholds, and this plan maps each threshold to a concrete scenario and load profile. The QA Agent implements the scripts from the plan, so the plan must be precise enough to build from without further consultation.

As a vertical Performance artifact, the plan is consultant and gate input: it advises the QA and DevOps agents on what to run and observe, and its pass/fail criteria gate a release once the load test has been executed.

## Inputs

| Field | Description |
|-------|-------------|
| `performance-budget` | The confirmed performance budget artifact, read via spgr-read-artifact. Supplies the latency, throughput, and error-rate thresholds that become the pass/fail criteria. |
| `traffic-models` | Expected baseline load, expected peak, and the expected growth curve. |
| `critical-user-journeys` | The critical journeys from the product spec, the basis for realistic scenarios rather than endpoint hammering. |
| `infrastructure-baseline` | Current capacity and auto-scaling configuration, plus the staging environment sizing relative to production. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `load-test-plan` | Envelope artifact written via spgr-write-artifact, holding the test scenarios, load profiles, virtual-user model, pass/fail criteria, monitoring scope, results-analysis instructions, and capacity-planning analysis. |

## Procedure

1. Read the performance budget with spgr-read-artifact and confirm it is the confirmed version. The budget thresholds are the only source of pass/fail criteria. If the budget is missing, in proposed state, or has no thresholds for a critical journey, stop and call spgr-escalate rather than inventing a threshold.

2. Read the traffic models, critical user journeys, and infrastructure baseline via spgr-read-artifact or spgr-read-file. Confirm the staging environment mirrors production infrastructure sizing. If staging is under-provisioned relative to production, record this and call spgr-escalate, because results from an under-provisioned environment are not meaningful.

3. Write a test scenario for each critical user journey. A scenario simulates a full journey with realistic steps, for example login then dashboard load then search then view item. Do not write single-endpoint volume tests, those are load-generator tests and are out of scope for this plan.

4. Define the virtual-user model for each scenario: think time between steps, session length, and request distribution across the journey steps.

5. Define the load profiles, each mapped to a traffic model:
   - Baseline: expected baseline load.
   - Expected peak: the expected peak from the traffic models.
   - Stress: 2x expected peak, to find the degradation point.
   - Soak: sustained expected peak over 1 to 4 hours, to surface memory leaks and connection-pool exhaustion that short tests miss.

6. Map each pass/fail criterion directly to a performance budget threshold. State the failure condition explicitly, for example p95 latency exceeding the budget under expected peak load is a fail. Every criterion traces to a budget threshold, none are introduced here.

7. Define the infrastructure monitoring scope: what to observe during each run (latency percentiles, throughput, error rate, CPU, memory, connection pools, auto-scaling events).

8. Write the results-analysis instructions: how to read the output, which findings trigger optimization work, and how a fail routes back to the Performance Agent.

9. Add the capacity-planning analysis. From the load test results model, project the infrastructure investment required to handle 3x and 10x current traffic, in a form the product roadmap can consume for cost projection.

10. Validate the artifact inline with spgr-validate-artifact before the write completes. On any validation failure, fix the artifact and revalidate rather than writing a failing artifact. Record consequential choices with spgr-log-decision and version with spgr-version-artifact.

11. Route the plan to the QA Agent as a consultation via spgr-tag-vertical-agent rather than editing QA's test artifacts directly. The QA Agent implements the scripts from the plan.

## Notes

- Output type is an envelope artifact (load-test-plan), written via spgr-write-artifact. Its content schema is not yet registered, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, and version). The content schema is registered in a later increment.
- Pass/fail criteria are derived only from the confirmed performance budget. Do not introduce a threshold that is not in the budget.
- Scenarios model user journeys, not endpoint volume. Soak tests run sustained load for 1 to 4 hours. Load tests run against a staging environment that mirrors production sizing.
- A vertical recommendation to QA flows through spgr-tag-vertical-agent, not by editing QA's artifacts.
