---
name: spgr-write-cd-pipeline
description: Write the continuous delivery pipeline configuration that auto-deploys to staging on every merge to main and gives a controlled, audited, zero-downtime path to production, with migrations-before-code ordering, post-deploy smoke tests with automatic rollback, drift detection, and deployment notifications. Use when the DevOps agent wires CD from a tested CI build artifact and a deployment target inventory, or when the QA agent has supplied the smoke-test pass/fail contract and the release path needs to be built and verified before a release proceeds.
---

# write-cd-pipeline

## Purpose

Produce the CD pipeline configuration for one application. Continuous delivery keeps main deployable at all times, so a merge to main auto-deploys to staging, and production deploys only on a deliberate signal (manual trigger, release tag, or approval gate). Run migrations before new code so the old running version stays compatible with the new schema and rollback works. Make the whole pipeline idempotent so the same artifact version deployed twice yields the same outcome, and record every deployment as a permanent log entry.

## Inputs

| Field | Description |
|-------|-------------|
| `build_artifact` | Tested CI output: container image tag or build artifact hash to deploy. |
| `target_inventory` | Environment specs for dev, staging, and production. |
| `promotion_strategy` | Auto to staging, deliberate signal to production (trigger, tag, or approval gate). |
| `migration_strategy` | Migration runner and rollback capability, including backward-compatibility status. |
| `zero_downtime_strategy` | Blue/green or canary preference for production. |
| `smoke_test_contract` | QA-supplied smoke-test commands and pass/fail contract for the post-deploy stage. |
| `release_manifest` | Expected artifact version per environment, used for post-deploy drift detection. |
| `notification_channel` | Team channel for deployment-event posts. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `cd-pipeline` | Pipeline source files (for example a workflow YAML and deploy scripts) defining the staging job, the production job, the deployment strategy, notifications, and logging. |

The pipeline source covers:
- Staging job, auto-triggered on merge to main: run migrations, deploy the new version, run smoke tests, roll back automatically on smoke-test failure.
- Production job, triggered by manual approval or release tag: same sequence as staging plus pre-deploy checks (release-checklist validation, rollback plan confirmed) and explicit human sign-off.
- Blue/green or canary configuration with traffic-shifting logic and automatic rollback on health-check failure.
- Deployment notification posting environment, artifact version, deployer identity, start time, and outcome to the notification channel.
- Artifact versioning, tagging each deployment with the exact version deployed and recording it in the deployment log.

## Procedure

1. Read any existing pipeline files and project structure with spgr-read-file before writing, to match conventions and avoid clobbering unread files.
2. Read the smoke-test contract from QA. If it is missing, raise spgr-escalate, because the post-deploy stage is required and cannot be guessed. Tag QA with spgr-tag-vertical-agent if the contract is ambiguous.
3. Write the staging job to trigger automatically on merge to main. Order the steps as migrations, then new-version deploy, then smoke tests. Keep the ordering migrations-before-code so the old running version stays compatible with the new schema.
4. Check the migration strategy for backward compatibility. A migration that is not backward-compatible needs a multi-step deployment process and must be flagged before the migration is written, so raise spgr-escalate and tag the Backend Developer agent rather than encoding a single-step deploy.
5. Make the smoke-test stage required, not optional. On smoke-test failure after staging deploy, roll back automatically and notify the deploying agent, so staging stays in a working state.
6. Write the production job to require a deliberate signal: manual trigger, release tag, or an approval gate. Never make production fully automatic. Add the pre-deploy checks (release-checklist validation, rollback plan confirmed) and the explicit human sign-off via spgr-notify-human, then run the same migrate-deploy-smoke sequence as staging.
7. Configure the zero-downtime strategy for production. For blue/green, provision a complete new environment and switch traffic, with automatic rollback on health-check failure. For canary, shift traffic gradually and add canary analysis that compares error rate and latency between the canary slice and the stable slice, aborting the rollout when the canary slice is statistically worse. Record the strategy choice with spgr-log-decision.
8. Confirm a tested rollback path exists for the chosen strategy. A deploy is not valid without a rollback that has been exercised, so wire the rollback trigger and verify it before treating the production job as complete.
9. Make the pipeline idempotent: running it twice for the same artifact version must produce the same outcome as running it once, to prevent partial deployment states.
10. Add the deployment notification step posting to the notification channel, and add the immutable deployment log entry recording environment, artifact version, initiating agent or trigger, start timestamp, completion timestamp, outcome (success, failure, or rollback), and smoke-test results.
11. Add a post-deploy drift-detection step that compares the deployed artifact version against the expected version in the release manifest, surfacing cases where a failed rollback left a version mismatch.
12. Add a deployment-frequency dashboard tracking the DORA deployment-frequency metric (deploys per day or week) as a leading indicator of delivery health.
13. Reject any literal secret in the pipeline. Source every credential from the secret store, never from inline values or committed config. Confirm the build meets the ten-minute build rule, since a slow pipeline erodes the deployable-main guarantee.
14. Write the pipeline files with spgr-write-file, then verify the staging path end to end (migrate, deploy, smoke, rollback on induced failure) in CI before treating the pipeline as complete. If any required input is missing or contradictory, stop and raise spgr-escalate with the precise list of what is missing rather than guessing.

## Notes

- The output is source or config (pipeline YAML and deploy scripts), verified by a CI run of the staging path rather than by an envelope content schema. There is no registered content schema for cd-pipeline yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered.
- No literal secrets in any pipeline or IaC. Source credentials from the secret store.
- Staging auto-deploys. A merge to main is the confidence signal, and a change not ready to ship is not ready for main. The trunk-based deployable-main model this pipeline depends on is defined in `.claude/references/git-workflow.md`.
- Production needs a deliberate signal and human sign-off via spgr-notify-human. It is appropriate care, not bureaucracy.
- A deploy is valid only with a tested rollback. Verify the rollback before the production job is treated as complete.
- Version every deployment under semantic versioning and record it in the immutable deployment log.
- Record the blue/green-versus-canary choice and any consequential pipeline decision with spgr-log-decision.
