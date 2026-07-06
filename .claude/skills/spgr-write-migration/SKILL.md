---
name: spgr-write-migration
description: Write a database schema migration as an expand/contract pair of up and down scripts, so every deploy step stays backwards compatible and reversible with no downtime window. Use when the Backend Developer agent must apply an ERD change to the live schema, or when a story's schema change needs its migration.
---

# write-migration

## Purpose

Produce a database schema migration that follows the expand/contract pattern. A migration written without that discipline opens a deployment window where the old code cannot run against the new schema and the new code cannot run against the old schema, which forces downtime. Separating every additive change from every destructive change across at least two phases removes that window. The output is source code (the migration script pair), not an envelope artifact. Build only the schema change the ERD delta and the story's acceptance criteria require, and nothing more.

## Inputs

| Field | Description |
|-------|-------------|
| `erd_change` | The intended schema change as a delta from the current applied state, read from the approved ERD artifact via spgr-read-artifact. |
| `current_schema` | The applied migration history, read via spgr-read-file, used to confirm starting state and ordering. |
| `migration_strategy` | One of zero-downtime, maintenance-window, or offline. Determines whether expand/contract must be split across deploys. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `migration_script` | Source code: an up migration applying the change and a down migration restoring the prior state. Named timestamp-first as `YYYYMMDDHHMMSS_description.sql` or the framework equivalent, written via spgr-write-file. |

## Procedure

1. Read the ERD change via spgr-read-artifact and the current applied schema via spgr-read-file. Confirm the delta against the applied history before writing anything. If the ERD change and the current schema disagree, stop and raise spgr-escalate.
2. Classify each part of the delta as additive (add a column, table, or index) or destructive (DROP COLUMN, DROP TABLE, a data transformation, a NOT NULL tightening, a type narrowing).
3. Split additive from destructive across phases. Phase 1 expand: add the new column, table, or index, and have new code write to both old and new structures. Phase 2 contract: remove the old structure only after every application-code reference to it is gone. Never combine an add and a remove of related structures in one migration when the strategy is zero-downtime.
4. Detect whether any column or table the contract phase would remove is still referenced by application code. Grep the codebase for the identifier. If a live reference exists, do not emit the contract migration. Stop and raise spgr-escalate naming the referencing files.
5. Write the up migration for the phase being produced. Write a working down migration that restores the exact prior state. Do not mark any schema change irreversible. Find the reversible equivalent, for example back up data before a transform so the down step can restore it.
6. Name the file timestamp-first so ordering is unambiguous, then write it via spgr-write-file.
7. Run spgr-validate-migration-safety on the migration before commit. If that skill flags a destructive operation, or the strategy or delta requires a DROP or a data transformation, raise spgr-notify-human and do not commit until a human approves. A safety pass alone does not authorize a destructive migration.
8. Test the migration up and down against a staging snapshot via spgr-run-tests before it can target production. Confirm the down migration restores the snapshot state. If either direction fails, fix the script or raise spgr-escalate.
9. Record the expand/contract phasing decision and the chosen strategy with spgr-log-decision so the contract phase has a traceable predecessor.

## Notes

- The output is source code, verified by spgr-validate-migration-safety, spgr-run-tests against a staging snapshot, and CI, not by an envelope schema. There is no registered artifact schema for the migration file itself.
- Every destructive operation is a human gate. DROP COLUMN, DROP TABLE, a data transformation, or any irreversible-by-default change routes through spgr-notify-human even when spgr-validate-migration-safety approves it.
- One logical schema change per migration and per commit. A phase that adds and removes related structures together must be split into separate migrations.
- Lint and format the migration clean before commit. Confirm the down migration exists and runs for every up migration.
- The PR for a migration carries a checklist the code-reviewer agent enforces: expand/contract split confirmed, down migration present and tested, spgr-validate-migration-safety passed, and tested against a staging snapshot.
