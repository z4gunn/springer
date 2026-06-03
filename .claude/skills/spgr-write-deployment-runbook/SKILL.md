---
name: spgr-write-deployment-runbook
description: Produce a deployment-runbook artifact for one release, covering the pre-deployment checklist, the ordered deployment sequence, a verification gate after every step, smoke-test instructions, measurable rollback trigger conditions, an on-call escalation path, and an execution-log format for live audit. Use when the DevOps Agent prepares a release and the runbook is the required gate before the release checklist can be marked ready, or when the rollback plan needs the documented state transitions it must undo.
---

# write-deployment-runbook

## Purpose

Produce the step-by-step runbook that turns a release from a from-memory manual procedure into a repeatable, auditable process any operator can execute. The runbook fixes the deployment sequence, pairs every step with a verification gate, and states the exact conditions that trigger rollback. It is also the first input to the rollback plan, because it defines the state transitions rollback must reverse. Write it as an envelope artifact for one named release version, not as a reusable template.

## Inputs

| Field | Description |
|-------|-------------|
| `architecture-diagram` | Services, databases, queues, and external dependencies. Read via spgr-read-artifact (system-diagram or infrastructure-diagram). |
| `ci-pipeline-config` | The CD pipeline configuration that the runbook steps invoke. Read via spgr-read-file. |
| `release-scope` | What changed in this release: services, migrations, feature flags, config. |
| `environment-topology` | Staging-versus-production differences that change the sequence or the gates. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `deployment-runbook` | Envelope artifact for one release version. Sections below. Write via spgr-write-artifact with inline spgr-validate-artifact. |

The runbook body covers, in order:
- Pre-deployment checklist: health checks green, freeze window confirmed, stakeholders notified, feature flags staged.
- Deployment sequence: order of service restarts, migration execution, cache invalidation.
- Per-step verification gate: the exact check to pass after each step before proceeding.
- Smoke-test execution instructions: which suite to run and how (reference spgr-run-smoke-test).
- Rollback trigger conditions: specific, measurable thresholds.
- On-call contact list and escalation path.
- Execution-log format: a per-step table with timestamp and outcome columns operators fill in during a live deployment.

## Procedure

1. Read the architecture diagram, pipeline config, release scope, and environment topology through spgr-read-artifact and spgr-read-file. If the release scope does not name every changed service, migration, flag, and config key, stop and call spgr-escalate, because an incomplete scope yields a runbook that misses a state transition.
2. Write the pre-deployment checklist. Each item is a binary check an operator can confirm, not a reminder. Include the freeze window and the stakeholder notification.
3. Order the deployment sequence from the architecture dependencies. Place each migration, restart, and cache invalidation in the order that keeps the system serving. Prefer blue-green migration patterns, where a backward-compatible column addition ships before the code that reads it.
4. For every step in the sequence, write one matching verification gate. A step is not complete without its gate. "Deploy service X" pairs with "verify service X health check returns 200 and p95 response time is under the threshold from the SLO spec." A sequence step with no gate is a defect, so do not emit the runbook until every step has one.
5. Flag any migration that cannot be rolled back with an explicit warning at the top of its step, naming why it is irreversible and what manual recovery it forces.
6. List every feature flag that gates new behavior with its key, current state, and intended post-deployment state. Reference the flag spec from spgr-define-feature-flag where one exists.
7. Add the smoke-test instructions and the rollback trigger conditions. Every trigger is specific and measurable, for example "error rate exceeds 1 percent for 3 consecutive minutes after deployment" or "any health check fails twice in a row." Reject vague triggers like "if something looks wrong."
8. Add the on-call contact list and escalation path, and the execution-log table that operators timestamp per step during the live run.
9. Version the runbook to the release it describes through spgr-version-artifact. A runbook written for one version is not reused for the next without review, so tie the version field to the release tag and follow semantic versioning.
10. Validate the artifact inline with spgr-validate-artifact and log the runbook completion with spgr-log-decision. The runbook completion is the required gate before the release checklist is marked ready, so do not signal ready until validation passes.

## Notes

- Output type is an envelope artifact. There is no registered content schema for deployment-runbook yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered. Still call it.
- Every deployment step carries a verification step. The pairing is the core contract this skill enforces, not a guideline.
- Rollback triggers must be measurable. A threshold with a number and a duration, not a feeling.
- Tag the Resilience and Observability vertical agents through spgr-tag-vertical-agent when the rollback triggers depend on SLO thresholds or alert definitions they own.
- An irreversible migration is called out explicitly at its step. Backward-compatible blue-green migration is the preferred pattern.
- Notify the human through spgr-notify-human when the release includes an irreversible migration, since that raises the stakes of the deployment decision.
