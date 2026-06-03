---
name: spgr-write-slo-spec
description: Produce an slo-spec artifact that sets the system's Service Level Objectives, each with an SLI, a target threshold, a measurement window, the derived error budget, and the multi-burn-rate alert windows, plus an error-budget-burn dashboard definition. Use when the Observability Agent has a performance budget and service criticality and must commit reliability targets before alerting is designed, or when a service's reliability targets must be revised after maturity data arrives.
---

# write-slo-spec

## Purpose

Define the reliability targets the system commits to keep. An slo-spec converts "the system should be reliable" into a measurable commitment with operational consequences: it names what is measured (the SLI), the acceptable threshold (the SLO target), the window over which it is judged, the error budget the target implies, and the alert windows derived from that budget. The slo-spec is the foundation that alert design depends on, so an alert that does not connect to budget burn has no SLO to justify it.

The Observability Agent owns this skill and operates as a vertical consultant and gate. It writes the slo-spec as an envelope artifact. It does not edit the performance budget or any alerting config directly. A reliability recommendation that changes another agent's artifact section flows through a consultation via spgr-tag-vertical-agent.

## Inputs

| Field | Description |
|-------|-------------|
| `performance-budget` | Latency budgets that seed the latency SLO targets. Read via spgr-read-artifact. |
| `service-criticality` | User-facing criticality per service, which sets the availability target. |
| `historical-reliability` | Past reliability data if available, used to set achievable targets. |
| `business-context` | The reliability level that is commercially necessary, distinct from aspirational. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `slo-spec` | Envelope artifact carrying one entry per SLO, plus the error-budget-burn dashboard definition. Written via spgr-write-artifact with inline spgr-validate-artifact. |

Each SLO entry records the SLO name and owning service, the SLI (request success rate, latency p95 or p99, job completion rate), the SLO target threshold, the measurement window (28-day rolling for most SLOs), the derived error budget (100% minus target, for example 99.9% yields 43.2 minutes per month), and the multi-burn-rate alert windows (fast burn 1h over 5m, slow burn 6h over 30m).

## Procedure

1. Read the inputs. Pull latency budgets from the performance budget via spgr-read-artifact, and gather service criticality, any historical reliability data, and the business context. If the performance budget is missing for a latency SLO, or service criticality is undefined for a service that needs an availability SLO, stop and raise spgr-escalate with the precise list of missing inputs. Do not guess a target.

2. Set each SLO target from the user's experience, not engineering convenience. Choose a target the system can reliably achieve given historical data, and tighten it as the system matures. Do not set 99.99% for an MVP, that is aspirational rather than a target. When historical data contradicts the business context (the commercially necessary level is not yet achievable), surface the conflict via spgr-escalate rather than committing an unreachable target.

3. Choose the SLI per objective. Measure latency SLOs at p95 or p99, never p50, because p50 improves as caches warm while p95 reveals the tail behavior that affects the worst-experiencing users. Use request success rate for availability and job completion rate for async work.

4. Set the measurement window to 28-day rolling unless an input justifies otherwise, and record the reason for any deviation.

5. Derive the error budget arithmetically from the target (100% minus target over the window), and state it in both percentage and wall-clock terms. Frame the budget as the mechanism for negotiating reliability work against feature work, not as a punishment: a fully spent budget means reliability work takes priority that sprint.

6. Derive the multi-burn-rate alert windows from the error budget: a fast-burn pair (1h budget window, 5m alert window) and a slow-burn pair (6h budget window, 30m alert window). These windows are the input contract that the alerting config consumes downstream.

7. Define the error-budget-burn dashboard: a real-time view of how fast each SLO's budget is being consumed across all SLOs, so on-call sees an impending violation before it occurs. Specify the panels, the per-SLO burn-rate series, and the thresholds that map to the fast-burn and slow-burn alerts.

8. Log each consequential target choice with spgr-log-decision, capturing the decision, the rationale, the alternatives, and the downstream impact, so settled targets are not re-litigated.

9. Write the slo-spec via spgr-write-artifact, which runs spgr-validate-artifact inline before the write completes. On a validation failure, fix the reported issues and re-validate. Do not write a partial artifact.

10. Where the targets imply an amendment to a horizontal agent's artifact (for example a latency budget that must change in the performance budget), route the recommendation through spgr-tag-vertical-agent as a consultation rather than editing that artifact.

## Notes

- Output type is an envelope artifact (`slo-spec`). Its content schema is registered in a later increment, so envelope-only validation applies for now: spgr-validate-artifact still checks the header, confidence map, decision log, and version.
- Reference the artifact schema registry rather than restating field lists. Read inputs via spgr-read-artifact and write the output via spgr-write-artifact.
- Mark each SLO target with a confidence signal. A target backed by historical data is confirmed, a target set without reliability history is proposed, and a target blocked on a missing input is needs-human-input.
- On revision after maturity data, re-version through spgr-version-artifact.
