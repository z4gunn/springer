---
name: spgr-run-deployment
description: Execute a staging or production deployment by following the release runbook step by step, enforcing every verification gate as a hard stop and executing the rollback plan the moment a gate fails. Use when the DevOps Agent has a confirmed runbook, rollback plan, release-readiness confirmation, and a versioned build artifact to ship.
---

# run-deployment

## Purpose

Execute a deployment by following the release runbook faithfully and making the binary rollback-or-continue decision at each verification gate without hesitation. The job is procedural, not creative. The risk is not the steps but the temptation to proceed past a failed gate because it is probably fine. Enforce the gate as a hard stop. Produce a deployment execution log that records every step, every command, and every verification result so the outcome is auditable. Production runs require human confirmation before execution begins. Staging runs can proceed automatically.

## Inputs

| Field | Description |
|-------|-------------|
| `deployment-runbook` | The step-by-step release procedure from spgr-write-deployment-runbook, read with spgr-read-artifact |
| `rollback-plan` | The tested rollback procedure from spgr-write-rollback-plan, read with spgr-read-artifact |
| `release-readiness` | The readiness confirmation from spgr-validate-release-readiness, read with spgr-read-artifact |
| `release-artifact` | The versioned build artifact or container image to deploy, identified by its semantic version |
| `target-environment` | `staging` or `production` |
| `canary-config` | Optional. Traffic percentage, baseline error-rate window, and divergence threshold for progressive rollout |

## Outputs

| Artifact | Description |
|----------|-------------|
| `deployment-log` | Envelope artifact written with spgr-write-artifact, holding a timestamped record of each step, the command run, its result, and the verification verdict at each gate |
| `smoke-test-results` | Post-deployment smoke test output from spgr-run-smoke-test, attached to the deployment log |
| `deployment-outcome` | Outcome record of `success`, `partial`, or `rolled-back`, written back to the release artifact via spgr-write-file |

## Procedure

1. Read the runbook, rollback plan, and readiness confirmation with spgr-read-artifact. If any is missing, unconfirmed, or the readiness verdict is not a pass, stop and call spgr-escalate with the precise list of what is missing or failing. Do not deploy on incomplete input.
2. Confirm the rollback plan has a tested-rollback marker. A deploy is not valid without a rollback that has been verified to work. If the rollback is untested, call spgr-escalate and stop.
3. Confirm the release artifact carries a semantic version. If it does not, call spgr-escalate and stop.
4. If `target-environment` is `production`, call spgr-notify-human and wait for explicit confirmation before any step runs. If `staging`, proceed automatically.
5. Open the deployment log with spgr-write-artifact and record the start time, the release version, the target environment, and the runbook version. Call spgr-notify-human (or the deployment Slack channel) at deployment start with a link to the log.
6. If `canary-config` is present, route the configured traffic percentage to the new version first. Compare the canary error rate against the baseline over the configured window. If the canary error rate diverges beyond the threshold, trigger rollback per step 9 immediately. Only on a clean canary, proceed to full rollout.
7. Execute each runbook step in order. Log the command, the timestamp, and the result for every step, not just the final outcome. Toggle feature flag states through spgr-define-feature-flag where the runbook sequences a flag change, rather than as a separate manual action.
8. At every verification gate (health check, error-rate check, smoke test via spgr-run-smoke-test), treat the gate as a hard stop. A passing gate continues. A failing gate triggers rollback immediately, not after waiting to see whether it clears. Notify the channel at each major stage completion.
9. On any gate failure, execute the rollback plan at once. Log each rollback step and its result. Set `deployment-outcome` to `rolled-back`, write it back to the release artifact with spgr-write-file, notify the channel of the rollback with a link to the log, and call spgr-escalate with the failing gate and its evidence.
10. On a clean run through all gates, run the post-deployment smoke test with spgr-run-smoke-test and attach the results. Set `deployment-outcome` to `success` (or `partial` if any non-gating step degraded), write it back to the release artifact, and notify the channel of the final outcome with a link to the log.
11. Validate the deployment log inline with spgr-validate-artifact before marking it confirmed. Version it with spgr-version-artifact and record the rollback-or-continue decision at each gate via spgr-log-decision.

## Notes

- Output type: the deployment-log is an envelope artifact, and the deployment-outcome write-back plus any pipeline or IaC change are source or config output verified by CI. The `deployment-log` type has no registered content schema, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered.
- Every verification gate is a hard stop. Never proceed past a failed gate. Rollback on gate failure is immediate.
- A deploy is not valid unless the rollback has been tested first. Releases carry a semantic version.
- No literal secrets in any command, pipeline step, or config touched during the deployment. Reference secrets through the environment or secret store.
- Log at the step level. A timestamped record of every command and its result is the artifact, not a single success line.
- Tag the Resilience and Observability verticals through spgr-tag-vertical-agent when a gate failure points at a missing timeout, retry, or alert rather than a release defect.
