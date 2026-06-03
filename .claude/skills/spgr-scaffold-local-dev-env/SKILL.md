---
name: spgr-scaffold-local-dev-env
description: Scaffold a verified local development environment as source files, producing a Docker Compose service stack, idempotent setup targets (`make install`, `make dev`, `make test`, `make reset`, `make verify`), a `.devcontainer/devcontainer.json`, and a seeded database, so a developer reaches a running application within 15 minutes of cloning. Use when the DevOps Agent stands up local dev for a project from a confirmed tech stack, env template, and seed data, or when onboarding friction shows that clone-to-running takes too long or fails from a clean machine.
---

# scaffold-local-dev-env

## Purpose

Produce the files a developer runs after `git clone` to reach a working application without tribal knowledge. The contract is a clean-machine guarantee on a supported OS (macOS, Linux). A developer who knows the tech stack reaches a running application within 15 minutes. The deliverable is source and config, not a documented artifact. Docker Compose pins service versions so the environment is identical across machines and across Codespaces, VS Code Remote Containers, and other containerized dev environments. Setup targets are idempotent, so running setup twice matches running it once.

## Inputs

| Field | Description |
|-------|-------------|
| `tech-stack` | Languages, frameworks, databases, queues, caches, external services. Read the confirmed `tech-stack-decision` artifact via spgr-read-artifact. |
| `env-template` | The `.env.example` from spgr-generate-env-template, with development defaults and test-mode external credentials. |
| `db-schema` | Database schema and migrations for the local database. |
| `seed-data` | Development seed data from spgr-write-seed-data. |
| `local-services` | Existing Docker Compose or equivalent local services config, if any. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `docker-compose.yml` | Local service stack (databases, queues, caches, mock external services) with pinned image versions. |
| `Makefile` | Targets `make install`, `make dev`, `make test`, `make reset`, `make verify`, each idempotent. |
| `.env` defaults | Environment config with every required variable set to a development default, derived from `.env.example`. |
| `.devcontainer/devcontainer.json` | Container definition that reproduces the dev environment in Codespaces and Remote Containers. |
| Seeded database | The local database loaded with development test data after setup runs. |

## Procedure

1. Read the tech stack via spgr-read-artifact and the `.env.example` via spgr-read-file. List every service the application depends on (database, queue, cache, external service) and its required version.
2. Write `docker-compose.yml` via spgr-write-file. Pin an explicit image version per service, never a floating `latest` tag. Add a mock or sandbox service for each external dependency rather than calling a live third party from local dev. Set every credential from `.env`, never a literal value in the compose file.
3. Write the `Makefile` via spgr-write-file with idempotent targets. `make install` provisions tooling and dependencies and re-runs cleanly after a dependency change rather than failing. `make dev` starts the compose stack and the application. `make test` runs the suite. `make reset` tears down and recreates a clean state. `make verify` is the acceptance gate below.
4. Derive `.env` from `.env.example`, setting every required variable to a development default. Carry test-mode external credentials (for example Stripe test keys, Twilio test credentials) through from `.env.example` as real test-mode values, not placeholders. Never write a literal secret into compose, the Makefile, or the devcontainer.
5. Run migrations and load seed data so the local database is populated after setup. Source migrations from `db-schema` and seed from spgr-write-seed-data output.
6. Write `.devcontainer/devcontainer.json` via spgr-write-file so the same toolchain, service stack, and post-create setup run in Codespaces and Remote Containers identically to a local run.
7. Verify the clean-machine guarantee. From a clean checkout, run `make install` then `make dev`, then run `make verify` through spgr-run-tests or CI. `make verify` confirms the application is running and serves a basic request. Measure clone-to-running wall-clock time.
8. Confirm idempotence. Run `make install` a second time and confirm it succeeds and produces the same result without error.
9. Record the scaffold and the verified clone-to-running time with spgr-log-decision, then call spgr-validate-artifact for envelope-only validation of the change record.

## Notes

- Output type is SOURCE or CONFIG (local dev scaffold written via spgr-write-file and verified by `make verify` through spgr-run-tests or CI). No content schema is registered for this output, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered.
- Escalate via spgr-escalate when verified clone-to-running exceeds 15 minutes on a supported OS, when a required external service has no test-mode credential or local mock available, when `make verify` cannot reach a running application, or when a setup target cannot be made idempotent. Return the precise blocker rather than shipping a setup that fails from a clean machine.
- No literal secrets in `docker-compose.yml`, the `Makefile`, the devcontainer, or any committed file. Every credential resolves from `.env`, and `.env` is never committed.
- Supported OS targets are macOS and Linux. State any deviation explicitly rather than assuming a Windows path works.
- Tag the DevOps Agent and any owning vertical with spgr-tag-vertical-agent when a service version pin conflicts with the confirmed tech stack.
