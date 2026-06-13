---
name: spgr-write-fixture-factory
description: Generate fixture factories for test data, one factory per domain entity, with valid defaults that encode domain constraints, per-call override support, named traits for recurring states, association factories for foreign keys, and sequence-based uniqueness, using Factory Boy, FactoryBot, Fishery, or the stack equivalent. Use when the QA Agent defines or updates the project's test data factories, or when the Backend Developer Agent needs factories to set up integration tests or flags that a factory breaks after a data model change.
---

# write-fixture-factory

## Purpose

Replace hardcoded test fixtures with factories that generate valid entity instances from minimal specification. A factory encodes what a valid entity looks like, so a test states only the fields it cares about as overrides and the rest are filled with realistic but obviously fake data. Factories stay consistent with the current schema because they are expressed in the same language as the domain model, and a default factory that produces a valid entity is the source of truth for the entity's domain constraints. Build only the factories and traits the integration tests need, not a factory for every conceivable state.

## Inputs

| Field | Description |
|-------|-------------|
| `data_model` | Schema files, ORM models, or TypeScript interfaces defining each entity. |
| `domain_constraints` | Which fields are required, which have valid ranges, which are unique, which reference other entities. |
| `validation_rules` | The domain's own validation rules, used to assert each default factory output is valid. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Factory definition files | One factory per entity with a valid default, override support, named traits, association factories for foreign keys, and sequence-based uniqueness for unique fields. |
| Factory validation test | A test that calls the default factory for every entity with no overrides and asserts each result passes the domain validation rules. |
| Factory reference table | A generated table listing each entity, its default field values, and its available traits. |

## Procedure

1. Read the data model and domain constraints with spgr-read-file. If a required constraint is missing or two inputs contradict (a field marked required in the model but optional in the constraints), stop and raise it with spgr-escalate rather than guessing the valid shape.

2. Read the acceptance criteria for the stories under test with spgr-read-artifact, or call spgr-write-acceptance-criteria when they are absent. Scope the factories and traits to the entities and states those criteria exercise. Do not add a factory or trait no test needs.

3. Write the factory validation test first, before any factory exists, so it fails. The test iterates every entity, calls its default factory with no overrides, and asserts the result is valid per the domain validation rules. This is the canary for schema and factory drift. Run it with spgr-run-tests and confirm it fails.

4. Write one factory per entity. The default factory generates a fully valid instance: required fields populated, statuses set to a valid value, and every domain constraint satisfied. A default that produces an invalid entity forces every test to override the missing field, which is noise that hides the test's intent.

5. Use realistic but obviously fake data. Generate names with Faker so they look real but are clearly synthetic, set email addresses to the example.com domain, use phone numbers in the E.164 test range, and use small integer amounts for money. Output that looks like real data is a PII risk if it reaches a production context by accident, so it must be obviously wrong on sight.

6. Support per-call overrides so any field can be set at the call site with a single argument. Model recurring entity states as named traits, not as separate top-level factories. When several tests repeat the same set of overrides, that pattern is a missing trait, so add the trait and keep the factories DRY.

7. Add association factories. When entity A holds a foreign key to entity B, the factory for A creates a B automatically unless the caller passes a specific instance.

8. Use sequences for fields with unique constraints so repeated factory calls in one test run never collide.

9. Apply a performance budget. If a factory with associations triggers more than three database writes from cascading associations, flag it and consider a lighter-weight test double for the peripheral associations, since deep association chains slow test setup.

10. Generate the factory reference table by introspecting all factory definitions, listing each entity, its default field values, and its available traits, so a new agent can read the test data landscape quickly.

11. Run the full suite, lint, and format with spgr-run-tests and confirm clean and the validation test green before write. For TypeScript or JavaScript, conform to `/Users/gunderer/Repos/springer/.claude/references/typescript-standards.md` and pass `tsc --noEmit`. Write each factory file, the validation test, and the reference table through spgr-write-file. Record any non-obvious factory design choice with spgr-log-decision. When a factory touches a vertical's domain (a PII field or an access-control state), consult that specialist with spgr-tag-vertical-agent before treating it as done.

## Notes

- The output is source code verified by spgr-run-tests and CI rather than by an envelope schema. The factory reference table is generated documentation, not a registered artifact.
- Do not use factories in unit tests. Unit tests mock external dependencies, while factories create real objects for a real database. A factory call inside a unit test is a sign the test is actually an integration test.
- When the data model changes (a new required field, a removed or renamed field, a new constraint), update the affected factories in the same PR as the model change. A factory that emits invalid entities causes silent, confusing failures across every test that uses it, and the validation test from step 3 catches the drift immediately.
- A large count of top-level factories is a smell. It points to either a complex data model, which is a design concern to raise, or over-engineered test setup, which means the tests should be refactored.
- Commit one logical change per commit, lint and format clean.
