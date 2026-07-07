---
name: spgr-write-performance-budget
description: Produce a performance-budget artifact that sets pass/fail latency and throughput thresholds for each critical user journey, with a regression threshold and a CI benchmark gate that enforces it. Use when the Performance Agent must replace subjective speed judgments with measurable thresholds before load tests, SLOs, or release gating are written.
---

# write-performance-budget

## Purpose

Set the numbers that define "fast enough" and the numbers that define a release-blocking regression. Without a budget, performance is a subjective call that drifts between conversations. This artifact fixes specific, measurable thresholds per critical journey, derived from user-experience research (perceived instant under 100ms, noticeable delay over 300ms, attention loss over 1s) and the product's competitive context, not from engineering convenience. The budget is the pass/fail criterion for load tests and the latency input for SLO definitions, so its thresholds must be testable, not aspirational.

## Inputs

| Field | Description |
|-------|-------------|
| `critical-user-journeys` | The 5 to 10 most important user journeys from the product spec. The budget covers these critical paths, not every endpoint in the system. |
| `product-context` | Whether this is a consumer app, an internal tool, a real-time feature, and any latency-tolerance signal it carries. A B2B dashboard tolerates more latency than a consumer mobile app, and a trading platform tolerates almost none. |
| `infrastructure-constraints` | Target infrastructure tier and expected scale, which bound what thresholds the system can realistically meet. |
| `competitive-benchmarks` | Known competitor performance figures, where available, used to set thresholds against market expectation. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `performance-budget` | Thresholds per critical journey for API response time (p50, p95, p99) per endpoint category, web page load (Time to First Byte, Largest Contentful Paint, First Input Delay), mobile frame rate (60 fps sustained, no jank on scroll or animation), database query time (p95 per read, write, and complex-query category), and background job completion time per job type. Includes a regression threshold (when a metric exceeds budget by X percent it is a blocking issue) and a CI benchmark-gate definition that runs the benchmark suite on every PR and fails on any over-budget metric. |

## Procedure

1. Read the inputs with spgr-read-artifact. Confirm the critical user journeys are named and the product context states the latency-tolerance class. If journeys are missing, unranked, or there is no way to derive a tolerance class, stop and raise spgr-escalate with a precise list of what is missing rather than guessing thresholds.
2. Select the critical paths. Budget the 5 to 10 most important journeys only. Do not attempt to budget every endpoint. If the input lists far more than that without a priority order, escalate to the PM or Performance Agent owner for a ranked critical-path set.
3. Set the threshold class from product context before setting numbers. A consumer or real-time surface gets tight thresholds, an internal tool gets looser ones. Anchor each number to user-experience research and, where available, to the competitive benchmarks. Record the tolerance class so every threshold below inherits a stated rationale.
4. For each journey, set API response-time thresholds at p50, p95, and p99 per endpoint category. State the category (read, write, complex query, search, and so on), not a single global number.
5. For each web surface in scope, set page-load thresholds for Time to First Byte, Largest Contentful Paint, and First Input Delay.
6. For each mobile surface in scope, set the frame-rate target (60 fps sustained) and the no-jank requirement on scroll and animation.
7. Set database query-time thresholds at p95 per query category (read, write, complex query), and background job completion-time thresholds per job type.
8. Set the regression threshold: the percentage by which any budgeted metric may move before the regression is a blocking issue. State it as one rule that applies across the budget so CI can enforce it without per-metric ambiguity.
9. Check each threshold against the infrastructure constraints. If a user-expectation threshold cannot be met on the target infrastructure tier at the expected scale, do not silently relax it. Record the conflict and raise spgr-escalate to the architecture owner, because the resolution is an architecture or scale decision, not a budget decision.
10. Define the CI enforcement gate as part of the artifact: a performance benchmark suite that runs on every PR and fails the build when any metric regresses past the regression threshold. State which metrics the suite measures and the fail condition, so the DevOps owner can wire it.
11. Record consequential choices with spgr-log-decision, in particular the tolerance class, any threshold set against a competitive benchmark, and the regression-threshold percentage.
12. Before finalizing thresholds that another agent will be held to, route the budget to the consuming horizontal agents through spgr-tag-vertical-agent rather than editing their artifacts. The p95 API thresholds feed the SLO spec and the load-test plan, so flag those handoffs in the consultation.
13. Write the artifact with spgr-write-artifact, then confirm it with spgr-validate-artifact. If validation fails or any input is missing or contradictory, raise spgr-escalate with the exact gap rather than filling it with an assumption.

## Notes

- This is an envelope artifact (a performance spec). Write it through spgr-write-artifact and validate inline with spgr-validate-artifact. The performance-budget type is not yet in the schema registry at `schemas/`, so envelope-only validation applies (header, confidence map, decision log, version) until a content schema is registered.
- This skill produces the budget only. It does not write the load-test plan and it does not write the SLO spec. It supplies the p95 latency thresholds those artifacts consume, routed through a consultation, not a direct edit.
- A threshold is confirmable only if it is testable against the target infrastructure. A number the system cannot meet at the expected scale is not a budget, it is a defect waiting to be filed, and it must be escalated to architecture instead of written.
