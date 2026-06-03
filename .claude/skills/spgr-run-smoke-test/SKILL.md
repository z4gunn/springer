---
name: spgr-run-smoke-test
description: Run a minimal fast post-deployment check of the critical paths and return a GO or NO-GO verdict that gates the release, writing both the smoke test suite as source code and a smoke-test-result artifact, and signaling automatic rollback on any failure. Use when the DevOps Agent needs a blocking post-deployment gate after a staging or production deploy or before shifting traffic to a canary slice, or when the QA Agent authors or maintains the smoke test suite and its critical-path scope.
---

# run-smoke-test

## Purpose

Confirm a deployment is alive and the critical path works before live traffic reaches it. A build can pass CI and staging and still fail in a target environment from configuration drift, missing environment variables, secrets that did not propagate, or infrastructure mismatch. This skill runs the smoke suite as a synchronous deployment gate, produces a single GO or NO-GO verdict, and on NO-GO emits the rollback trigger so the pipeline reverts without waiting for a human. Scope is deliberately small. The smoke suite confirms the deployment is alive. Comprehensive regression coverage lives in the E2E suite that runs nightly, not here.

## Inputs

| Field | Description |
|-------|-------------|
| `environment` | Target environment URL and the secrets-manager reference for the smoke test account credentials. Same skill runs against staging, production, and a canary slice. |
| `critical_paths` | The 3 to 7 most important user-facing actions that must work for the deployment to count as live. Defines the suite scope. |
| `artifact_version` | The deployment artifact version under test, recorded in the result and the deployment log. |
| `mode` | `standard` (run after a full deploy) or `canary` (run against the canary slice before traffic shift). |

## Outputs

| Artifact | Description |
|----------|-------------|
| Smoke test suite | Source code. The 5 to 10 checks that exercise the health endpoint, authentication, and at least one complete core workflow. Written via spgr-write-file. |
| smoke-test-result | Per-check pass/fail with measured response time and failure detail, health-check status, authentication status, core-workflow status, total duration, and the overall GO or NO-GO verdict with a rollback trigger signal. Written via spgr-write-artifact. |

## Procedure

1. Read the environment and critical-path inputs with spgr-read-file. Resolve smoke test account credentials from the secrets-manager reference, never from inline literals. The account carries only the minimal permissions needed to exercise the critical paths and is provisioned in every environment.

2. When authoring or maintaining the suite (QA Agent path), write the smoke checks as source via spgr-write-file. Cap the suite at 5 to 10 checks. This is not a regression suite. Keep each check independent so a single failure names the exact broken path. Confirm the suite scope against spgr-write-acceptance-criteria for the critical-path stories so the checks track the actual completion contract.

3. Run the suite against the target environment via spgr-run-tests. Cover three categories at minimum: the API health endpoint returns 200 with the expected payload, the smoke account authenticates and receives a valid session token, and at least one complete primary user action succeeds end to end (for example create a record then retrieve it). Health and smoke are distinct. A health check proves the service is running. A smoke check proves the service is working. Run both.

4. Enforce the time budget. Total runtime must stay under 3 minutes so the gate is synchronous rather than skipped. If the run exceeds 3 minutes, escalate via spgr-escalate to trim the critical-path scope or optimize the implementation rather than silently letting the gate slow the pipeline.

5. Compute the verdict. GO only when every check passes. Any single failure is NO-GO. There is no exception for a quick fix or a minor config change. Every deployment runs the suite.

6. Write the smoke-test-result via spgr-write-artifact with inline spgr-validate-artifact, recording per-check status and response time, the overall verdict, the artifact version, the deploying agent, the environment, the timestamp, and total duration. Log the verdict to the deployment log via spgr-log-decision so deployment history carries a quality signal for later incident investigation.

7. On NO-GO, emit the rollback trigger signal in the result immediately so the pipeline reverts without human intervention. In `canary` mode, a NO-GO aborts the rollout before any user traffic shifts to the new version.

8. On a production NO-GO, raise a P0 via spgr-escalate and page the on-call agent through spgr-notify-human with the specific check that failed, the environment, the artifact version, and the timestamp. Rollback removes the urgency but the failure still requires a post-mortem.

## Notes

- The smoke test suite is source code, verified by spgr-run-tests and CI rather than by an envelope schema.
- The smoke-test-result artifact type is not yet in the schema registry at /Users/gunderer/Repos/springer/schemas/. Write it via spgr-write-artifact and add its registered schema, referenced through spgr-validate-artifact, in a later increment.
- The result verdict is the deployment go/no-go signal. NO-GO blocks the release and triggers automatic rollback. Do not mark a result confirmed on any failed check.
- YAGNI. Build only the checks the critical paths require. Adding regression coverage here breaks the time budget and defeats the gate.
