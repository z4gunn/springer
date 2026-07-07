---
name: spgr-audit-observability-coverage
description: Produce an observability-coverage audit report that checks every service against the metric definitions, logging schema, SLO spec, and alert runbooks, with a PASS or GATE verdict that blocks production release on any critical-path service lacking an SLO or alerting. Use when the Observability Agent must confirm a release is instrumented.
---

# audit-observability-coverage

## Purpose

Observability coverage erodes incrementally. A new service ships without metrics instrumentation, a background job is added without a completion metric, a new endpoint is not covered by the latency SLO. Each gap is small alone, but together they create blind spots that let incidents go undetected. Run this audit to make observability coverage a reviewable property of the system rather than an assumption.

This skill operates the Observability Agent in auditor and gate mode. It generates the coverage report automatically from the service registry, metric definitions, and SLO spec rather than from manual assembly, and it sets a blocking threshold. A critical-path, user-facing service with no SLO or no alerting is a production release blocker.

## Inputs

| Field | Description |
|-------|-------------|
| `service-topology` | The service registry listing every service that should be instrumented, with critical-path and user-facing flags. Read with spgr-read-file or spgr-read-artifact. |
| `metric-definitions` | The metric definitions document naming the required metrics per service class. |
| `logging-schema` | The logging schema spec naming the approved structured logging library and required fields. |
| `slo-spec` | The SLO spec listing targets per service and endpoint. |
| `alert-runbooks` | The alert runbook set mapping alerts to services and response procedures. |
| `release-scope` | Optional. The set of services in the pending release, used to scope the gate verdict to what is shipping. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `observability-coverage` | Audit report envelope artifact written via spgr-write-artifact. Carries a per-service coverage status across the four pillars (metrics, logging, SLO, alerting) as complete, partial, or missing, a gap list with owning agent and remediation path, the blocking gaps, and a PASS or GATE verdict. |

## Procedure

1. Read the inputs. Load the service topology with spgr-read-artifact (or spgr-read-file for a raw registry), then read the metric definitions, logging schema, SLO spec, and alert runbooks. If any input is missing or the topology has no services, stop and raise spgr-escalate with the precise list of what is absent. Do not infer coverage from an incomplete source set.

2. Build the service list. Enumerate every service that should be instrumented, including background jobs and async workers, not only HTTP services. Mark each service critical-path and user-facing per the topology flags, since those flags drive the blocking threshold.

3. Audit the metrics pillar per service. Confirm the service emits every metric its class requires from the metric definitions. Background jobs need a completion metric, a duration histogram, and a failure-rate metric, the same as HTTP services. Record complete, partial, or missing.

4. Audit the logging pillar per service at the code level. Confirm the service uses the approved structured logging library with the required schema fields. Treat ad-hoc freeform logging calls (for example `console.log` with a freeform string) as a coverage gap, not as compliant logging. Use spgr-search-codebase to locate logging call sites. Record complete, partial, or missing.

5. Audit the SLO pillar per service. Confirm an SLO is defined for the service and for each user-facing endpoint or job. A service with no SLO is a service whose user expectations cannot be measured. Record complete, partial, or missing.

6. Audit the alerting pillar per service. Confirm each SLO has a corresponding alert with a runbook. Record complete, partial, or missing.

7. Classify gaps and set the verdict. For every non-complete cell, write a gap entry with the service, the pillar, the specific missing element, the owning agent, and the remediation path. Apply the blocking threshold: any critical-path user-facing service that is missing an SLO or missing alerting is a release blocker. If `release-scope` is supplied, score the verdict against only the services in scope. The verdict is GATE if any blocking gap exists, otherwise PASS.

8. Write and validate the report. Write the `observability-coverage` artifact via spgr-write-artifact with inline spgr-validate-artifact. Record the verdict rationale and the blocking-threshold call with spgr-log-decision.

9. Route remediation, do not patch other artifacts. For each gap owned by another agent, route the recommendation through a consultation with spgr-tag-vertical-agent rather than editing that agent's artifact directly. On a GATE verdict for a pending release, surface the decision to the human gate with spgr-notify-human.

## Notes

- Output type is an audit report (envelope artifact). Its content schema is registered in a later increment, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, version).
- Blocking threshold: a critical-path user-facing service missing an SLO or alerting yields a GATE verdict for production traffic. Non-critical or non-user-facing gaps are reported but do not gate.
- This audit reads and reports only. It does not write metrics, logging, or SLO definitions. Recommendations to other agents flow through spgr-tag-vertical-agent.
