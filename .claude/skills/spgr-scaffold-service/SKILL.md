---
name: spgr-scaffold-service
description: Add a new service or module to an existing project as source code, matching the project's established conventions exactly, with route or handler registration, controller, service layer, optional data access layer, error handling, structured logging, a contract-documenting README stub, and a running smoke test that starts the service and confirms a health-check response. Use when the Backend Developer agent must add a new service or module to an existing project, or when the QA or code-reviewer agent needs the service skeleton built to project convention before feature code or review.
---

# scaffold-service

## Purpose

Add a new service or module to an existing project so it is indistinguishable from the existing services in structure and wiring. A service added off-convention creates structural inconsistency that raises cognitive load for every contributor and makes later tooling harder to build. Read the existing project to learn its conventions, then match them exactly. Include every standard file from the start, including error handling and logging, because a service without them fails on its first bug. Confirm the smoke test actually starts the service and gets a valid health-check response before handing off.

## Inputs

| Field | Description |
|-------|-------------|
| `project-structure` | The existing project tree. The conventions to follow: directory layout, file naming, dependency injection pattern, error and logging conventions, and how routes register. Read with spgr-read-file. |
| `service-spec` | What the service does, its domain boundaries, and its interface (inputs accepted, outputs produced, failure modes). |
| `tech-stack` | The stack of the existing project. The same stack the new service uses. Read the tech-stack-decision with spgr-read-artifact when present. |

## Outputs

| Artifact | Description |
|----------|-------------|
| New service directory (source code) | All standard files matching project convention: route or handler registration wired into the project router, a controller or handler at the request and response boundary, a service layer for business logic, a data access layer when the service owns data, error handling middleware per project convention, structured logging instrumentation per project convention, a README stub documenting the service contract, and a smoke test that starts the service, hits the health-check endpoint, and asserts a valid response. Each file written with spgr-write-file. |

## Procedure

1. Read the existing project structure with spgr-read-file. Catalog the actual conventions in use: directory layout, file and module naming, dependency injection pattern, the error handling and logging approach, and the route registration mechanism. Follow these conventions, not the agent's preferred ones.

2. Read the service-spec and confirm it names the domain boundaries and the interface (inputs, outputs, failure modes). If the spec is missing the interface, the domain boundary, or conflicts with an existing service that already owns the same domain, stop and raise spgr-escalate with the precise gap. Do not assume a boundary.

3. Confirm the new service uses the same stack as the existing project. Read the tech-stack-decision with spgr-read-artifact when present and reference its schema through spgr-validate-artifact rather than inlining fields. If the spec implies a different stack, stop and raise spgr-escalate rather than introducing a second stack.

4. Run the service generator script for the project's common service template so the skeleton lands in seconds and stays consistent across services. See [scripts/scaffold-service.sh](scripts/scaffold-service.sh). When no template matches the project's convention, generate the files by hand from the cataloged conventions in step 1 and raise spgr-escalate so a template can be added rather than improvising a one-off layout.

5. Generate the service directory and every standard file: route or handler registration, controller or handler, service layer, data access layer when the service owns data, error handling middleware, and logging instrumentation. Include all standard files from the start. Do not omit error handling or logging. Build only what the service-spec requires, no speculative endpoints (YAGNI).

6. Register the route explicitly, wired into the project's router. Use auto-discovery only when auto-discovery is the established project convention.

7. Write the README stub documenting the service contract: its purpose, the inputs it accepts, the outputs it produces, and its failure modes.

8. Write the smoke test test-first, before any handoff is considered done. The smoke test must start the service, hit the health-check endpoint, and assert a valid response. A check that only confirms the file compiles is not a smoke test and fails the gate below.

9. Validation gate. Run the smoke test with spgr-run-tests and confirm it starts the service and gets a valid health-check response. Run the project linter and formatter and confirm a clean pass on the new files. If any check fails, fix the service and re-run. Do not hand off a service that does not pass the smoke test on a clean run.

10. Record the cataloged conventions followed, the template used, and any spec gap that shaped the result with spgr-log-decision so the reasoning is traceable.

## Notes

- The output is source code (the service skeleton, wiring, and smoke test), verified by spgr-run-tests and CI rather than by an envelope schema.
- Honor the read-before-write contract: read the project structure and any input artifact before generating files, reading through spgr-read-file and spgr-read-artifact and writing through spgr-write-file.
- Keep the tree lint and format clean before commit and make one logical change per commit.
- The smoke-test-result is written via spgr-write-artifact with its registered schema added in a later increment.
