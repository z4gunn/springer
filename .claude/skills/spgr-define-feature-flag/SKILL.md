---
name: spgr-define-feature-flag
description: Produce a feature-flag spec artifact fixing a flag's key, type, per-environment defaults, target audience, lifecycle milestones with a retirement date, and rollback procedure before the flag is created in the flag platform. Use when the Feature Flag Agent must specify a flag before creation so it does not become permanent technical debt.
---

# define-feature-flag

## Purpose

Write the specification for a feature flag before the flag exists in the platform, so its purpose, audience, and expected removal are decided up front rather than discovered later. Feature flags without lifecycle management become permanent technical debt, and the most common cause is a release flag that ships, reaches 100 percent, and is never removed. This artifact fixes the flag key, the flag type, the per-environment default state, the target audience, the lifecycle milestones including a retirement date or trigger, the emergency rollback procedure, and any flag dependencies. Choosing the type correctly is the load-bearing decision here, because release and experiment flags are temporary while kill-switch and entitlement flags are permanent, and the wrong type sets the wrong retirement expectation.

## Inputs

| Field | Description |
|-------|-------------|
| `feature-description` | The feature being gated and the rollout intent behind the flag. |
| `target-audience` | Who the flag exposes the feature to: all users, a specific user cohort or segment, a specific plan, or internal team only. |
| `intended-lifecycle` | The lifecycle class implied by the use: release flag (temporary), kill switch (permanent), entitlement (permanent), or experiment (temporary). |
| `flag-platform` | The feature flag system in use (LaunchDarkly, Unleash, PostHog flags, GrowthBook, and so on), which determines the platform-native targeting and default-state semantics the spec must map to. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `feature-flag-spec` | A spec containing the flag key in `<feature-area>.<feature-name>` kebab-case form, the flag type (release, experiment, kill-switch, or entitlement), the default state (on or off) per environment for development, staging, and production, the target audience definition, the lifecycle (creation milestone, expected full-rollout date for release flags, retirement date or trigger condition), the emergency rollback procedure for turning the flag off, the dependencies on other flags or features, and the lifecycle-management rules that govern debt review and rollout alerting. |

## Procedure

1. Read the inputs with spgr-read-artifact. Confirm the feature description, the target audience, and the intended lifecycle are all present. If the lifecycle class is absent or the target audience is undefined, stop and raise spgr-escalate with the precise gap rather than assuming a release flag by default.
2. Select the flag type from the intended lifecycle and the use. A release flag rolls a feature out safely and is temporary. An experiment flag drives an A/B test and is temporary. A kill switch is a permanent emergency shutoff for high-risk functionality. An entitlement flag controls plan-based feature access and is permanent. If the description fits more than one type, or fits none, escalate to the Feature Flag Agent owner for the type decision rather than picking one silently.
3. Set the flag key in `<feature-area>.<feature-name>` kebab-case form, for example `checkout.new-pricing-display`. Treat the key as immutable, because renaming a key after creation requires a new flag and a consumer migration. State that constraint in the spec so the key is chosen with care.
4. Set the default state per environment for development, staging, and production. For a kill switch, default to on (functionality enabled) in production so the switch is flipped to off only in an emergency. For a release flag, default to off in production until rollout begins. State the rationale for each environment's default.
5. Define the target audience precisely: all users, a named segment or cohort, a named plan, or internal only. Map the definition to the targeting model of the named flag platform so the spec is directly implementable.
6. Define the lifecycle. Record the creation milestone. For a release flag, set the expected full-rollout date and a retirement date that is no later than one sprint after stable 100 percent rollout. For an experiment flag, set retirement to the experiment conclusion. For kill-switch and entitlement flags, record that the flag is permanent and has no retirement date. A release flag with no retirement date is not confirmable, so escalate rather than ship one without it.
7. Write the emergency rollback procedure: the exact steps to turn the flag off, who can perform them, and the expected effect. The rollback must be operable without a deploy.
8. List dependencies on other flags or features this flag interacts with, including any ordering constraint between flags, so a consumer does not enable this flag into a broken combined state.
9. Record the lifecycle-management rules in the spec: a flag whose retirement date is overdue surfaces in the weekly flag-debt review, and a release flag that holds 100 percent rollout for 14 consecutive days without being retired triggers an alert. State these as conditions the Feature Flag Agent and DevOps owner can wire, not as prose.
10. Where the flag's audience is plan-based (entitlement) or the rollback affects another agent's domain, route the recommendation to the consuming horizontal agent through spgr-tag-vertical-agent rather than editing that agent's artifact. An entitlement flag's plan mapping flows to the Billing vertical through a consultation.
11. Record consequential choices with spgr-log-decision, in particular the chosen flag type, the per-environment default states, and the retirement date or permanent designation.
12. Write the artifact with spgr-write-artifact, then confirm it with spgr-validate-artifact. If validation fails or any input is missing or contradictory, raise spgr-escalate with the exact gap rather than filling it with an assumption.

## Notes

- This is an envelope artifact (a feature-flag spec). Write it through spgr-write-artifact and validate inline with spgr-validate-artifact. The feature-flag-spec type is not yet in the schema registry, so envelope-only validation applies for now (header, confidence map, decision log, version), and its content schema is registered in a later build increment.
- This skill specifies one flag only. It does not create the flag in the platform and it does not write the rollout plan or the entitlement map. It supplies the flag key, type, and lifecycle those artifacts consume, routed through a consultation, not a direct edit.
- The flag key is immutable once the flag is created. A spec that proposes a key is committing the project to that key, so the key is a confirmed field, not a placeholder.
- A release flag is confirmable only with a retirement date set. A flag type chosen by habit rather than by lifecycle is the failure mode this artifact exists to prevent, so a type that does not match the intended lifecycle must be escalated, not written.
