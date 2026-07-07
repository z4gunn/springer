---
name: spgr-check-rate-limit-consistency
description: Produce a rate-limit-consistency report that checks every API endpoint against the rate-limit configuration and entitlement map, verifying tenant-level enforcement, with a PASS or GATE verdict that blocks release on IP-only limits or cross-tenant degradation. Use when the Multi-tenancy Agent must confirm tenant-fair rate limiting before a release.
---

# check-rate-limit-consistency

## Purpose

In a multi-tenant system, rate limits are the fairness and availability mechanism that stops one high-volume tenant from exhausting shared resources (database connections, external API quotas, compute) and degrading the experience for every other tenant. This skill produces a check report that verifies rate limits are enforced at the correct granularity (per tenant or per API key, not per IP) and stay consistent with the product's plan structure. As an auditor and gate skill for the Multi-tenancy vertical, it sets a blocking threshold and returns a PASS or GATE verdict. The report is a consultation input to the horizontal agent that owns the API surface, so route fixes through a consultation rather than editing the gateway config directly.

## Inputs

| Field | Description |
|-------|-------------|
| `rate-limit-config` | Rate-limit middleware, API gateway rules, or limiter source defining limits, key granularity, and storage backend |
| `entitlement-map` | Plan entitlement map stating whether plan tiers carry different rate limits (read via spgr-read-artifact) |
| `api-surface` | The set of endpoints, marking which carry rate limits and which are intentionally exempt |
| `load-test-result` | Optional output of a noisy-neighbor load test (one tenant at 10x limit for 5 minutes) used to verify cross-tenant isolation |

## Outputs

| Artifact | Description |
|----------|-------------|
| `rate-limit-consistency-report` | Check-report envelope artifact carrying per-endpoint and per-plan-tier limit configuration, a granularity assessment, consistency gaps, plan-differentiation verification, 429 response verification, the noisy-neighbor isolation result, findings by severity, and a PASS or GATE verdict. Written via spgr-write-artifact with inline spgr-validate-artifact |

## Procedure

1. Load the inputs. Read the rate-limit config with spgr-read-file. Read the entitlement map and any prior version of this report with spgr-read-artifact. If the rate-limit config, the entitlement map, or the API surface is missing or contradictory, stop and raise spgr-escalate with the precise list of what is missing. Do not assume a default limit or granularity.

2. Build the per-endpoint and per-plan-tier configuration table. For each endpoint on the API surface, record the configured limit, the key the limiter is bucketed on, and the plan tiers it applies to. Mark each endpoint as limited or exempt.

3. Assess granularity per endpoint. The limiter key must be the tenant identifier or an API key that maps to a tenant. IP-level keying is insufficient because it is circumvented by rotating addresses and incorrectly penalizes users behind a shared NAT. Flag any tenant-scoped endpoint keyed only on IP.

4. Verify consistency gaps. Flag any endpoint that handles tenant work and consumes shared resources but carries no rate limit and is not on the documented exempt list.

5. Verify plan differentiation. Where the entitlement map states a paid tier carries a higher limit, confirm the config enforces that tier's limit per plan and that the limit is read from the tenant's plan rather than hardcoded. Flag any plan whose stated limit is not actually enforced.

6. Verify the rate-limit response. Confirm a limited request returns `429 Too Many Requests` with a `Retry-After` header, and that every API response carries `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` so consumers can manage limits proactively. Flag a missing `Retry-After` or missing rate-limit headers.

7. Verify rate-limit storage resilience. Confirm the limiter backend (for example Redis) is not a single point of failure and fails open with logging rather than fail closed, so a limiter outage does not take down the API. Flag a fail-closed limiter or an unreplicated single-instance backend.

8. Verify cross-tenant isolation. If a noisy-neighbor load test result is supplied (one tenant sending at 10x its limit for 5 minutes), confirm other tenants' p95 latency is unaffected. If no test result is supplied, record the isolation check as unverified and recommend the load test before release.

9. Assign severity to each finding and set the verdict. Treat as high (blocking) any IP-only limit on a tenant-scoped endpoint, any consumed-shared-resource endpoint with no limit, any plan tier whose differentiated limit is not enforced, and any measured cross-tenant p95 degradation under the noisy-neighbor test. Treat a missing `Retry-After`, missing rate-limit headers, or an unverified isolation check as medium (advisory). Set the verdict to GATE if any high finding exists, otherwise PASS.

10. Write the report with spgr-write-artifact and run inline spgr-validate-artifact. On a GATE verdict, log the gate with spgr-log-decision and route the findings to the API-surface-owning agent via spgr-tag-vertical-agent as a consultation. Notify the human with spgr-notify-human only when the gate blocks a release checkpoint.

## Notes

- Output type is a check or audit report (an envelope artifact). The `rate-limit-consistency-report` content schema is not registered yet, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, version) and the content schema is registered in a later increment.
- This skill is a gate. The blocking threshold is any high-severity finding. A GATE verdict blocks the release or architecture-review checkpoint until the owning agent resolves the finding and the report is re-run.
- Recommendations to the horizontal agent flow through a registered consultation (spgr-tag-vertical-agent). Do not edit the rate-limit config or the API agent's artifacts directly.
- Carry the version forward with spgr-version-artifact when re-running against a changed config or a new release so the posture is comparable across runs.
