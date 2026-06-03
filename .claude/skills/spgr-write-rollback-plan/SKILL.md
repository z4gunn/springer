---
name: spgr-write-rollback-plan
description: Produce a rollback-plan artifact for one release, defining the exact reverse sequence to restore the previous known-good state across application code, database migrations, feature flags, and external configuration, with per-step verification, irreversible changes flagged with a forward-fix mitigation, expected rollback duration, minimum operator count, staging-drill timestamps, and automated trigger conditions wired to observability signals. Use when the DevOps Agent prepares a release for the same human gate as the deployment runbook and must specify how to undo the change before it ships, or when a release includes a database migration, a feature-flag change, or an external config change whose reversal mechanics must be settled before the deployment window opens.
---

# write-rollback-plan

## Purpose

Define how to undo one release before the question becomes urgent. A rollback is always easier to plan before deployment than to improvise during an incident. The plan covers four change classes with different reversal mechanics and different irreversibility constraints: application code, database schema, feature flags, and external service or secrets configuration. The plan is approved by the human at the same gate as the release checklist, not after the deployment has started, so the absence of a tested rollback is itself a release blocker that must surface before the window opens.

## Inputs

| Field | Description |
|-------|-------------|
| `deployment_runbook` | The runbook artifact for the corresponding release. The rollback trigger conditions mirror its conditions and the rollback sequence reverses its deploy sequence |
| `migration_list` | Every database migration in the release, each marked reversible or irreversible |
| `flag_changes` | Feature-flag changes in scope, including any flag usable as an emergency rollback handle |
| `config_changes` | External configuration or secrets changes in scope |
| `service_drill_log` | Per service, the timestamp of the last staging rollback drill, used to flag stale rollback procedures |

## Outputs

| Artifact | Description |
|----------|-------------|
| `rollback-plan` | Envelope artifact covering trigger conditions, the reverse-order rollback sequence with migration reversal, per-step verification of restored state, irreversible changes flagged with forward-fix mitigation, expected duration, minimum operator count, staging-drill timestamps per service, and automated-trigger conditions tied to observability signatures |

## Procedure

1. Read the inputs. Load the runbook with `spgr-read-artifact` and any prior rollback-plan version, and read `migration_list`, `flag_changes`, `config_changes`, and `service_drill_log` with `spgr-read-file`. If the runbook is missing or the migration list does not state reversible or irreversible per migration, stop and escalate with `spgr-escalate` naming the missing input.
2. Mirror the trigger conditions. Copy the rollback trigger conditions from the runbook so the two artifacts agree on when a rollback starts. Add the automated-trigger conditions: for each failure signature that observability can detect (for example a sustained error-rate spike past threshold for a set duration), state the signal, the threshold, and whether it auto-triggers rollback without an operator or only pages one.
3. Build the rollback sequence in reverse order of deployment. For each step record the action, the change class, the command or control to use, and the per-step verification that confirms the previous state is restored. Reverse database migrations where the migration is reversible.
4. Flag irreversible changes. For every migration or config change that cannot be reversed, mark it and attach a forward-fix path: the corrective migration to re-run, the data-reconciliation steps, or the fallback feature flag that disables the new behavior. An irreversible change with no documented forward-fix is a blocking gap.
5. Identify feature-flag rollback handles. Feature-flag rollback is usually the fastest path, since flipping a flag disables new behavior without touching code or schema. List each flag that can serve as an emergency handle and the value to set.
6. Record the operational envelope. State the expected rollback duration and the minimum operator count. Carry the per-service last-drill timestamp from `service_drill_log` into the plan and flag any service whose procedure is stale relative to the release date.
7. Gate on staging-tested rollback. A rollback that includes an irreversible change must be drilled in staging before the production deployment. If the rollback cannot be tested in staging, do not silently proceed. Surface that risk to the human with `spgr-notify-human` before the deployment window, and mark the affected sections `needs-human-input` in the confidence map.
8. Tag the DevOps vertical with `spgr-tag-vertical-agent` when a config or secrets change needs sign-off, and tag the owning vertical for any migration whose reversal touches its domain.
9. Write and validate. Emit the artifact with `spgr-write-artifact` and run `spgr-validate-artifact` inline. Record the approval-gate decision and the staging-drill result with `spgr-log-decision`, and version the artifact with `spgr-version-artifact` on any re-issue.

## Notes

- Output type is an envelope artifact. The `rollback-plan` type has no registered content schema yet, so `spgr-validate-artifact` applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered. Still call it.
- The deploy is not valid until its rollback is tested. Treat an untested rollback on an irreversible release as a blocking finding routed to the human, not an advisory note.
- Use the confidence map honestly: a step verified by a completed staging drill is `confirmed`, a step that depends on an untested reversal is `proposed`, and a step blocked on an untestable rollback is `needs-human-input`.
- Do not fill an unknown reversal mechanic with an assumption. If a migration's reversibility is unstated, escalate rather than guessing.
