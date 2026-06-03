---
name: spgr-write-metric-definitions
description: Produce a metric-definitions artifact that specifies every application metric the system must emit (name, type, labels, unit, description, recording rule) under bounded-cardinality and consistent-naming rules, then generate OpenTelemetry instrumentation stubs so application code cannot drift from the spec. Use when the Observability Agent has a service topology and the four golden signals per service and must define the metric contract before instrumentation begins, or when the DevOps Agent needs the metric definitions to configure monitoring infrastructure.
---

# write-metric-definitions

## Purpose

Define the metric contract between application code and observability infrastructure. When two services emit a metric under the same name but with different label cardinalities or semantic meaning, aggregations produce garbage, and when a metric is named inconsistently across services, dashboards need per-service logic instead of fleet-wide views. Writing the definitions before any instrumentation prevents both, and generating instrumentation stubs from the definitions keeps the implementation aligned with the spec.

This skill operates as a consultant and gate for the Observability vertical. It produces the metric-definitions envelope artifact and the matching stub source files. It does not edit another agent's artifact. Where a horizontal agent needs a metric decision reflected in its own artifact, route the recommendation through `spgr-tag-vertical-agent`.

## Inputs

| Field | Description |
|-------|-------------|
| `service-topology` | The services in the system and their relationships, read with `spgr-read-artifact` or `spgr-read-file`. |
| `slo-targets` | SLO targets, so every metric that drives an SLO is explicitly defined. Read with `spgr-read-artifact`. |
| `golden-signals` | The four golden signals per service: latency, traffic, errors, saturation. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `metric-definitions` | Envelope artifact listing each metric with name, type, description, labels, unit, and optional recording rule. Written with `spgr-write-artifact` and validated inline with `spgr-validate-artifact`. |
| OpenTelemetry stubs | One named instrument per defined metric, written as source files with `spgr-write-file` and verified by `spgr-run-tests` or CI. |

## Procedure

1. Read the service topology, SLO targets, and golden signals with `spgr-read-artifact` and `spgr-read-file`. If any input is missing or contradictory, for example an SLO target that names a metric the topology cannot source, stop and raise `spgr-escalate` with the precise list of what is missing. Do not invent metrics to fill the gap.
2. For each service, enumerate metrics that cover all four golden signals (latency, traffic, errors, saturation), plus every metric an SLO target depends on. A service missing a golden signal is a finding, not a default to silence.
3. Name each metric under the Prometheus convention. Use `<namespace>_<metric_name>_<unit>_total` for counters, `<namespace>_<metric_name>_<unit>` for gauges, and `<namespace>_<metric_name>_<unit>_bucket` for histograms. Keep the segment order consistent across services so fleet-wide aggregation works.
4. Set the type per metric. Use a histogram, not a summary, for latency, because histograms aggregate correctly across instances and summaries do not. Use a counter for monotonic counts, a gauge for point-in-time values.
5. Assign labels and verify each label is cardinality-bounded, meaning its value set is finite and enumerable (status_code, method, endpoint_group). Reject any unbounded label (user_id, request_id, trace_id). A high-cardinality label on a metric is a blocking error, not a warning. If an input implies one, escalate with `spgr-escalate` rather than emitting it.
6. State an explicit unit per metric (milliseconds, bytes, requests) and a plain-English description of what it measures. Add a recording rule only where a raw metric needs a pre-computed rollup for dashboard performance.
7. Generate one OpenTelemetry instrument per defined metric and write the stub source files with `spgr-write-file`. Verify the stubs compile and pass with `spgr-run-tests` or CI.
8. Write the metric-definitions artifact with `spgr-write-artifact`, calling `spgr-validate-artifact` inline before the write completes. Record the consequential choices (type selection, dropped labels, recording rules) with `spgr-log-decision`, and version with `spgr-version-artifact`.

## Notes

- Output type: a spec envelope artifact (`metric-definitions`) plus OpenTelemetry source stubs. The `metric-definitions` content schema is not registered yet, so `spgr-validate-artifact` applies envelope-only validation (header, confidence map, decision log, version) for now. Still call it. The content schema is registered in a later increment.
- Bounded label cardinality and the histogram-over-summary rule for latency are hard rules. Treat a violation as a blocking error and escalate rather than emitting a non-conforming metric.
- This skill is a vertical consultant and gate. To have a metric decision reflected in a horizontal agent's artifact, use `spgr-tag-vertical-agent`, not a direct edit. Notify a human gate only through `spgr-notify-human` when a definition conflict requires a judgment call.
