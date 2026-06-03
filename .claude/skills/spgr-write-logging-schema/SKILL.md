---
name: spgr-write-logging-schema
description: Produce a logging-schema artifact that defines the structured log fields, types, semantic conventions, level meanings, prohibited-field list, and sampling rules that every service must follow, plus a CI validation test that emits sample log entries and checks them against the schema. Use when the Observability Agent sets the shared log contract before services begin emitting logs, or when a new service, compliance constraint, or observability platform forces the schema to be re-issued.
---

# write-logging-schema

## Purpose

Define one shared structured-log schema so logs are consistent across every service, machine-parseable, and correlatable with traces. Unstructured or per-service log formats make every incident investigation start by learning a new format, and they cannot be traced, alerted on, or queried at scale. This skill produces the logging-schema envelope artifact that all log statements conform to, and stands up a CI test that catches schema drift before deployment. The Observability Agent owns this artifact as a vertical. It advises horizontal agents on log-field decisions through a consultation rather than editing their artifacts directly.

## Inputs

| Field | Description |
|-------|-------------|
| `service-topology` | The services that will emit logs, so the schema covers every emitter |
| `compliance-constraints` | Fields that must never appear in logs (PII, credentials, PHI, payment card data), drawn from the data-classification and retention artifacts |
| `observability-platform` | The log aggregation target (Datadog, Grafana Loki, CloudWatch, and so on), which sets the JSON shape and field conventions |

## Outputs

| Artifact | Description |
|----------|-------------|
| `logging-schema` | Envelope artifact defining required fields, context fields, per-event-type fields, prohibited fields, log-level semantics, and sampling rules |
| Schema validation test | Source-code CI test that emits sample log entries and asserts them against the schema, written via `spgr-write-file` and run by `spgr-run-tests` |

## Procedure

1. Read the service topology, compliance constraints, and platform target with `spgr-read-file`, and read any upstream data-classification or retention artifacts with `spgr-read-artifact` to get the authoritative prohibited-field list.
2. Define the required fields present on every log entry: `timestamp`, `level`, `service`, `trace_id`, `span_id`, `request_id`, `message`. Every entry carries `trace_id` and `span_id` from the distributed trace context, because without them logs cannot be correlated with traces in a multi-service architecture.
3. Define the context fields: `user_id`, `tenant_id`, `environment`, `version`. Specify `user_id` as a non-reversible opaque identifier (hash), never the raw user ID or email address.
4. Define event-specific fields per log event type (HTTP request, background job, error), with field name, type, and whether the field is required for that event type.
5. List prohibited fields explicitly (PII, credentials, raw passwords, payment card data). State that this list is enforced by log sanitization middleware, not by convention, so the prohibition is a hard rule and not a suggestion.
6. Define log-level semantics: ERROR requires action, WARN may require action, INFO is normal behavior, DEBUG is for diagnosis only and is disabled in production.
7. Define sampling rules: sample DEBUG logs at one percent in production, and never sample ERROR logs.
8. State that production output is JSON, not human-readable formatted strings, because aggregation systems parse JSON and do not parse freeform text.
9. Write the schema validation test with `spgr-write-file`: it emits one sample log entry per event type and asserts each against the schema, including a negative case that a prohibited field is rejected. Run it with `spgr-run-tests` so a schema violation fails CI before deployment.
10. Write the artifact with `spgr-write-artifact` and call `spgr-validate-artifact` inline before the write completes. Record each consequential choice with `spgr-log-decision` and stamp the version with `spgr-version-artifact`.
11. If the prohibited-field list is missing, the compliance constraints are absent, or the service topology omits an emitter the schema must cover, stop and raise `spgr-escalate` with the precise list of what is missing rather than inferring the prohibited set. Do not fill gaps with assumptions.

## Notes

- Output types: `logging-schema` is an envelope artifact and the validation test is source or config output. The `logging-schema` content schema is registered in a later increment, so `spgr-validate-artifact` applies envelope-only validation for now (header, confidence map, decision log, version).
- When a horizontal agent reaches a log-field decision in this vertical's domain, route the recommendation through a consultation with `spgr-tag-vertical-agent` rather than editing the other agent's artifact.
- Reference the prohibited-field list against the data-classification artifact rather than restating sensitive-data definitions here.
- Use confidence signals on each section: confirmed, proposed, or needs-human-input. Mark any field set that depends on unresolved compliance input as needs-human-input.
