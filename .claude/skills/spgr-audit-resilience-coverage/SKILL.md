---
name: spgr-audit-resilience-coverage
description: Produce a resilience-coverage audit report that checks every external dependency call site for timeout, retry, circuit breaker, and fallback coverage against the resilience spec, returning a PASS or GATE verdict that blocks release on any unguarded call in a critical path. Use when the Resilience Agent must confirm coverage before a release.
---

# audit-resilience-coverage

## Purpose

A resilience spec describes intended behavior. This audit verifies the implementation against it. The common failure is not a complete absence of resilience patterns but inconsistent application. Some call sites set a timeout but no circuit breaker, some retry without backoff, some catch an error and discard it. Any unguarded external call is a cascade failure waiting for a dependency to slow down or go offline. Run this audit to make resilience coverage a reviewable property of the system rather than an assumption.

This skill operates the Resilience Agent in auditor and gate mode. The audit is code-level. It inspects the actual call site, not framework configuration alone. A framework default timeout that is not explicitly set to a project-appropriate value counts as a gap. It sets a blocking threshold. An unguarded external call on a critical path is a release blocker.

## Inputs

| Field | Description |
|-------|-------------|
| `resilience-spec` | The resilience spec naming the required patterns (timeout, retry with backoff, circuit breaker, fallback) per dependency class. Read with spgr-read-artifact. |
| `error-standards` | The error handling standards document defining how errors are caught, logged, and propagated. Read with spgr-read-artifact or spgr-read-file. |
| `source-code` | Source for all service-to-service and service-to-external-API call sites. Located with spgr-search-codebase and read with spgr-read-file. |
| `release-scope` | Optional. The set of services or paths in the pending release, used to scope the gate verdict to what is shipping. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `resilience-coverage` | Audit report envelope artifact written via spgr-write-artifact. Carries a per-call-site row (timeout yes or no, retry yes or no, circuit breaker yes or no, fallback yes or no), coverage gaps by severity, error standard violations, the blocking gaps, and a PASS or GATE verdict. |

## Procedure

1. Read the inputs. Load the resilience spec and error standards with spgr-read-artifact (or spgr-read-file for a raw document). If either is missing, stop and raise spgr-escalate with the precise list of what is absent. Do not infer the required patterns from habit when the spec is the source of truth.

2. Enumerate the external call sites. Use spgr-search-codebase to find every site that imports an HTTP client library, a database client, a message-queue client, or any other out-of-process dependency call. Include background jobs and async workers, not only request-path code. Flag each call site critical-path or not, per the resilience spec dependency classification.

3. Apply the static-analysis enforcement check. Flag any call site that imports an HTTP client or database client without a wrapping resilience library (for example a project that requires resilience4j or an equivalent for all external calls). A raw client call with no resilience wrapper is an unguarded call.

4. Audit each call site at the code level. Inspect the actual site, not just the framework default. For each site record four cells. Timeout configured yes or no, where a value left at framework default and not set to a project-appropriate value is no. Retry configured yes or no, where a retry with no backoff is a partial gap, not a yes. Circuit breaker configured yes or no. Fallback defined yes or no.

5. Audit error standard compliance. Flag silent error swallowing as a high-severity finding. An empty catch (for example `catch {}`) and a catch that only debug-logs and discards (for example `catch (e) { logger.debug(e) }`) both make later debugging impossible. Flag missing error logging and swallowed errors against the error standards.

6. Classify gaps by severity and fix-priority order. Unguarded external calls in critical paths are highest severity. Silent error swallowing is high severity. Apply the spec fix-priority order to each gap. Timeout first, since no timeout is the highest-risk gap. Retry second, since a permanent failure with no retry causes immediate user impact. Circuit breaker third, since it is needed at scale to prevent cascade.

7. Set the verdict. The blocking threshold is any unguarded external call on a critical path, where unguarded means no timeout. If `release-scope` is supplied, score the verdict against only the call sites in scope. The verdict is GATE if any blocking gap exists, otherwise PASS.

8. Write and validate the report. Write the `resilience-coverage` artifact via spgr-write-artifact with inline spgr-validate-artifact. Record the verdict rationale and the blocking-threshold call with spgr-log-decision.

9. Route remediation, do not patch other artifacts. For each gap owned by another agent (a backend developer call site, an architecture pattern decision), route the recommendation through a consultation with spgr-tag-vertical-agent rather than editing that agent's artifact or code directly. On a GATE verdict for a pending release, surface the decision to the human gate with spgr-notify-human.

## Notes

- Output type is an audit report (envelope artifact). Its content schema is registered in a later increment, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, version).
- Blocking threshold: any unguarded external call (no timeout) on a critical path yields a GATE verdict. Non-critical-path gaps and partial gaps (retry without backoff, missing circuit breaker on a non-critical call) are reported but do not gate.
- Fix-priority order for reported gaps is timeout, then retry, then circuit breaker. Silent error swallowing is reported as a high-severity error standard violation.
- This audit reads and reports only. It does not add resilience wrappers or rewrite catch blocks. Recommendations to other agents flow through spgr-tag-vertical-agent.
