---
name: spgr-analyze-query-plan
description: Produce a query-analysis report from execution plans, slow query logs, and schema, with per-query findings, ranked optimization recommendations, and ready-to-use index DDL. Use when the Performance Agent must diagnose a slow query or audit a query workload, or when a backend agent needs query-plan evidence for an index or rewrite.
---

# analyze-query-plan

## Purpose

Turn database query execution plans into an evidence-backed optimization report. Slow queries are the most common application performance problem, and a plan that scans a large table on every request degrades as the table grows. This skill makes the problem visible from EXPLAIN ANALYZE output, slow query logs, and schema, so optimization rests on the actual plan rather than a guess. The skill operates in the Performance vertical's consultant and auditor modes. It produces a findings report. It does not edit migrations or application code directly. Index DDL and rewrite recommendations are delivered to the owning horizontal agent through a consultation.

## Inputs

| Field | Description |
|-------|-------------|
| `database_type` | Engine and version (PostgreSQL, MySQL, SQLite, and so on). Plan syntax and index features differ by engine. |
| `query_samples` | Slow query log entries or query samples, each with its measured execution time. |
| `explain_output` | `EXPLAIN ANALYZE` output for each candidate query. Required, not plain `EXPLAIN`. |
| `schema` | Table definitions and existing indexes, for index-coverage analysis. |
| `application_context` | Optional. ORM call sites or list-rendering code, needed to confirm N+1 patterns at the application layer. |

Read source files with spgr-read-file. Read any upstream artifact (performance-budget, slo-spec) with spgr-read-artifact.

## Outputs

| Artifact | Description |
|----------|-------------|
| `query-analysis` report | Envelope artifact with per-query findings (plan summary, identified problem, severity), ranked optimization recommendations (index addition, query rewrite, eager-loading change), an expected-improvement estimate per recommendation, ready-to-use index DDL, and an overall verdict. |
| consultation (when recommendations target another agent) | A registered recommendation to the backend, architect, or DevOps agent for index DDL or query rewrites, raised via spgr-tag-vertical-agent. |

## Procedure

1. Confirm each candidate query carries `EXPLAIN ANALYZE` output, not plain `EXPLAIN`. Plain `EXPLAIN` shows the planner estimate, not the actual execution. If only plan estimates are available, escalate for the analyzed plans before proceeding.
2. Read the schema and the existing indexes so coverage analysis runs against real index definitions, not assumptions.
3. For each query, classify the plan problem: full table scan, sequential scan where an index exists, poor index selection, sort or aggregate without a supporting index, or a covering-index opportunity (a query selecting two or three columns from a large table where a covering index removes the heap fetch).
4. Identify N+1 patterns at the application layer, not the database layer. A single query executed N+1 times in a list page or loop is an eager-loading problem. Confirm against the ORM call site in `application_context`. Do not infer N+1 from the plan alone.
5. For each finding, write a recommendation: index addition (with the exact DDL), query rewrite, or eager-loading change. Attach an expected-improvement estimate grounded in the plan (rows examined before versus after, scan type change).
6. Before recommending the removal of any existing index, verify it is not used by other queries or background jobs in the workload. Do not recommend a drop on the evidence of one query. State this verification explicitly in the finding, and if the workload sample is insufficient to confirm non-use, mark the drop as not-recommended and escalate for a wider sample.
7. Set severity per finding and an overall verdict. A finding that a critical-path query runs a full scan on a large table is the report's blocking signal to the owning agent. Lower-cost findings are advisory.
8. Where a recommendation requires another agent to act (a migration for index DDL, a code change for eager loading), raise a consultation via spgr-tag-vertical-agent rather than editing that agent's artifact or source.
9. Write the report with spgr-write-artifact and call spgr-validate-artifact inline before the write completes. Record consequential analysis choices with spgr-log-decision. Version the report with spgr-version-artifact on revision.

## Notes

- Output type is an audit/review report, written as an envelope artifact via spgr-write-artifact. The `query-analysis` content schema is not registered yet, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, version). Its content schema is registered in a later increment. Registered content-schema types are listed in the schema registry.
- Phase 2 query regression testing: capture the execution plan of each critical query in the report so a later run can compare plans and flag a degradation, for example an index scan dropping to a sequential scan after a table grows. Record the captured baseline plan in the per-query finding.
- Mark every confidence signal explicitly. A recommendation backed by an analyzed plan is confirmed. An estimate without the analyzed plan is proposed. A drop recommendation lacking a full-workload sample is needs-human-input.
- Escalate via spgr-escalate when the analyzed plans are missing, when an index-drop recommendation cannot be cleared against the full workload, or when query samples and execution times are absent and the report cannot be grounded in evidence. Do not fill the gap with assumptions.
