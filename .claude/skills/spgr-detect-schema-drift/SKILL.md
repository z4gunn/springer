---
name: spgr-detect-schema-drift
description: Produce a schema-drift report that compares each environment's live database schema against the intended schema derived from running the full migration history on a clean database, listing divergent tables, columns, indexes, and constraints with a per-divergence diff and remediation step, and returns a go or no-go deployment verdict that gates on any drift not explained by an in-progress migration. Use when the Architect Agent must confirm a production deployment is safe, when a deployment pre-gate needs the current drift posture, or when a backend agent runs a check after any manual database change to confirm the live schema still matches the migrations.
---

# detect-schema-drift

## Purpose

Compare the applied database schema in each environment against the intended schema that the migration history defines, and surface every divergence with a remediation path. Drift, where the live schema diverges from what migrations say it should be, causes bugs that cannot be reproduced and makes deployments unsafe. This skill catches drift before it reaches an incident and returns a blocking verdict the deployment gate reads. Apply zero tolerance: any drift that an in-progress migration cannot explain is a blocking issue.

## Inputs

| Field | Description |
|-------|-------------|
| `migration-history` | Applied migrations per environment, in order, with their applied timestamps. |
| `live-schema` | Per-environment introspection of tables, columns, indexes, constraints, and sequences from the running database. |
| `intended-schema` | The schema produced by running all migrations against a clean database. |
| `database-engine` | The engine per environment (PostgreSQL, MySQL, SQLite), which selects the introspection method. |
| `in-progress-migrations` | Migrations mid-rollout, used to explain expected transient divergence. |
| `deployment-window` | Whether the run is inside a scheduled deployment window, used to flag unauthorized manual change. |

Read each input with spgr-read-file. Read any upstream artifact (for example the data-dictionary or erd) with spgr-read-artifact.

## Outputs

| Artifact | Description |
|----------|-------------|
| `schema-drift report` | One report per environment, written via spgr-write-artifact. Records the environment name, divergent tables (present in one schema and not the other), divergent columns (missing, extra, or type-mismatched per table), divergent indexes, divergent constraints, an intended-versus-actual diff for each divergence, a remediation step per divergence, and an overall go or no-go deployment recommendation. |

## Procedure

1. Derive the intended schema. Run the full migration history against a clean database for the target engine and capture the resulting schema as the reference.
2. Introspect the live schema for each environment. Use the engine-specific method: `pg_dump --schema-only` for PostgreSQL, `SHOW CREATE TABLE` for MySQL, `.schema` for SQLite.
3. Diff intended against actual per environment. Compare tables, columns (name, type, nullability, default), indexes, constraints, and sequences. Record every divergence with both sides of the diff.
4. Explain or flag each divergence. If an in-progress migration accounts for the divergence, mark it expected and non-blocking. Otherwise mark it drift and blocking.
5. Write an actionable remediation step per divergence. Name the fix, not just the symptom, for example "run migration 2026-03-15-add-column-x to resolve" rather than "column x is missing." If a divergence is an intentional manual change, the remediation is to formalize it as a migration immediately.
6. Detect unauthorized change. If drift is found outside a deployment window, mark it as a probable unauthorized manual change and raise its severity.
7. Set the verdict. Return no-go if any blocking drift remains, otherwise go. Compute this for each environment, and a no-go in any production environment blocks the deployment gate.
8. Write the report and validate it. Write each environment's report with spgr-write-artifact and run spgr-validate-artifact inline. Version it with spgr-version-artifact and record the verdict and its basis with spgr-log-decision.
9. Escalate on a no-go. On any blocking drift, call spgr-escalate with the divergence list and remediation steps, and spgr-notify-human when the drift is an unauthorized out-of-window change. Do not let a no-go environment pass the deployment gate.

## Notes

- Output type is an envelope artifact (a findings report). The `schema-drift` content type is not registered, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered.
- Run before every production deployment as a pre-deployment CI gate, and after any manual database change including emergency ones.
- Mark each finding's confidence as confirmed when the diff is reproduced from introspection, and needs-human-input when a divergence cannot be classified as expected or drift without judgment.
- The verdict is a hard gate. A no-go on any production environment blocks the deployment regardless of the cause of the drift.
- Tag the DevOps and Backend Developer vertical agents with spgr-tag-vertical-agent when a remediation requires a new migration or a CI gate change.
