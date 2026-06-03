---
name: spgr-write-seed-data
description: Produce a deterministic database seed script that loads representative normal-case, edge-case, boundary, relationship, and state-coverage data into a development or test database, structured so each scenario can be seeded independently and mapped to the user stories it supports. Use when the Backend Developer agent needs a realistic, reproducible dataset to work against, when QA needs a known fixture state for a test scenario, or when a schema migration adds or changes a required column and the seed data must be brought back in sync.
---

# write-seed-data

## Purpose

Create a seed script that loads a predictable dataset into development and test databases so developers and agents work against realistic data without hand-building scenarios each run. Determinism is the contract. Running the seed twice on a clean database produces byte-identical data, which is what makes bugs reproducible and tests reliable. The seed covers normal cases, edge and boundary values, every defined relationship type, and every defined status state, and it is partitioned so a caller can load one scenario in isolation.

## Inputs

| Field | Description |
|-------|-------------|
| `erd` | Entities, relationships, and cardinality. Read with spgr-read-artifact. |
| `data-dictionary` | Authoritative field names, types, constraints, and PII classification. Read with spgr-read-artifact. The seed must match these exactly. |
| `user-stories` | The scenarios the seed must cover, and the source for the scenario-to-story map. Read with spgr-read-artifact. |
| `test-plan` | The QA scenarios and test-data strategy the seed must satisfy. Read with spgr-read-artifact. |
| `migrations` | Current schema migrations on disk. Read with spgr-read-file to confirm every required column has a seed value. |

## Outputs

| Artifact | Description |
|----------|-------------|
| seed script | Source code that loads the dataset, partitioned by scenario, written with spgr-write-file. |
| scenario map | A comment block or sidecar manifest in the seed source listing each scenario, the entities it loads, and the user-story IDs it supports. |

## Procedure

1. Read the ERD, data dictionary, user stories, and test plan with spgr-read-artifact. Read the current migrations with spgr-read-file. If any input is missing, contradictory, or a required column in the migrations has no defined value source, stop and raise spgr-escalate with the precise list of what is missing. Do not invent values to fill a gap.

2. Enumerate the scenarios to cover. Derive them from the user stories and the test plan, not from habit. At minimum cover the normal case (typical usage), the empty or first-run state, boundary values (minimum and maximum for each constrained field), every relationship type defined in the ERD including the many-to-many junctions, and every status state each entity can hold.

3. Make every value deterministic. Use fixed reference timestamps for created_at and updated_at, never now() or any clock call. Use no random values and no generated UUIDs unless they are hardcoded constants. Seed primary keys and foreign keys from a fixed sequence so reruns are identical.

4. Use obviously fake values for any field that resembles PII, and confirm the PII markers in the data dictionary are all covered. Names use forms like Alice Test and Bob Example. Emails use the example.com domain. Phone numbers use the 555-0100 reserved range. Payment values use the published test card numbers from the project payment provider. Never write a value that could be mistaken for real PII.

5. Partition the script so each scenario seeds independently. A caller must be able to load only the empty-state scenario, or only the pro-user scenario, without loading the rest. Keep shared reference data (lookup tables, enums) in a base block that each scenario depends on.

6. Add a guard that refuses to run against a production environment. Seed data is for development and test only. The script reads the environment and exits non-zero if the target is production.

7. Write the scenario-to-story map into the source so a developer can load the right context fast. List each scenario, the entities and counts it loads, and the user-story IDs it supports.

8. Write the script with spgr-write-file. Validate the result by running it against a clean test database, then running it a second time, and confirming the two loads are identical. Run the project test suite that depends on the seed with spgr-run-tests. Lint and format the source clean before the change is committed. Record any consequential modeling choice (for example, how a boundary value was chosen) with spgr-log-decision.

## Notes

- The output is source code, verified by spgr-run-tests and CI, not by an envelope schema, so there is no spgr-write-artifact or spgr-validate-artifact call in this skill.
- This skill produces static seed data only. For dynamic per-test data generation through factory libraries (FactoryBot, Factory Boy, Fishery, or the stack equivalent), call spgr-write-fixture-factory. The two are complementary. The seed loads fixed scenarios into a shared database, the factories build ad-hoc records inside individual tests.
- Keep the seed in sync with schema migrations. When a migration adds a required column, this skill must be re-run to add a valid value for it. A stale seed that omits a now-required column is a defect, not a warning.
- Follow YAGNI. Seed only the scenarios the user stories and test plan name. Do not pad the dataset with rows no test or story exercises.
- One logical change per commit. A new scenario, a sync to a migration, and a value correction are separate commits.
