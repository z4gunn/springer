---
name: spgr-audit-async-coverage
description: Produce an async-coverage audit report that checks every background job, webhook delivery, email send, and event consumer against the async job spec registry for retry, DLQ, and observability coverage, returning a PASS or GATE verdict that blocks release on any unguarded async process. Use when the Async Infrastructure Agent must confirm a release.
---

# audit-async-coverage

## Purpose

Async infrastructure fails silently by default. A background job that fails leaves a task undone with no user-visible error and no alert. A webhook delivery that fails with no dead letter queue loses the event permanently. A job with no observability is invisible to the on-call team. This audit makes the safety nets a reviewable property of the system rather than an assumption, so every async process fails loudly and recovers correctly.

This skill operates the Async Infrastructure Agent in auditor and gate mode. The audit is code-level. It compares the actual job code against the async job spec registry, not the registry alone. It covers all async process kinds because each has different retry semantics but all need the same safety nets. It sets a blocking threshold. A job with no DLQ, or an infinite-retry job, on a critical path is a release blocker.

## Inputs

| Field | Description |
|-------|-------------|
| `async-job-spec-registry` | The registry of all defined background jobs, scheduled jobs, webhooks, email sends, and event consumers, with intended retry, DLQ, and observability per process. Read with spgr-read-artifact. |
| `job-queue-config` | The queue configuration carrying retry settings and DLQ bindings. Read with spgr-read-file. |
| `observability-config` | The configuration naming which jobs emit metrics and which have alerts. Read with spgr-read-artifact or spgr-read-file. |
| `async-job-code` | Source for every background job, scheduled job, webhook delivery, email send, and event consumer, for the implementation-versus-spec comparison. Located with spgr-search-codebase and read with spgr-read-file. |
| `release-scope` | Optional. The set of async processes in the pending release, used to scope the gate verdict to what is shipping. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `async-coverage` | Audit report envelope artifact written via spgr-write-artifact. Carries a per-process row (spec exists yes or no, DLQ configured yes or no, retry configured correctly yes or no, observability instrumented yes or no), processes in the codebase but not in the registry, gaps by severity, the blocking gaps, a per-job DLQ-depth monitoring recommendation, and a PASS or GATE verdict. |

## Procedure

1. Read the inputs. Load the async job spec registry and observability config with spgr-read-artifact, and the job queue config with spgr-read-file. If the registry is missing, stop and raise spgr-escalate with the precise list of what is absent. Do not infer intended retry or DLQ behavior from habit when the registry is the source of truth.

2. Enumerate every async process in the codebase. Use spgr-search-codebase to find all background jobs, scheduled jobs, webhook delivery sites, email sends, and event consumers. Record each one. Flag each process critical-path or not per the registry classification.

3. Reconcile code against the registry. List every async process found in the codebase that has no entry in the spec registry. An unregistered process is a coverage gap, since it has no defined retry, DLQ, or observability intent. Record spec exists yes or no per process.

4. Audit each process at the code and config level. For each process record four cells. Spec exists yes or no from step 3. DLQ configured yes or no, where a process with no DLQ binding silently discards failed work and is the most dangerous gap. Retry configured correctly yes or no, where no max retry count (infinite retry) is a no, and a finite retry count with a bound DLQ is a yes. Observability instrumented yes or no, where a process emitting no metrics and having no alert is a no.

5. Classify gaps by severity and fix-priority order. A missing DLQ (failed jobs silently discarded) is high priority. Infinite retry with no max count is high priority, since a permanently failing job runs forever and consumes queue capacity and worker threads. Treat a process that has both infinite retry and no DLQ as the top fix. Missing observability (no metrics, no alerts) is medium priority. Every job must have both a finite retry count and a DLQ.

6. Add the DLQ-depth monitoring recommendation. For each job, recommend a DLQ-depth monitor, since DLQ depth is a leading indicator of systemic failure. A DLQ that fills signals a class of jobs failing consistently and needing investigation. Route this as a dashboard recommendation, not a code edit.

7. Set the verdict. The blocking threshold is any async process on a critical path that has no DLQ or has infinite retry (no max count). If `release-scope` is supplied, score the verdict against only the processes in scope. The verdict is GATE if any blocking gap exists, otherwise PASS.

8. Write and validate the report. Write the `async-coverage` artifact via spgr-write-artifact with inline spgr-validate-artifact. Record the verdict rationale and the blocking-threshold process with spgr-log-decision.

9. Route remediation, do not patch other artifacts. For each gap owned by another agent (a backend developer job site, a DevOps queue or dashboard config, an architecture pattern decision), route the recommendation through a consultation with spgr-tag-vertical-agent rather than editing that agent's artifact or code directly. On a GATE verdict for a pending release, surface the decision to the human gate with spgr-notify-human.

## Notes

- Output type is an audit report (envelope artifact). Its content schema is registered in a later increment, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, version).
- Blocking threshold: any critical-path async process with no DLQ, or with infinite retry (no max count), yields a GATE verdict. Missing observability and non-critical-path gaps are reported but do not gate.
- Fix-priority order for reported gaps is DLQ, then finite retry count, then observability. A process with both infinite retry and no DLQ is the top fix, since failures are discarded while the job runs forever.
- This audit reads and reports only. It does not bind DLQs, set retry counts, or wire metrics. Recommendations to other agents flow through spgr-tag-vertical-agent.
