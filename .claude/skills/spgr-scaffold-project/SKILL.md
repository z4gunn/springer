---
name: spgr-scaffold-project
description: Generate a new project skeleton from the approved architecture ADRs and tech-stack decision, with directory structure, pinned dependencies, passing lint and format, a test runner with one example test, a CI stub, and an .env.example. Use when a developer agent starts a project and must lay the foundation before any feature code.
---

# scaffold-project

## Purpose

Lay down the initial project foundation before any feature code exists. The structure and conventions set here are inherited by every future feature, and bad initial structure is the primary source of early technical debt because it is costly to correct once code accumulates. Match the approved architecture ADRs and the tech-stack decision exactly, install and pin dependencies, and confirm the linter, formatter, test runner, and CI all actually run before handing off. There is no valid reason to write feature code in an unscaffolded project.

## Inputs

| Field | Description |
|-------|-------------|
| `architecture-decision` | Approved architecture ADRs. Every decision that affects directory structure, layering, or service boundaries. Read with spgr-read-artifact. |
| `tech-stack-decision` | The tech-stack-decision artifact. The binding list of layers, libraries, and pinned versions. Read with spgr-read-artifact. |
| `target-surface` | Which surface to scaffold (backend service, frontend app, or mobile app), since each developer agent scaffolds its own. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Scaffolded project (source code) | Directory structure per the architecture, base dependencies installed, committed lockfile, configured linter, configured formatter, test runner with one passing example test, a CI stub that runs lint, format check, and tests on push, an `.env.example` listing every required variable with no values, and a README stub with project description, local setup steps, and links to key docs. Each file written with spgr-write-file. |

## Procedure

1. Read the architecture-decision and tech-stack-decision artifacts with spgr-read-artifact. If either is missing, unapproved, or does not name the stack for the target surface, stop and raise spgr-escalate. Do not pick a stack or substitute a library.

2. Cross-check the tech-stack-decision against the architecture ADRs. The scaffold must exactly match the tech-stack decision. No substitutions, and no scaffolding against a stack you intend to update the decision for later. If the decision and an ADR conflict, or the decision omits a required layer, stop and raise spgr-escalate rather than choosing.

3. Select the matching scaffold template from the template library for the resolved stack combination (for example Rails with PostgreSQL, React, and Tailwind) so scaffolds stay consistent across projects. See [references/scaffold-templates.md](references/scaffold-templates.md) for the library structure and the per-stack file maps. If no template matches the stack combination, raise spgr-escalate so the library can add one rather than improvising a one-off layout.

4. Generate the directory structure per the approved architecture. Honor the layering and service boundaries the ADRs define. Build only what the scaffold needs, no speculative feature folders (YAGNI).

5. Install the base dependencies and pin every version in the lockfile. Write the lockfile to disk with spgr-write-file so it is committed at scaffold time.

6. Configure the linter and the formatter from the stack defaults in the template. For a JavaScript-runtime stack, initialize tooling with `npx gts init`, then apply the Springer tsconfig and ESLint overrides per `.claude/references/typescript-standards.md`. Plain JavaScript is not a valid scaffold target. Run the linter and formatter with spgr-run-tests or the stack command, and for TypeScript also run `tsc --noEmit`, and confirm a clean pass on the generated tree.

7. Configure the test runner and write one example test that passes. Confirm it runs green with spgr-run-tests. This is the test-first seed the developer agent extends, so the suite must be runnable before any feature work begins.

8. Write the CI pipeline stub. It must actually run lint, format check, and at minimum the one test on push. For a TypeScript stack it must also run the `tsc --noEmit` typecheck. A stub that does nothing is not a CI pipeline and fails the validation step below.

9. Write `.env.example` listing every environment variable the application needs, with documentation and no values. A missing variable here causes local setup to fail for every later contributor, so derive the full list from the stack and the ADRs.

10. Write the README stub with the project description, local setup instructions, and links to the architecture and tech-stack artifacts.

11. Validation gate. Run the scaffold against a clean environment and confirm every check passes before considering the work done: dependency install from the committed lockfile, linter, formatter check, the example test, and the CI stub. Run the suite with spgr-run-tests. If any check fails, fix the scaffold and re-run. Do not hand off a scaffold that does not pass on a clean checkout.

12. Record the resolved stack, the chosen template, and any architecture constraint that shaped the layout with spgr-log-decision so the reasoning is traceable.

## Notes

- The output is source code (the project skeleton, config, CI, and stubs), verified by spgr-run-tests and the clean-environment CI pass rather than by an envelope schema.
- Commit the lockfile and one logical change per commit. Keep the tree lint and format clean before any commit.
- Read both input artifacts before generating any file, honoring the read-before-write contract through spgr-read-artifact and spgr-write-file.
- Reference the artifact schema registry through spgr-validate-artifact when reading the input artifacts. Do not inline their field lists here.
