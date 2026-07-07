---
name: spgr-write-async-job-spec
description: Produce an async-job-spec artifact that specifies one background job before it is built, covering trigger, payload schema, idempotency, retry cap with dead letter queue, SLA targets, and required metrics. Use when the Async Infrastructure Agent must specify a job ahead of implementation, or a backend or QA agent needs the job contract settled.
---

# write-async-job-spec

## Purpose

Specify one background job in full before any worker code exists. Background jobs are routinely the most under-specified part of an application, written quickly because a developer "just needs to run something in the background" without settling retry behavior, idempotency, failure routing, or observability. Jobs that fail silently, retry forever on a permanent error, or run blind become operational liabilities. This skill produces the async-job-spec envelope artifact that fixes those properties up front, so the worker is built against a confirmed contract rather than improvised.

The Async Infrastructure Agent owns this skill and operates as a vertical specialist. Its recommendations to a horizontal agent (for example the backend developer who will implement the worker) flow through a registered consultation via spgr-tag-vertical-agent, not by editing the other agent's artifact directly.

## Inputs

| Field | Description |
|-------|-------------|
| `business_requirement` | What the job must accomplish |
| `trigger_mechanism` | Queue message, scheduled cron, or event, with the source and payload shape |
| `data_dependencies` | What data the job reads and what it writes |
| `sla_requirements` | How long the job may take and what happens if it is delayed |

Read each upstream input with spgr-read-file for raw sources or spgr-read-artifact for stored artifacts.

## Outputs

| Artifact | Description |
|----------|-------------|
| `async-job-spec` | Envelope artifact specifying one background job: name and purpose, trigger with source and payload schema, ordered processing steps, idempotency strategy, failure handling, SLA, observability metrics, and concurrency constraints |

Write the artifact with spgr-write-artifact and validate it inline with spgr-validate-artifact.

## Procedure

1. Confirm the four inputs are present and non-contradictory. If the trigger source, payload shape, data dependencies, or SLA is missing or conflicts with another input, stop and raise spgr-escalate with the precise list of what is missing. Do not fill the gap with an assumed value.
2. State the job name and a one-sentence purpose. The name is lowercase-kebab and unique within the job registry.
3. Specify the trigger. Name the type (queue message, cron schedule, or event), the trigger source, and the payload schema with field types and required-or-optional per field.
4. List the processing steps in execution order.
5. Define the idempotency strategy. Determine whether the operation is naturally idempotent (setting a value to X) or not (incrementing a counter). For non-idempotent work, specify an explicit idempotency key and the check that prevents double effect. Idempotency is the load-bearing property. The same payload processed twice must produce the same result as processing it once. If idempotency cannot be guaranteed from the inputs, escalate rather than ship a job that can double-apply.
6. Define failure handling. Classify errors as retryable (transient external failure, network timeout, temporary resource contention) or non-retryable (invalid payload, permanently deleted resource, authorization failure). Set a finite maximum retry count, a backoff strategy, and a dead letter queue for exhausted or non-retryable failures. A spec with no DLQ or an unbounded retry count is incomplete, so do not finalize it.
7. Set the SLA: expected processing time at p50 and p95, and the maximum acceptable latency before alerting.
8. Define observability. List the metrics the job must emit, at minimum enqueue rate, processing duration, failure rate, and DLQ depth. These metrics are generated from the spec by the job framework, so name them precisely against the SLA and observability targets.
9. State the concurrency constraints: whether multiple instances may run in parallel and the maximum number of concurrent workers.
10. Record each consequential choice (idempotency approach, retry cap, backoff, concurrency limit) with spgr-log-decision, capturing the rationale and alternatives.
11. Write the artifact with spgr-write-artifact and run spgr-validate-artifact inline. If validation fails, correct the artifact and re-validate before returning.
12. Where the job's behavior constrains another agent's work (for example a worker implementation or an observability dashboard), route the recommendation through spgr-tag-vertical-agent as a consultation rather than editing that agent's artifact.

## Notes

- Output type is an envelope artifact (a spec). The `async-job-spec` content schema is not registered yet, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, version), and the content schema is registered in a later increment. Still call spgr-validate-artifact.
- Registered content-schema types are listed in the schema registry. Reference the registry rather than inlining field lists.
- Version every revision with spgr-version-artifact. A scope change to a confirmed spec is a human gate, so surface it with spgr-notify-human rather than revising silently.
- Mark each field in the confidence map as confirmed, proposed, or needs-human-input. An idempotency strategy that cannot be confirmed from the inputs is needs-human-input, not a guess.
