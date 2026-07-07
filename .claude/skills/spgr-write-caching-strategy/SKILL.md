---
name: spgr-write-caching-strategy
description: Produce a caching-strategy artifact that defines which data is cached, at which tier, with what TTL and invalidation trigger, plus key design, stampede mitigation, and hit-rate monitoring. Use when the Performance Agent must settle the caching architecture before any cache is built, or is tagged to advise on a specific read path.
---

# write-caching-strategy

## Purpose

Define the caching architecture for the project before any cache is built. Undocumented caching produces the hardest class of correctness bugs, where data looks wrong but only sometimes, because nobody wrote down when the cache goes stale, what invalidates it, what the cold path is, and what must never be cached. Answer those questions per cacheable resource so the cache is a documented decision rather than an emergent behavior.

This is a Performance vertical skill. The Performance Agent operates as consultant, auditor, and gate. When advising a developer or architect on a specific read path, route the recommendation through a consultation artifact via spgr-tag-vertical-agent rather than editing the other agent's artifact directly.

## Inputs

| Field | Description |
|-------|-------------|
| `hot-read-paths` | Hot read paths from query analysis or profiling, the candidates for caching |
| `freshness-requirements` | Per data type, how stale a read is allowed to be |
| `cache-infrastructure` | Available tiers (CDN, Redis, Memcached, in-process) and their constraints |
| `traffic-patterns` | Read/write ratio and peak load characteristics per resource |
| `tenancy-model` | Whether the system is multi-tenant, read via spgr-read-artifact from the architecture decision when present |

Read source inputs with spgr-read-file and upstream artifacts with spgr-read-artifact.

## Outputs

| Artifact | Description |
|----------|-------------|
| `caching-strategy` | Envelope artifact written via spgr-write-artifact, covering cache tiers, per-resource entries, invalidation strategy, stampede mitigation, bypass rules, cold-cache behavior, and the hit-rate monitoring plan |

## Procedure

1. Enumerate the cache tiers in scope from the available infrastructure: CDN edge cache, API response cache, application-level cache, and database query cache. Record which tiers this project will use and which it will not, with a one-line reason for each.

2. For each hot read path, decide whether to cache it. Skip a path when its read/write ratio or freshness requirement makes caching add complexity without proportionate benefit. Record the skipped paths and the reason.

3. For each cacheable resource, write an entry with: what data is cached, which tier holds it, the TTL, the invalidation trigger, and the cache key design. Specify invalidation in terms of events, not TTL alone. A TTL by itself is insufficient when the data can change at any time, so pair the TTL with write-through or event-driven invalidation for that case.

4. Design every cache key to be collision-safe and tenant-aware. In a multi-tenant system the tenant ID is always part of the key, so user A can never read user B's cached data. If the tenancy model is unknown, escalate before writing keys (step 9).

5. Default to cache-aside. Specify write-through or read-through only when the consistency requirement demands it and the added complexity is justified, and record that justification in the entry.

6. Specify cache stampede mitigation for cold-start and mass-expiry events: name the technique (for example request coalescing, jittered TTL, or early recompute) per resource where a thundering herd would breach the performance budget.

7. List cache bypass requirements: reads that must never be served from cache, such as admin reads and audit reads. Make the bypass condition explicit per resource.

8. Document cold-cache behavior per resource: when the cache is empty after a deploy or flush, name the fallback read path and its performance characteristic. Add the hit-rate monitoring plan: track hit rate per cache key pattern over time, and flag any pattern whose sustained hit rate is low enough that the cache is barely helping (use a project threshold, defaulting to 30 percent) for review and possible removal.

9. Validate before write. Call spgr-validate-artifact inline. Escalate via spgr-escalate, rather than assuming a value, when: a data type has no stated freshness requirement, the tenancy model needed for key design is missing, infrastructure cannot meet a required TTL or consistency mode, or a freshness requirement and the available tier are in direct conflict. Record consequential choices with spgr-log-decision, and stamp the version with spgr-version-artifact. When this strategy advises a developer or architect on a specific path, deliver it as a consultation via spgr-tag-vertical-agent.

## Notes

- Output type is an envelope artifact (`caching-strategy`). Its content schema is registered in a later increment, so envelope-only validation applies for now (spgr-validate-artifact checks the header, confidence map, decision log, and version).
- Mark each entry's confidence as confirmed, proposed, or needs-human-input in the confidence map. A resource that needed an escalation in step 9 cannot be confirmed until the human or upstream agent resolves it.
- Reference artifact field shapes through the schema registry rather than restating them here.
