---
name: spgr-write-load-test
description: Write performance and load test scripts (k6, Gatling, or Locust) that validate the system against its NFR performance targets under baseline, peak, spike, and soak traffic, with thresholds wired to NFR IDs. Use when the QA, Performance, or Architect agent must verify NFR targets against a staging environment before launch.
---

# write-load-test

## Purpose

Translate NFR performance targets into executable load test scripts that exercise the system at scale and fail loudly when a measured value misses its target. Functional tests run at single-user scale and never surface query degradation, connection-pool exhaustion, or burst-recovery behavior. These scripts do. The contract that matters here is the one-to-one binding between each script threshold and an NFR ID, so a failure names the regulation it broke rather than reporting an anonymous "threshold exceeded."

## Inputs

| Field | Description |
|-------|-------------|
| `nfr-targets` | Specific p50/p95/p99/p99.9 latency targets, max error rate, and minimum RPS throughput, each carrying its NFR ID. Read the source NFR artifact via spgr-read-artifact. |
| `traffic-model` | Expected concurrency, request distribution across endpoints (the percent share per endpoint), and the peak-vs-sustained load ratio. |
| `auth-mechanism` | The authentication flow and dedicated staging test credentials the script uses to obtain tokens. |
| `target-environment` | The staging target, with confirmation it is infrastructure-equivalent to production. Never production. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Load test scripts | One script set per chosen tool (k6, Gatling, or Locust) covering baseline, peak, spike, and soak scenarios, with per-scenario pass/fail thresholds. Written via spgr-write-file. |
| Results report | A report carrying p50/p95/p99/p99.9 latency, error rate, throughput (RPS), and resource utilization (CPU, memory, database connection count) per scenario. Written via spgr-write-artifact (see Notes). |

## Procedure

1. Read the NFR targets with spgr-read-artifact and confirm each performance target is specific, measurable, and carries an NFR ID. If any target is vague (for example "fast" with no number) or missing an ID, stop and raise spgr-escalate naming the gap. Do not invent a threshold.
2. Confirm the target environment is staging and is infrastructure-equivalent to production (same instance sizes, same database tier, same cache configuration). If the environment is production, or is smaller than production, stop and raise spgr-escalate. A quarter-sized environment produces misleading results, so the run must not proceed.
3. Confirm the test credentials are dedicated staging test accounts that carry no real PII. If real user accounts are supplied, stop and raise spgr-escalate.
4. Select the tool: k6 for scripting flexibility, Gatling for JVM-based systems, Locust when test logic is complex Python. Record the choice and its reason with spgr-log-decision.
5. Encode the traffic model as a weighted request distribution that matches the input percentages per endpoint. Do not hammer a single endpoint at peak RPS, since that tells you almost nothing about real-world behavior.
6. Author every scenario in the run. Baseline: sustained load at 50 percent of peak RPS for 10 minutes. Peak: ramp to maximum expected concurrent users over 5 minutes, sustain 10 minutes, ramp down. Spike: instant jump from 0 to peak RPS, then observe recovery. Soak: sustained moderate load for 1 hour to surface memory leaks and connection-pool exhaustion. Each run includes ramp-up, sustained, and spike profiles, because each catches a different failure mode.
7. Wire each pass/fail threshold one-to-one to an NFR ID. Write the failure message to name the NFR ID, the measured value, and the target value, in the form "p99 latency: 340ms (NFR-PERF-01 target: 200ms or less)". Never emit a bare "threshold exceeded".
8. Write the scripts with spgr-write-file. Run them with spgr-run-tests against staging and confirm they execute, parse the traffic model, and emit thresholds before handoff.
9. Produce the results report from the run output with spgr-write-artifact.
10. If any scenario fails an NFR threshold, tag the Performance Agent with spgr-tag-vertical-agent, passing the specific bottleneck findings (slow queries, saturated connection pool, CPU-bound endpoint) from the results report. Remediation does not begin before diagnosis.

## Notes

- The script set is source code, verified by running it with spgr-run-tests and by CI, not by an envelope schema.
- The results report is an artifact type not yet in the registered schema list. Write it via spgr-write-artifact with its registered schema added in a later increment, and validate inline with spgr-validate-artifact once that schema exists.
- For the Phase 2 CI path: author the weekly staging run as a CI job and trend p99 latency and throughput across runs to catch gradual degradation before it becomes a production incident.
- When a scenario flags a slow endpoint, trigger an APM profiler capture during the run so the Performance Agent receives a flame graph alongside the results report.
- Once the product is live, replace the estimated traffic model with one synthesized from production analytics so the load profile reflects real usage.
- The NFR targets that drive these thresholds trace back to spgr-write-nfr, and the acceptance contract for a performance story comes from spgr-write-acceptance-criteria.
