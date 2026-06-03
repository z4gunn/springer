---
name: spgr-provision-environment
description: Stand up a target environment (development, staging, or production) by executing infrastructure-as-code, then handle the post-provisioning steps IaC alone cannot, injecting secrets by reference from the secrets manager, verifying every required service-to-service path, running readiness smoke tests, and recording an environment-metadata artifact with endpoints and resource identifiers. Use when the DevOps Agent must turn confirmed IaC into a running, secrets-injected, connectivity-verified environment, or when a downstream agent needs the endpoint URLs and resource identifiers of a provisioned tier.
---

# provision-environment

## Purpose

Bridge the gap between an IaC definition and a running environment. "Infrastructure deployed" and "environment ready" are not the same state. Execute the IaC (Terraform, Pulumi, CDK, or equivalent), then perform the post-provisioning steps that infrastructure code does not cover, secrets injection by reference, service-to-service connectivity verification, and a readiness smoke test. Provisioning is idempotent and drift-aware, and a production apply is gated on human confirmation. The output is a running environment plus an envelope artifact that records endpoints, resource identifiers, the connectivity result, and the projected cost change.

## Inputs

| Field | Description |
|-------|-------------|
| `iac-config` | The IaC configuration files for the environment, read via spgr-read-file |
| `environment-tier` | One of dev, staging, or production, plus any tier-specific variable overrides |
| `secrets-manifest` | The list of secrets the environment needs, by name or ARN sourced from the secrets manager, never the values themselves |
| `connectivity-matrix` | The required service-to-service reachability pairs to confirm after provisioning |

## Outputs

| Artifact | Description |
|----------|-------------|
| Provisioned environment | All infrastructure components running, secrets injected by reference from the secrets manager into runtime configuration |
| Environment-metadata record | Envelope artifact written via spgr-write-artifact: endpoint URLs, resource identifiers, environment tier, connectivity verification result, projected monthly cost change, and provision timestamp for age tracking |

## Procedure

1. Read the IaC config, the tier overrides, the secrets manifest, and the connectivity matrix via spgr-read-file. Confirm the secrets manifest carries only names or ARNs. If any literal secret value appears in the manifest, the IaC, or a tier override, stop and call spgr-escalate. Secret values are fetched at runtime from the secrets manager and never enter state files or artifacts.
2. Run a plan against the live environment to detect drift. If the live environment diverges from the IaC definition because of a manual change, log the deviation with spgr-log-decision and call spgr-escalate before applying. Do not silently overwrite drift.
3. Produce the pre-apply cost estimate. Show the projected monthly cost change for the tier before any apply runs. Carry the estimate into the metadata artifact.
4. For a production tier, call spgr-notify-human with the plan summary and the cost estimate, and wait for confirmation before the final apply. Dev and staging apply without a human gate.
5. Apply the IaC idempotently. Apply changes in place against an already-provisioned environment and do not destroy and recreate resources unless the plan explicitly requires it.
6. Inject secrets into runtime configuration by reference, resolving names or ARNs from the secrets manager at apply time. Record only references in any output, never resolved values.
7. Verify connectivity. Confirm every required service-to-service path in the connectivity matrix is reachable, and run the readiness smoke test (see spgr-run-smoke-test). If any required path fails or the smoke test fails, the environment is not ready, call spgr-escalate with the failed paths and stop.
8. Write the environment-metadata record with spgr-write-artifact (endpoints, resource identifiers, tier, connectivity result, cost estimate, provision timestamp) and validate it inline with spgr-validate-artifact. On a validation failure, fix the artifact and re-validate before finishing. Tag the DevOps and Security verticals with spgr-tag-vertical-agent for the metadata and secret-reference handling.

## Notes

- Output type. The running environment is a SOURCE or CONFIG result produced by executing IaC and verified by spgr-run-smoke-test. The environment-metadata record is an ENVELOPE ARTIFACT. environment-metadata has no registered content schema yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered.
- No secret values in IaC state files or any artifact. Store only references such as ARNs or secret names. Resolve actual values at runtime from the secrets manager.
- Provisioning is idempotent. Re-running against an already-provisioned environment applies changes in place and does not destroy and recreate resources unless explicitly required.
- Drift is flagged and logged before apply via spgr-log-decision and spgr-escalate, never silently overwritten.
- Production provisioning always requires human confirmation via spgr-notify-human before the final apply.
- Record the provision timestamp in the metadata so environment age can be tracked. Flag any environment running longer than its planned tear-down window to prevent cost leaks from a forgotten staging environment.
- Version metadata changes with spgr-version-artifact when an environment is re-provisioned.
