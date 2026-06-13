---
name: spgr-scaffold-background-job
description: Generate the source-code scaffold for one background job from its async job spec, including the worker class, a typed message payload schema, a type-safe enqueue helper, retry and dead-letter configuration, observability instrumentation for the spec-defined metrics, and a unit test scaffold for the success, retryable-failure, and non-retryable-failure cases. Use when the Async Infrastructure agent starts a new background job from a confirmed async job spec, or when the Backend Developer agent needs the correct job scaffold before implementing the business logic inside it.
---

# scaffold-background-job

## Purpose

Generate the correct background job scaffold from the async job spec so a developer starts from a working baseline rather than copying an existing job and carrying its mistakes forward. The repetitive parts of a background job are the parts that are easy to get subtly wrong: the framework integration, the queue binding, the retry and dead-letter configuration, and the observability instrumentation. A missing retry rule or an unwired metric is an operational defect that surfaces only under load. This skill maps the async job spec fields directly to scaffold configuration so the retry behavior, the typed payload, and the metrics are present from day one. The output is source code, not an envelope artifact.

## Inputs

| Field | Description |
|-------|-------------|
| `async-job-spec` | The confirmed async job spec from spgr-write-async-job-spec. Read with spgr-read-artifact. Defines the payload schema, retry config (max retries, backoff, dead-letter binding), SLA, and the observability metrics to emit. |
| `job-framework` | The queue framework in use (Sidekiq, BullMQ, Celery, Cloud Tasks, SQS, and so on), taken from the tech-stack decision. Determines worker shape and queue binding. |
| `stack-conventions` | Tech-stack conventions for worker file location, module layout, and the typed-schema mechanism. Read existing job files with spgr-read-file to match the established pattern. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Worker class or function | Source written with spgr-write-file, integrated with the named job framework and bound to the correct queue. The business logic body is left as a marked stub for the developer to fill. |
| Message payload schema | A typed payload schema definition derived from the spec's payload fields. |
| Enqueue helper | A type-safe enqueue function that constructs and validates the payload at the call site, so a malformed message fails at enqueue, not in the worker. |
| Retry and dead-letter config | Max retries, backoff strategy, and dead-letter queue binding wired from the spec's retry config. |
| Observability instrumentation | Pre-wired metrics for enqueue, start, success, failure, and duration, matching the metrics named in the spec. |
| Unit test scaffold | Tests via spgr-write-unit-test for the success case, a retryable-failure case, and a non-retryable-failure case. |

## Procedure

1. Read the async-job-spec with spgr-read-artifact and validate it with spgr-validate-artifact against its registered schema. Read the tech-stack decision and any existing job files with spgr-read-file to honor the read-before-write contract and match the established worker pattern.

2. Validate the inputs before generating. Confirm the spec names the payload schema with each field and type, the retry config (max retries, backoff, dead-letter binding), the SLA, and the metrics to emit. Confirm the job-framework is one the stack supports. If any of these is missing or contradictory, or the spec and the tech-stack decision disagree, stop and raise spgr-escalate with the precise gap. Do not fill the gap with a default and proceed.

3. Generate the typed message payload schema directly from the spec's payload fields, with no field the spec does not list and none omitted (YAGNI).

4. Write the unit test scaffold first with spgr-write-unit-test, before the worker implementation. Include a test for the success case, a test for a retryable failure that asserts the job is retried under the spec's retry config, and a test for a non-retryable failure that asserts the job is sent to the dead-letter queue and not retried. Run spgr-run-tests and confirm these tests fail before any scaffold exists.

5. Generate the worker class or function for the named framework, bound to the correct queue. Leave the business logic body as a clearly marked stub for the developer. Wire the retry and dead-letter configuration from the spec's retry config so the right retry behavior is present in the scaffold, not added later.

6. Generate the type-safe enqueue helper that constructs the payload against the typed schema and enqueues it, so an invalid payload fails at the enqueue call site. Wire the observability instrumentation to emit the spec-defined metrics for enqueue, start, success, failure, and duration. The metrics are pre-wired, never deferred.

7. Run spgr-run-tests and confirm the success, retryable-failure, and non-retryable-failure tests now pass against the scaffold. Run lint and format and confirm both are clean before commit. For TypeScript or JavaScript, conform to `/Users/gunderer/Repos/springer/.claude/references/typescript-standards.md` and pass `tsc --noEmit`.

8. Confirm the scaffold matches the spec: the payload schema, retry config, and metric set agree with the async job spec exactly. If the spec cannot be satisfied within the framework or stack, do not deviate silently. Raise spgr-escalate to request a spec change versioned through spgr-version-artifact, and consult the Async Infrastructure vertical with spgr-tag-vertical-agent. Record any consequential scaffolding choice with spgr-log-decision.

## Notes

- The output is source code verified by spgr-run-tests and CI, not an envelope artifact with a registered schema. The unit test scaffold for success, retryable failure, and non-retryable failure is the proof that retry and dead-letter behavior is correct.
- Read the spec and validate field and retry definitions through spgr-read-artifact and spgr-validate-artifact against the registry at /Users/gunderer/Repos/springer/schemas/ rather than inlining field lists here.
- Build only what the spec defines (YAGNI). One logical change per commit. Lint and format must be clean before commit.
- The enqueue helper enforces the payload schema at the call site, so a type error at enqueue replaces a runtime error in the worker.
