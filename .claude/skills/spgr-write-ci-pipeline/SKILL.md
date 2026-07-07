---
name: spgr-write-ci-pipeline
description: Produce the CI pipeline configuration that builds, lints, tests, and scans on every push, with a fast run under 3 minutes and a full run under 10 minutes per the XP ten-minute build rule. Use when the DevOps Agent must stand up or change the automated quality gate from a confirmed tech stack and test-suite structure.
---

# write-ci-pipeline

## Purpose

Write the CI pipeline configuration that gives every push the same automated quality treatment: build, lint, test, coverage gate, and security scan. The contract that matters is timing. The fast run (build, lint, unit tests) stays under 3 minutes on every push, and the full run (all stages) stays under 10 minutes on PR and merge. Past that budget, agents stop waiting for CI and start merging speculatively, and the gate stops working. This skill writes pipeline source files, it does not author the linters, tests, or scanners it invokes. Those commands and thresholds come from the QA and Security agents.

## Inputs

| Field | Description |
|-------|-------------|
| `tech-stack` | Languages, frameworks, and runtimes. From the confirmed tech-stack-decision artifact via spgr-read-artifact. |
| `test-suite-structure` | Unit, integration, and E2E runners with their commands and approximate runtimes. Supplied by the QA Agent. |
| `coverage-floor` | The minimum coverage percentage below which the unit-test stage fails. Supplied by the QA Agent. |
| `lint-config` | Linter and formatter tools and their config file locations. |
| `security-scan-requirements` | SAST tool (Semgrep), dependency scanner (Snyk or Dependabot), and the finding severity that gates. Supplied by the Security Agent. |
| `ci-platform` | GitHub Actions, CircleCI, Buildkite, or equivalent. |

## Outputs

| Artifact | Description |
|----------|-------------|
| CI pipeline config file(s) | Written with spgr-write-file to the platform's config path (for example `.github/workflows/`). Source output, not an envelope artifact. |
| Runtime version pin | A `.tool-versions` or `.nvmrc` file pinning runtime versions to production parity, if not already present. |

## Procedure

1. Read the tech-stack-decision with spgr-read-artifact. Confirm the test-suite structure, coverage floor, lint config, and security-scan thresholds are all supplied. If any input is missing or contradictory, stop and call spgr-escalate with the precise list of what is missing rather than guessing a command or threshold.

2. Pin the runtime. Write `.tool-versions` or `.nvmrc` with the same language runtime versions used in production, and pin the same database version for integration tests. Pin every container image to a version tag, never `latest`. Run jobs in containers so host state cannot affect builds.

3. Author the staged pipeline with fail-fast ordering:
   - Stage 1 Build: install dependencies, compile or transpile, produce the build artifact. Fail immediately and skip all later stages if the build fails.
   - Stage 2 Lint and typecheck: run the linter and formatter check, fail on any lint error or unformatted file. For a TypeScript project, also run `tsc --noEmit` and fail on any type error, per `.claude/references/typescript-standards.md`. Run this stage in parallel with unit tests, the one allowed exception to fail-fast since both are fast and independent.
   - Stage 3 Unit tests: run the fast unit suite, generate the coverage report, fail if coverage drops below the floor. Budget under 3 minutes.
   - Stage 4 Integration tests: run against the pinned test database. Budget under 7 minutes.
   - Stage 5 SAST and dependency audit: run Semgrep and the dependency scanner. Fail on Critical or High findings per the Security Agent thresholds.

4. Split into two runs. A fast run (build, lint, unit tests, under 3 minutes) triggers on every push to a feature branch. A full run (all five stages, under 10 minutes) triggers on PR and on merge to main.

5. Add a test impact analysis step for feature-branch pushes that maps changed files to their covering tests and runs only those, falling back to the full suite for merges to main.

6. Add a PR size check that flags any PR over 500 changed lines, excluding generated files, as a soft warning. This does not block.

7. Cache aggressively. Configure the dependency cache and build cache, keyed so a lockfile change invalidates them. Dependency installation from scratch is the most common source of avoidable CI latency.

8. Inject every secret from the CI platform secrets store as an environment variable. Write no literal secret value into any config file. The config is committed and visible to all contributors. Verify this before writing.

9. Emit a coverage report artifact and a test results artifact on every run, retained at least 7 days, linked from the PR status check.

10. Verify the budget. Trigger the pipeline (or run spgr-run-tests against the config) and measure actual fast-run and full-run duration on the first run. If the fast run exceeds 3 minutes or the full run exceeds 10 minutes, optimize caching and stage parallelism before declaring the work done. If the budget cannot be met within the approved architecture, call spgr-escalate. Log the platform and timing decisions with spgr-log-decision.

## Notes

- Output type is source or config (pipeline YAML), so it is written via spgr-write-file and verified by a real CI run, not by spgr-validate-artifact. There is no envelope artifact for this skill.
- The ten-minute build rule, no-literal-secrets rule, and production environment parity are inviolable DevOps constraints. A pipeline that violates any of them is not done.
- Treat the pipeline config as production code. It is reviewed in PRs and a change to it triggers its own CI run by definition.
- Tag the Security Agent with spgr-tag-vertical-agent to confirm the SAST and dependency thresholds before marking the pipeline confirmed. Coverage floor and test commands come from the QA Agent.
