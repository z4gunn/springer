---
name: spgr-generate-readme
description: Generate the project README.md as source code, the entry-point document that lets a new developer answer what the project is, how to run it locally from a clean environment, and how to contribute, in under ten minutes, plus a PR-time freshness check that flags a stale README when config files change without it. Use when the Documentation Agent stands up or refreshes the README for a project, or when any commit changes package.json, Dockerfile, .env.example, or another file the README describes and the README must be updated in the same change.
---

# generate-readme

## Purpose

Produce `README.md`, the first document a new developer reads. The README sets the mental model for what the project is, signals that the project is maintained, and gives a quickstart that reaches a running local environment without guesswork. This is the Documentation vertical operating as a builder of source output, not an envelope artifact. The two contract rules that matter: the quickstart is verified from a clean environment so it actually works, and the README is kept current in the same commit as any change it describes, because a stale README misleads rather than helps.

## Inputs

| Field | Description |
|-------|-------------|
| `project_description` | Project name and value proposition, what it is and why it exists. |
| `tech_stack` | Languages, frameworks, and key dependencies with pinned versions. |
| `local_dev_setup` | Local development setup from the project scaffold, install, configure, and run steps. |
| `architecture_overview` | Top-level structure and component view from the architecture artifacts, read via spgr-read-artifact. |
| `changed_files` | For the freshness check, the file list of the PR diff under review. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `README.md` | Source file written to the repository root via spgr-write-file, covering name and one-line description, status badges, what it is and why, prerequisites with exact versions, a verified local quickstart, project structure, testing, a CONTRIBUTING link, and license. |
| Freshness finding | A PR-time flag raised via spgr-escalate when a described config file changed without a matching README update. |

## Procedure

1. Read the inputs. Pull `project_description`, `tech_stack`, and `local_dev_setup` from the scaffold and project sources via spgr-read-file, and the structure and component view from the architecture artifacts via spgr-read-artifact. Where the architecture or onboarding detail is owned by another agent, request it through spgr-tag-vertical-agent rather than inferring it.
2. Draft the README sections in order: project name with a one-line description and status badges (CI, coverage, version), a two-to-three sentence statement of what it is and why it exists written as plain description and not marketing copy, prerequisites with exact versions (for example Node 20.x, Go 1.22, PostgreSQL 16, never "recent version"), the local development quickstart as install then configure then run, the project structure as top-level directories and what each contains, how to run the tests, a link to CONTRIBUTING.md, and the license.
3. Make every code block specify its language for syntax highlighting. Make status badges real badges generated from CI and registry data that reflect actual state, not placeholder images.
4. Verify the quickstart from a clean environment. Run the listed install, configure, and run steps as written with nothing assumed pre-installed beyond what the prerequisites name. If a step fails or depends on an unlisted tool, fix the instructions or add the missing prerequisite before writing the file. Do not ship a quickstart that has not been run.
5. Write `README.md` to the repository root via spgr-write-file, then call spgr-validate-artifact for envelope-only validation. Verify the file in CI through spgr-run-tests or the documentation coverage gate.
6. Run the freshness check on the PR diff. If any file the README describes (package.json, Dockerfile, .env.example, and similar) appears in `changed_files` without a corresponding edit to README.md, raise the gap via spgr-escalate as a blocking PR finding and record the rationale via spgr-log-decision. If inputs are missing or contradictory, for example a version the tech stack and scaffold disagree on, stop and escalate with the precise gap rather than guessing.

## Notes

- Output type is SOURCE/CONFIG (a `README.md` source file), so it is written via spgr-write-file and verified by CI, not stored as a content-schema artifact. Its content schema is registered in a later increment, so envelope-only validation from spgr-validate-artifact applies for now.
- The freshness check is the gate behavior for this skill. An undocumented change to a described config file is a blocking finding on the PR, surfaced through spgr-escalate, not a silent edit to another agent's artifact.
- Version the README with spgr-version-artifact when it is regenerated so onboarding history stays recoverable.
