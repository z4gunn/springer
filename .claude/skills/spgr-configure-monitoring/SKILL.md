---
name: spgr-configure-monitoring
description: Configure metrics collection, health-check endpoints, and operational dashboards as version-controlled config so the system's operational state is continuously visible, writing the source files via spgr-write-file and verifying them in CI. Use when the DevOps Agent must stand up monitoring infrastructure for a service before alerting can be wired, or when the Observability Agent needs golden-signal and SLO burn-rate dashboards built from confirmed metric definitions and an SLO spec.
---

# configure-monitoring

## Purpose

Stand up the monitoring layer that alerting depends on. Before an alert can fire, the signal it watches must be collected, retained, and visible. This skill writes health-check endpoint config, metrics instrumentation wiring, and dashboards as configuration-as-code so the system's operational state is observable. It produces source and config files, not an envelope spec, so write through spgr-write-file and prove it with CI rather than describing it.

This skill consumes the Observability Agent's metric definitions and SLO spec. It does not invent metrics or thresholds. Where a metric or threshold is missing, escalate rather than guess. The Observability Agent owns those artifacts and reaches the DevOps Agent through a consultation, not a direct edit.

## Inputs

| Field | Description |
|-------|-------------|
| `metric-definitions` | Confirmed metric set from the Observability Agent (read via spgr-read-artifact). Names, types, units, and bounded label dimensions. |
| `slo-spec` | SLO thresholds defining healthy, degraded, and breached, plus error budget windows (read via spgr-read-artifact). |
| `tech-stack-decision` | Instrumentation libraries and monitoring platform in use (Prometheus, OpenTelemetry, Grafana, or platform equivalent). |
| `service-topology` | Which services expose which endpoints, from the system diagram or infrastructure diagram. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Health-check config | A liveness probe and a separate readiness probe per service, each returning a machine-readable status. |
| Instrumentation wiring | Scrape config, collector config, or platform equivalent that ingests the defined metrics. |
| Dashboard definitions | One operational dashboard per service covering the four golden signals, plus an SLO burn-rate dashboard per service. |
| Platform config | Data retention, cardinality limits, and rollup rules for the monitoring platform. |

All written via spgr-write-file under version control alongside application code. None of these are envelope artifacts.

## Procedure

1. Read the inputs. Pull `metric-definitions` and `slo-spec` via spgr-read-artifact, and the tech stack and topology via spgr-read-artifact or spgr-read-file. Confirm the platform and instrumentation libraries before writing any config.

2. Validate the inputs before building. If a metric a dashboard needs is undefined, if an SLO threshold is missing for a service on the critical path, or if a metric definition carries an unbounded label dimension (user IDs, request IDs, or other high-cardinality values), stop and raise spgr-escalate to the Observability Agent. Do not fill the gap with an assumed metric or threshold. Record the resolution path through a consultation via spgr-tag-vertical-agent rather than editing the metric-definitions or slo-spec artifact directly.

3. Write a liveness probe and a separate readiness probe for each service via spgr-write-file. Keep the two concerns distinct: liveness reports that the process is alive, readiness reports that it can serve traffic. Each returns a machine-readable status at `/health` or the platform equivalent.

4. Write the instrumentation wiring via spgr-write-file. Ingest exactly the metrics in `metric-definitions`. Enforce bounded label values in the scrape or collector config. Set cardinality limits, retention, and rollup rules in the platform config.

5. Write one operational dashboard per service via spgr-write-file, covering the four golden signals of latency, traffic, errors, and saturation as the baseline. Additional signals are additive and do not replace the four. Dashboards are configuration-as-code (Grafana JSON, Terraform, or equivalent) and ship through the same CD pipeline as application code.

6. Write an SLO burn-rate dashboard per service via spgr-write-file, derived from `slo-spec`. Surface error budget burn rate, which is more actionable for on-call engineers than raw error rate.

7. Annotate dashboards with deployment markers from the feature flag system so feature rollouts appear inline on the timeline. Where the flag-system integration point is not yet defined, raise a consultation to the Feature Flag vertical via spgr-tag-vertical-agent rather than hardcoding an endpoint.

8. Verify. Run the monitoring config through CI via spgr-run-tests or the project lint and validation pipeline. Confirm every health endpoint responds, every defined metric is scraped, and every dashboard renders against its data source. Record the configuration choices with spgr-log-decision. On a CI failure, fix the config and re-run before handing off.

## Notes

- Output type is source and config, not an envelope artifact. Write files via spgr-write-file and verify with CI, per the Springer source-output contract. There is no registered content schema to validate against, because this skill emits config files rather than a typed artifact.
- This skill is a DevOps deliverable advised by the Observability vertical. The Observability Agent's recommendations on metric coverage and thresholds arrive through a consultation registered via spgr-tag-vertical-agent, not as edits to this skill's output.
- Health checks must separate liveness from readiness. Dashboards must carry the four golden signals as a baseline. Metric labels must be bounded. These three rules are non-negotiable.
