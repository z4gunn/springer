---
name: spgr-write-dockerfile
description: Write a secure multi-stage Dockerfile plus a matching .dockerignore that builds a production container image with a minimal runtime layer, a pinned base image, a non-root user, and no embedded secrets. Use when the DevOps agent containerizes a service, when the Backend Developer agent supplies a service's runtime and build dependencies for packaging, or when the Security agent needs the image hardened to non-root and pinned-base before a release.
---

# write-dockerfile

## Purpose

Produce the container build definition for one service. The Dockerfile is the deployment unit, so its discipline is a security and cost concern, not a convenience. Separate the build environment from the runtime environment with multi-stage builds, run the process as a dedicated non-root user, pin the base image to a patch version and OS variant, and ship only what the service needs to run. Pair every Dockerfile with a .dockerignore so the build context stays small and test fixtures or secrets never reach a layer.

## Inputs

| Field | Description |
|-------|-------------|
| `service_type` | Web API, background worker, CLI tool, or similar. |
| `runtime` | Language runtime and exact version (for example Python 3.12, Node 22, Go 1.22). |
| `runtime_dependencies` | System packages the service needs at run time. |
| `build_dependencies` | Tools needed only to compile, transpile, or install, never at run time. |
| `listen_port` | Port the service listens on, for the EXPOSE declaration. |
| `health_endpoint` | Path the HEALTHCHECK calls (for example `/healthz`). |
| `size_budget` | Optional runtime image size ceiling for the CI budget check. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `Dockerfile` | Multi-stage build: a builder stage on a full toolchain image, then a runtime stage on a minimal distroless or slim base with a non-root user, pinned base, EXPOSE, and HEALTHCHECK. |
| `.dockerignore` | Excludes `.git/`, `node_modules/`, `__pycache__/`, `.env` files, test files, and docs from the build context. |

## Procedure

1. Read any existing Dockerfile and project structure with spgr-read-file before writing, to match conventions and avoid clobbering unread files.
2. Resolve the base image to a full version tag that includes the patch version and the OS variant (for example `python:3.12.3-slim-bookworm`). Reject `latest` and minor-only tags such as `python:3.12`.
3. Write the builder stage from the full runtime image. Install build dependencies, then compile, transpile, or install application dependencies, producing the build artifacts.
4. Write the runtime stage from a minimal base (distroless or slim). Copy only the compiled artifacts and runtime dependencies from the builder stage. Do not include the compiler, build tools, package manager, or development dependencies.
5. Create a dedicated application user and group, set ownership of copied files to that user, and switch to it with `USER` so the process runs as non-root. Grant the user write access only to the directories the service must write to (logs, temp, uploads).
6. Add `EXPOSE` for the listen port and a `HEALTHCHECK` that calls the health endpoint.
7. For any build-time secret (for example a private registry token), use a BuildKit `--secret` mount. Never place a secret in `ENV` or `ARG`, because both persist in the image layer history.
8. Write the `.dockerignore` alongside the Dockerfile with the exclusions above.
9. Write both files with spgr-write-file, then build the image to confirm it succeeds. Tag the verification with spgr-run-security-scan against the runtime image and fail on Critical or High OS-level CVE findings. If a size budget is set and the runtime image exceeds it, stop and report the largest layers.
10. If a required input is missing or contradictory (for example a build step is declared but no build dependencies are given, or no runtime version is supplied), stop and raise spgr-escalate with the precise list of what is missing rather than guessing a base image or version. If the chosen base or non-root model conflicts with a security constraint, tag the Security agent with spgr-tag-vertical-agent before finalizing. Record any consequential base-image or hardening choice with spgr-log-decision.

## Notes

- The output is source code (a Dockerfile and a .dockerignore), verified by a successful image build, spgr-run-security-scan, and CI rather than by an envelope schema.
- Multi-stage is mandatory for any language with a build step. The runtime image must not carry the toolchain.
- `EXPOSE` is documentation only and does not publish the port. Port publishing is a runtime concern.
- Build from an organization-owned hardened base image where one exists for the runtime, rather than directly from the public registry.
- Image vulnerability scanning and the size budget are CI gates wired through spgr-run-security-scan and the pipeline, not steps the developer runs by hand on every change.
