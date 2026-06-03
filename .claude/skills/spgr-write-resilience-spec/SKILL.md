---
name: spgr-write-resilience-spec
description: Produce a resilience-spec artifact that defines the resilience patterns each service must implement per dependency call (timeouts, retry policy with exponential backoff and jitter, circuit breaker, bulkhead isolation, fallback behavior, and observability), plus the chaos-engineering fault-injection plan that verifies the patterns hold under failure. Use when the Resilience Agent has a service dependency map, SLO specs, and latency budgets and must design graceful-degradation patterns before any failure occurs, or when a new external dependency is added and its failure isolation must be specified before it ships.
---

# write-resilience-spec

## Purpose

Define the resilience patterns each service must implement so partial failures degrade gracefully rather than cascading. A service that calls a slow or unavailable dependency without designed isolation will pile up request threads, exhaust its pool, and become unresponsive, which fails the upstream caller in turn. The resilience spec specifies, per dependency call, the timeout, retry policy, circuit breaker, bulkhead, fallback, and observability that contain a partial failure. It also defines the chaos-engineering plan that injects faults to prove the patterns work before a real outage tests them.

The Resilience Agent owns this skill and operates as a vertical consultant, auditor, and gate. It writes the resilience-spec as an envelope artifact. It does not edit the SLO spec, the latency budgets, or any service implementation directly. A recommendation that changes another agent's artifact section flows through a consultation via spgr-tag-vertical-agent.

## Inputs

| Field | Description |
|-------|-------------|
| `service-dependency-map` | Which services call which external services or other internal services. The set of dependency calls this spec must cover. |
| `slo-spec` | Availability targets that must be maintained under partial failure. Read via spgr-read-artifact. |
| `latency-budget` | How much time each dependency call is allowed to consume, which seeds the timeout values. Read via spgr-read-artifact. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `resilience-spec` | Envelope artifact carrying one entry per dependency call plus the chaos-engineering fault-injection plan. Written via spgr-write-artifact with inline spgr-validate-artifact. |

Each dependency-call entry records the timeout configuration (connect timeout and read timeout, no infinite waits), the retry policy (max retries, backoff strategy, and the retryable-versus-non-retryable status code list), the circuit breaker configuration (failure threshold, half-open probe interval, recovery window), the bulkhead configuration (separate thread pool or connection pool per dependency), the fallback behavior (cached value, degraded response, or graceful failure), and the observability requirements (metrics for circuit breaker state, retry counts, and timeout rates).

## Procedure

1. Read the inputs. Pull the dependency call set from the service dependency map, the availability targets from the slo-spec via spgr-read-artifact, and the per-call time allowance from the latency-budget via spgr-read-artifact. If the dependency map is missing a call that the topology implies, or the latency budget is absent for a call that needs a timeout, stop and raise spgr-escalate with the precise list of missing inputs. Do not guess a timeout value.

2. Set a timeout for every external call. A timeout is mandatory, because a hung external call holds the request thread indefinitely. Derive the read timeout from the latency budget for that call, and set a connect timeout that is tight enough to fail fast on an unreachable host. No call is permitted an infinite wait.

3. Define the retry policy per call. Classify each status code as retryable (transient network errors, 429, 503) or non-retryable (400, 401, 403, 404). Retrying a 400 is wasteful and retrying a 401 will not change the outcome, so retry only the retryable set. Set a bounded max-retry count so total retry time stays inside the latency budget.

4. Require exponential backoff with jitter on every retry. Without jitter, all clients back off to the same slot and create a synchronized retry storm that amplifies the outage. State the base delay, the multiplier, the cap, and the jitter range.

5. Configure the circuit breaker per call. The breaker opens when the error rate or latency exceeds the threshold, which stops the cascade. Specify the failure threshold that trips it, the half-open probe interval that tests recovery before fully reopening, and the recovery window. Set thresholds so the breaker protects the SLO target rather than tripping on normal variance.

6. Configure a bulkhead per dependency: a separate thread pool or connection pool so one saturated dependency cannot exhaust the resources the other dependencies need. Size each pool against the dependency's expected concurrency.

7. Specify the fallback behavior for when the dependency is unavailable or the breaker is open. Choose a cached value, a degraded response, or a graceful failure, and state which reduced-functionality state the system enters. The fallback must keep the upstream service responsive.

8. Specify the observability requirements per call: metrics for circuit breaker state, retry counts, and timeout rates, so the on-call sees the breaker open before users report the degradation.

9. Define the chaos-engineering fault-injection plan: periodic automated latency injection and error injection (for example via Chaos Monkey or Gremlin) that verifies each resilience pattern behaves as designed under failure. Name the target dependency calls, the injected fault types, the schedule, the expected graceful-degradation outcome, and the abort condition that halts the experiment.

10. Log each consequential choice with spgr-log-decision, capturing the decision, the rationale, the alternatives, and the downstream impact, so settled patterns are not re-litigated.

11. Write the resilience-spec via spgr-write-artifact, which runs spgr-validate-artifact inline before the write completes. On a validation failure, fix the reported issues and re-validate. Do not write a partial artifact.

12. Where a pattern implies an amendment to a horizontal agent's artifact (for example a latency budget that cannot accommodate the required retry headroom), route the recommendation through spgr-tag-vertical-agent as a consultation rather than editing that artifact.

## Notes

- Output type is an envelope artifact (`resilience-spec`). Its content schema is registered in a later increment, so envelope-only validation applies for now: spgr-validate-artifact still checks the header, confidence map, decision log, and version.
- Reference the artifact schema registry rather than restating field lists. Read inputs via spgr-read-artifact and write the output via spgr-write-artifact.
- Mark each dependency-call entry with a confidence signal. A pattern derived from a confirmed latency budget and SLO is confirmed, a pattern set without firm budget data is proposed, and a pattern blocked on a missing input is needs-human-input.
- On revision after a new dependency is added or after chaos results show a pattern is insufficient, re-version through spgr-version-artifact.
