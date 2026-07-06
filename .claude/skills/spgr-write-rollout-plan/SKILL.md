---
name: spgr-write-rollout-plan
description: Produce a rollout-plan artifact defining the staged release schedule for a feature flag, with an ordered stage sequence, minimum dwell times, green-metric advancement criteria, and measurable rollback triggers. Use when the Feature Flag Agent has a confirmed feature-flag spec and must define the staged rollout before deployment.
---

# write-rollout-plan

## Purpose

Define the staged rollout schedule for a release flag before deployment so a new feature reaches users in widening cohorts rather than all at once. The plan names which cohorts get the feature first, the percentage ramp and the minimum time at each stage, the green metrics required to advance, and the specific measurable thresholds that force an immediate rollback. This is a Feature Flag vertical artifact. It advises the deploying horizontal agent through a consultation rather than editing that agent's deployment artifact.

## Inputs

| Field | Description |
|-------|-------------|
| `feature-flag-spec` | The flag definition from spgr-define-feature-flag, read via spgr-read-artifact |
| `slo-metrics` | SLO metrics to monitor during the rollout, sourced from the slo-spec |
| `segmentation-strategy` | User segmentation strategy that defines the cohorts each stage targets |
| `traffic-volume` | Production traffic volume, used to estimate absolute user counts at each rollout percentage |

## Outputs

| Artifact | Description |
|----------|-------------|
| `rollout-plan` | Envelope artifact written via spgr-write-artifact. Carries the stage sequence with per-stage dwell time, advancement criteria, rollback triggers, monitoring plan, and communication plan |
| `consultation` | A consultation to the deploying agent (DevOps) registered via spgr-tag-vertical-agent, carrying the rollout plan as the recommended ramp and rollback contract |

## Procedure

1. Read the inputs. Load the feature-flag spec with spgr-read-artifact and read the SLO spec, segmentation strategy, and traffic-volume figures with spgr-read-file or spgr-read-artifact as applicable.
2. Define the stage sequence as an ordered list, internal then a ramping percentage series (for example 1, 5, 20, 50, 100). Adjust the percentages to the traffic volume and the segmentation strategy. Translate each percentage to an estimated absolute user count using the traffic volume so the blast radius at each stage is explicit.
3. Set a minimum dwell time per stage, defined as the time needed to observe a statistical signal before advancing. Mark the internal stage as a short dogfooding window (about one day) since the internal team actively uses and reports issues.
4. Write advancement criteria per stage as the green-metric conditions that must hold for the full dwell time before the rollout advances. Tie each criterion to a named SLO metric.
5. Write rollback triggers as specific measurable thresholds, not judgment calls. State each as a metric, a comparison, and a duration, for example error rate for flag-variant users exceeds baseline times two for ten or more minutes. Reject any trigger phrased as "something looks wrong".
6. Record the cohort-stability rule. Once a user is in the treatment group, keep them there for the duration of the rollout. Do not re-randomize users between stages.
7. Write the pause-and-resume rule. If a rollback trigger fires, pause the rollout. Advance only after the trigger condition is resolved and the metrics are stable.
8. Define the monitoring plan (what to watch and how often, with closer attention in the early stages) and the communication plan (who is notified at each stage and how rollout status is reported).
9. Validate the artifact with spgr-validate-artifact, log the ramp and threshold choices with spgr-log-decision, version it with spgr-version-artifact, and register the consultation to the deploying agent with spgr-tag-vertical-agent.
10. If any input is missing or contradictory (no SLO metrics to gate advancement, no baseline to set rollback thresholds against, or a segmentation strategy that cannot keep cohorts stable), stop and raise spgr-escalate with a precise list of what is missing rather than assuming default thresholds.

## Notes

- Output type: spec or policy envelope artifact (rollout-plan). The rollout-plan content schema is not registered yet, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, version) and the content schema is registered in a later increment.
- Every rollback trigger is measurable and unattended, so the trigger condition decides a rollback without a human judgment call.
- Route the rollout plan to the deploying agent through a consultation (spgr-tag-vertical-agent), not by editing the deployment artifact.
- Future Phase 2 increment: wire the advancement criteria to the monitoring platform so the rollout advances automatically once all criteria stay green for the required dwell time.
