---
name: spgr-identify-bottleneck
description: Produce a bottleneck-analysis report that locates the single performance constraint worth fixing now from profiling data, traces, slow query logs, and saturation metrics, ranked by Theory-of-Constraints priority. Use when the Performance Agent must find the one constraint to fix before any optimization work begins.
---

# identify-bottleneck

## Purpose

Find the one performance constraint worth fixing now, with evidence, before any optimization is attempted. Optimization without bottleneck identification is speculation. The only change that matters is the one that removes the current constraint, the thing that, once removed, lets the system handle more load or respond faster. Spreading effort across ten changes that each shave two percent is the failure this skill exists to prevent. Work top-down from where the user's time actually goes, separate code-logic constraints from resource saturation, and name a single bottleneck per analysis so the later optimization's effect can be attributed cleanly.

This is a Performance vertical skill. Operate as a consultant when a horizontal agent tags the Performance Agent to diagnose a slowdown, and as an auditor on a scheduled performance sweep. The report is a recommendation, not a code change. When a fix touches another agent's artifact (an API spec, an ADR, a migration), route the recommendation through spgr-tag-vertical-agent rather than editing that artifact directly.

## Inputs

| Field | Description |
|-------|-------------|
| `symptoms` | Performance symptoms: latency percentile data, throughput measurements, user-reported slowness |
| `observability_data` | Distributed traces, APM data, slow query logs |
| `infra_metrics` | CPU, memory, disk I/O, network I/O, connection pool utilization |
| `profiling_output` | Flamegraph, CPU profile, heap profile, or continuous-profiling capture (Parca, Polar Signals, Pyroscope) |
| `known_bottlenecks` | Optional list of other identified bottlenecks, for relative priority ranking |

Read source, trace, and metric files with spgr-read-file. Consume any upstream artifact (for example an NFR carrying the latency budget) with spgr-read-artifact.

## Outputs

| Artifact | Description |
|----------|-------------|
| `bottleneck-analysis` | Envelope report naming the single bottleneck, its evidence, root-cause classification, recommended optimization with expected impact, and its Theory-of-Constraints priority against other known bottlenecks |

Write the report with spgr-write-artifact. Each finding carries the named location (for example `PostgreSQL query at UserRepository.findByEmail:47 scanning without index`), the evidence excerpt (trace span, flamegraph annotation, query-plan fragment), the root-cause class (query plan, N+1, resource saturation, inefficient algorithm, lock contention), the recommended optimization, the expected impact, and a confidence signal.

## Procedure

1. Start at the top. Use the distributed traces to find the slow span that owns the user's time before reading any code. A 200ms query is not the bottleneck if it runs inside a loop that fires 500 times per request. Locate where the time goes, then descend.
2. Check resource saturation independently of code. Read `infra_metrics` to decide whether the constraint is the code logic or a saturated resource (for example a CPU-bound database while the code path is fine). Infrastructure metrics separate these two cases, so do not classify a code root cause until saturation is ruled out.
3. Confirm the constraint against profiling data. Prefer a continuous-profiling capture when available so the finding is data-driven rather than inferred. Annotate the flamegraph or profile span that proves the constraint.
4. Classify one root cause per finding from the fixed set: query plan, N+1, resource saturation, inefficient algorithm, lock contention.
5. Recommend the optimization and state its expected impact against the symptom (for example "adds index on `users.email`, expected p95 from 210ms to under 20ms").
6. Rank by Theory of Constraints. Name the single bottleneck to fix first relative to `known_bottlenecks`. Do not list ten parallel optimizations. One bottleneck at a time keeps the later improvement attributable to one change.
7. Validate and write. Call spgr-write-artifact with inline spgr-validate-artifact. Record the diagnostic reasoning and the rejected alternatives with spgr-log-decision.
8. Escalate rather than guess. If the trace, profiling, and metric data are absent or contradict each other and the constraint cannot be located from evidence, do not infer a bottleneck. Raise the gap with spgr-escalate, listing exactly which signal is missing (no traces, no profile, saturation and code data disagree). When the recommended fix would change another agent's confirmed artifact, route the recommendation through spgr-tag-vertical-agent instead of editing it.

## Notes

- Output type is an audit/review report, written as an envelope artifact via spgr-write-artifact. The `bottleneck-analysis` content schema is not yet in the registry, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, version checked). The content schema is registered in a later increment.
- Identify one bottleneck per report. A second distinct constraint is a second analysis, run after the first fix is measured.
- The report recommends and does not implement. The Performance Agent's optimization, caching, and query-plan skills act on this report's named bottleneck.
