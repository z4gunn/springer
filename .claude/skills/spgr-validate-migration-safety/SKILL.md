---
name: spgr-validate-migration-safety
description: Produce a migration-safety report that checks one database migration for table-lock risk, backwards incompatibility, data loss, and rollback safety before it runs in any environment, with per-risk severity, recommended safeguards, and a go or no-go recommendation. Use when the Backend Developer agent has written a migration and must clear it before commit, when spgr-write-migration calls the safety gate, or when a QA or code-reviewer agent needs the migration cleared before a story's schema change merges.
---

# validate-migration-safety

## Purpose

Check one database migration for the failure modes that cause outages, then emit a safety report with a go or no-go recommendation. Table locks block all reads and writes during the migration window. Backwards-incompatible changes break old code still running during a rolling deploy. Data loss is irreversible. This skill catches those issues before the migration reaches production. The report is advisory on safe migrations and gating on unsafe ones. A passing report never authorizes a destructive operation on its own. Destructive operations are always a human gate regardless of the recommendation.

## Inputs

| Field | Description |
|-------|-------------|
| `migration_file` | The specific migration to validate (the up and down script pair), read via spgr-read-file. |
| `current_schema` | The applied schema state the migration runs against, read via spgr-read-file, used to resolve what each operation touches. |
| `deployment_strategy` | One of rolling, blue-green, or maintenance-window. Determines whether backwards compatibility is required during the deploy window. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `migration_safety_report` | Per-risk entries (risk type, severity of blocking, warning, or info, and the specific operation causing it), recommended safeguards per risk, and a go or no-go recommendation with rationale. Written via spgr-write-artifact. |

## Procedure

1. Read the migration file and the current schema via spgr-read-file. Detect the target database (PostgreSQL, MySQL, or the configured engine) from the schema or project config. If the migration and the current schema disagree on what exists, stop and raise spgr-escalate naming the mismatch rather than guessing the starting state.
2. Parse each operation in the up script. For each, record the operation type and the table or column it touches.
3. Check lock risk per operation against the target database. For PostgreSQL flag `ADD COLUMN NOT NULL` without a default, `ADD CONSTRAINT`, a non-concurrent index build, and any full-table rewrite. For MySQL flag `ALTER TABLE` on engines that take a table-level lock. Estimate the lock scope and set severity by how it interacts with the deployment strategy. A table-locking operation under a rolling or blue-green strategy is blocking. The same operation under a maintenance-window strategy is a warning.
4. Check backwards compatibility against the deployment strategy. Under rolling or blue-green, flag removing a column still referenced by running code, changing a column type, and renaming a column without an alias or compatibility view. Grep the codebase for any column or table the migration removes or renames. A live reference under a non-window strategy is a blocking risk.
5. Check data loss. Flag DROP COLUMN, DROP TABLE, TRUNCATE, a type narrowing that truncates values, and any irreversible data transformation. Classify each as destructive.
6. Check rollback safety. Confirm a down script exists and restores the exact prior state. A missing down script, or a down script that cannot restore data removed by the up script, is a blocking risk.
7. Check sequence and identifier exhaustion where the migration alters an auto-increment or sequence type, and long-running risk where an operation rewrites a large table.
8. Assign safeguards per risk: `CREATE INDEX CONCURRENTLY` for index builds, staged column additions with a default then a backfill then a constraint, a compatibility view for renames, `lock_timeout` and `statement_timeout` so a long operation fails fast rather than holding locks, and `pt-online-schema-change` or the engine equivalent for online table changes.
9. Set the recommendation. Any blocking risk yields no-go. Warnings yield go with stated conditions. Write the report via spgr-write-artifact with inline spgr-validate-artifact.
10. Record the validation outcome and the rationale for the recommendation via spgr-log-decision.
11. If any operation is destructive, raise spgr-notify-human for explicit approval before the migration runs, even when no other risk is found and the recommendation is go. Do not treat the safety pass as authorization. If input is missing or contradictory, raise spgr-escalate with the precise list of what is wrong rather than filling the gap.

## Notes

- The migration-safety-report is not yet in the registered schema registry. Write it via spgr-write-artifact with its registered schema added in a later increment, validated inline by spgr-validate-artifact once registered.
- A go recommendation is not authorization to run a destructive migration. DROP COLUMN, DROP TABLE, TRUNCATE, and irreversible transformations always route through spgr-notify-human.
- Validate against the deployment strategy, not in the abstract. The same operation can be blocking under a rolling deploy and acceptable under a maintenance window.
- Require testing against a staging snapshot at the same data volume as production before a migration targets production. A migration that is fast on a small dataset can take hours on production volume. Surface this as a condition on the go recommendation when no snapshot run is on record.
- Phase 2: wire this skill as a required CI check on every migration PR, and stand up a staging snapshot pipeline that keeps a recent copy of the production schema for migration testing without exposing production data.
