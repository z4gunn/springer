# scaffold-templates

Read this when selecting and applying a scaffold template for a resolved stack combination. The template library exists so scaffolds stay consistent across projects. Each template is a per-stack file map, not a single command, so the same stack always produces the same layout.

## Library structure

Templates are keyed by the full stack combination resolved from the tech-stack-decision, named in lowercase-kebab with each layer joined by a plus, for example `rails-postgres-react-tailwind`. A key matches only when every layer in the decision matches. A partial match is not a match. When no key matches the resolved stack, raise spgr-escalate so the library gains a new template rather than improvising a one-off layout.

Each template entry defines five things.

| Part | What it specifies |
|------|-------------------|
| Directory map | The root folders and their meaning, aligned to the architecture layering. |
| Dependency manifest | The base dependencies and the lockfile to write and commit. |
| Tooling config | Linter, formatter, and test-runner config files with stack defaults. |
| CI stub | The pipeline file that runs lint, format check, and the example test on push. |
| Boilerplate | The one passing example test, the `.env.example` skeleton, and the README stub. |

## Applying a template

1. Resolve the stack combination from the tech-stack-decision and look up the matching key.
2. Copy the directory map and adjust folder names only where an architecture ADR requires a different boundary. Do not add speculative folders.
3. Write the dependency manifest, install, then write the resulting lockfile so it is committed.
4. Write the tooling config and run the linter, formatter, and test runner to confirm a clean pass.
5. Write the CI stub, the example test, the `.env.example`, and the README stub.
6. Run the full clean-environment validation gate from the SKILL procedure before handoff.

## Adding a template

When an escalation requests a new stack combination, add one entry that fills all five parts above, then run the clean-environment validation gate against a fresh checkout to confirm install, lint, format, test, and CI all pass. Only a template that passes the gate is added to the library.
