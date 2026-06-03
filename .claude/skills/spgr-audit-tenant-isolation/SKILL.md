---
name: spgr-audit-tenant-isolation
description: Produce a tenant-isolation audit report that tests whether one tenant's data, resources, and operations can be accessed or affected by another tenant, checking isolation at the API, database, storage, cache, and session layers, recording per-layer findings with cross-tenant access evidence, and returning a PASS or GATE verdict that blocks release on any confirmed cross-tenant access path. Use when the Multi-tenancy Agent must confirm a multi-tenant release or architecture review enforces isolation at every layer, or when a CI sweep needs the current isolation posture before a cross-tenant data leak reaches production.
---

# audit-tenant-isolation

## Purpose

Tenant isolation is the most critical security property in a multi-tenant SaaS product. A bug that lets tenant A read tenant B's data is a catastrophic privacy violation that can end the company. Unlike most security properties, isolation bugs are not caught by SAST or DAST. They require understanding the application's multi-tenancy model and testing its enforcement at each layer of the stack. Run this audit to make isolation a tested, reviewable property rather than an assumption.

This skill operates the Multi-tenancy Agent in auditor and gate mode. The audit is behavioral and code-level. It does not trust that a query "looks right." It authenticates as two distinct tenants and attempts cross-tenant access, and it reads the actual query, object name, and cache key. It sets a blocking threshold. Any confirmed cross-tenant access path is a release blocker.

## Inputs

| Field | Description |
|-------|-------------|
| `tenancy-model` | The multi-tenancy architecture model: shared schema with a tenant_id column, schema-per-tenant, or database-per-tenant. Read with spgr-read-artifact (tenant provisioning spec) or spgr-read-file. |
| `api-surface` | Every endpoint that operates on a tenant-scoped resource. Located with spgr-search-codebase and read with spgr-read-file, or from a confirmed api-spec via spgr-read-artifact. |
| `storage-layer` | How tenant isolation is enforced in object storage (S3 or file storage): object naming convention and IAM policy. Read with spgr-read-file. |
| `caching-layer` | The cache key design, used to confirm tenant_id is always part of the cache key. Read with spgr-read-file. |
| `release-scope` | Optional. The resources or endpoints in the pending release, used to scope the gate verdict to what is shipping. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `tenant-isolation-audit` | Audit report envelope artifact written via spgr-write-artifact. Carries per-layer findings (API, database, storage, cache, session and token) with cross-tenant access evidence, gaps by severity, the blocking findings, and a PASS or GATE verdict. |

## Procedure

1. Read the inputs. Load the tenancy model first, because every later check depends on which model is in use. If the tenancy model, the API surface, or the cross-tenant test accounts are missing, stop and raise spgr-escalate with the precise list of what is absent. Do not infer the isolation mechanism from habit.

2. Audit the API layer with two-tenant cross-access tests. Provision or confirm two distinct test tenant accounts, tenant A and tenant B. For each tenant-scoped resource type, authenticate as tenant A and use tenant A's auth token to request, modify, and delete tenant B's resource IDs. Record pass or fail per resource. A pass returns 403 or 404. A fail returns 200 with tenant B's data, which is a confirmed cross-tenant access path and a blocking finding. Add an automated test per resource type to the integration suite so each cross-tenant attempt is asserted to return 403 or 404, not 200.

3. Audit the database layer for missing tenant scoping. Review every multi-tenant query for a missing tenant filter (for example a missing `WHERE tenant_id = $current_tenant`). This is the most common isolation bug and it passes code review because the query is correct, just not tenant-scoped. For shared-schema tenancy, confirm a row-level enforcement mechanism exists. PostgreSQL Row-Level Security policies are the verified approach. Application-level enforcement is acceptable only when it is confirmed consistent across every query path, so trace each path rather than sampling.

4. Audit the storage layer. Review the object naming convention and the IAM policy for any path that lets one tenant read or write another tenant's objects. Flag tenant identifiers that are guessable or sequential where the IAM policy does not also scope access by tenant.

5. Audit the cache layer. Confirm tenant_id is present in every cache key for tenant-scoped data. A cache key without tenant_id can serve tenant A's cached response to tenant B, which is a confirmed cross-tenant access path.

6. Audit the session and token layer. Confirm tenant context is derived from the authenticated session or token and cannot be set or overridden from user-controlled input (a header, a query parameter, or a request body field). A tenant ID that the client can supply is a blocking finding.

7. Classify findings by severity. Any confirmed cross-tenant access path at any layer is highest severity and blocking. A missing tenant filter, a cache key without tenant_id, and a client-settable tenant context are confirmed paths. A guessable object name behind a correct IAM policy is reported but does not block on its own.

8. Set the verdict. The blocking threshold is any confirmed cross-tenant access path on an in-scope resource. If `release-scope` is supplied, score the verdict against only the resources in scope. The verdict is GATE if any blocking finding exists, otherwise PASS.

9. Write and validate the report. Write the `tenant-isolation-audit` artifact via spgr-write-artifact with inline spgr-validate-artifact. Record the verdict rationale and each blocking finding with spgr-log-decision.

10. Route remediation, do not patch other artifacts. For each finding owned by another agent (a backend query path, an architecture isolation pattern, an IAM policy), route the recommendation through a consultation with spgr-tag-vertical-agent rather than editing that agent's artifact or code directly. On a GATE verdict for a pending release, surface the decision to the human gate with spgr-notify-human, since a cross-tenant leak is a security flag.

## Notes

- Output type is an audit report (envelope artifact). Its content schema is registered in a later increment, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, version).
- Blocking threshold: any confirmed cross-tenant access path on an in-scope resource yields a GATE verdict. A guessable object name behind a correct IAM policy is reported but does not gate on its own.
- This audit reads, tests, and reports only. It does not add tenant filters, rewrite cache keys, or change IAM policy. Recommendations to other agents flow through spgr-tag-vertical-agent.
- API cross-tenant tests require two distinct test tenant accounts. If only one is available, escalate rather than skipping the layer, because single-tenant testing cannot detect a cross-tenant path.
