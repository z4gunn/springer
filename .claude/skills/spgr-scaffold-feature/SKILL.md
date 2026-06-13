---
name: spgr-scaffold-feature
description: Generate the boilerplate file set for one new feature, following the project's existing structure and naming conventions exactly, with the story's acceptance criteria pre-filled as machine-readable TODO comments in every stub and the ERD change recorded in the migration stub. Use when the backend or frontend developer agent picks up a confirmed user story and wants a clean, conventionally-structured starting point (route, controller, service, model or repository, migration, and test stubs) before writing feature logic.
---

# scaffold-feature

## Purpose

Lay down the correctly structured starting point for one feature so the implementing agent writes logic, not file plumbing. Feature work that starts by copy-pasting an existing feature carries that feature's inconsistencies forward, so generate fresh stubs from the project's conventions instead. Each stub is a starting point and not finished code. It carries the correct structure, the right imports, and the story's acceptance criteria as TODO comments so the contract never gets lost between the story and the implementation. Keep the scaffold lint and format clean, because a stub that fails lint wastes the implementing agent's first action.

## Inputs

| Field | Description |
|-------|-------------|
| `user-story` | The confirmed user story with its acceptance-criteria set. Read with spgr-read-artifact. The acceptance criteria are pre-filled into the stubs. |
| `architecture-decision` | Approved architecture ADRs. The directory, layering, and naming conventions the scaffold must follow. Read with spgr-read-artifact. |
| `feature-name` | The feature name used to derive file names, class names, and route paths under the project's naming convention. |
| `project-structure` | The existing repository tree to match. Read with spgr-read-file so the scaffold mirrors current layout rather than inventing one. |
| `erd` | The ERD or the relevant entity definition, read with spgr-read-artifact only when the feature requires a schema change, so the migration stub records the exact change. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Feature boilerplate (source code) | A set of stub files written with spgr-write-file: route handler stub, controller stub, service-layer stub, data model or repository stub, a migration stub when the feature requires a schema change, and test file stubs (one acceptance test stub, unit test stubs). Each stub carries the correct file structure and imports, the story's acceptance criteria as machine-readable TODO comments, and, for the migration, the ERD change as a comment. |

## Procedure

1. Read the user-story and its acceptance-criteria set with spgr-read-artifact, and the architecture-decision with spgr-read-artifact. If the story is unconfirmed, the acceptance criteria are missing, or the architecture is unapproved, stop and raise spgr-escalate. Do not scaffold against an incomplete contract or invent conventions the architecture has not set.

2. Read the existing project structure with spgr-read-file. Derive the file names, class names, and route paths from the feature-name using the project's exact naming and directory conventions. If the project's convention for any of these is ambiguous or the architecture and the existing tree disagree, stop and raise spgr-escalate rather than picking a layout.

3. Determine the stub set the story needs. Generate only the stubs the acceptance criteria call for (YAGNI). Skip the migration stub when the feature requires no schema change, and skip layers the architecture does not use.

4. For each stub, write the correct file skeleton with its imports and the layer's conventional shape, with no implementation logic. Pre-fill the story's acceptance criteria as TODO comments in a single machine-readable format (one criterion per comment, tagged with the criterion ID) so the acceptance-test generator and the implementing agent both read the same contract. See [references/ac-comment-format.md](references/ac-comment-format.md) for the comment format.

5. When the feature requires a schema change, write the migration stub and record the relevant ERD change as a comment in it, so the implementing agent does not look it up separately. Pair this with spgr-write-migration when the migration is implemented later.

6. Write every stub to disk with spgr-write-file, honoring the read-before-write contract.

7. Run the project formatter and linter on the generated stubs and confirm a clean pass before handoff. For TypeScript or JavaScript, conform to `/Users/gunderer/Repos/springer/.claude/references/typescript-standards.md` and pass `tsc --noEmit`. Fix any stub that fails. Do not hand off a scaffold that is not lint and format clean.

8. Record the resolved naming, the stub set generated, and any convention decision that shaped the layout with spgr-log-decision so the reasoning is traceable.

## Notes

- The output is source code (the feature stubs and the migration stub), verified by spgr-run-tests and CI rather than by an envelope schema.
- The acceptance-test stub is a starting point for spgr-write-acceptance-test, which turns the pre-filled criteria into executable failing tests before any implementation begins. The TODO comment format is the machine-readable bridge between this skill and that one.
- Read every input artifact with spgr-read-artifact and reference the schema registry through spgr-validate-artifact. Do not inline their field lists here.
- Keep one logical change per commit and the tree lint and format clean before any commit.
