---
name: spgr-write-tenant-provisioning-spec
description: Produce a tenant-provisioning-spec artifact defining the full tenant lifecycle (creation, configuration, suspension, deletion) as an ordered saga with per-step error handling, compensating actions, and idempotency. Use when the Multi-tenancy Agent must specify how a tenant is created and torn down before provisioning code is written.
---

# write-tenant-provisioning-spec

## Purpose

Define the complete tenant lifecycle so that every customer arrives at a fully initialized product state and every cancelled tenant is torn down without orphaned records or FK violations. Provisioning is the on-ramp to a SaaS product: signup creates the tenant data space, default configuration, subscription, and first admin user. Done poorly, a new customer lands in a partially initialized state that looks complete but is missing default settings or has failed background setup jobs. This spec makes the flow explicit, testable, and recoverable by modeling it as a multi-step saga with a compensating action per step and idempotent re-trigger behavior.

The Multi-tenancy Agent owns this skill and operates as a vertical consultant, auditor, and gate. It writes the tenant-provisioning-spec as an envelope artifact. It does not edit the data model, the billing spec, or the auth model directly. A recommendation that changes another agent's artifact section flows through a consultation via spgr-tag-vertical-agent.

## Inputs

| Field | Description |
|-------|-------------|
| `multi-tenancy-architecture-model` | The tenancy model (shared schema, schema-per-tenant, database-per-tenant) that determines what a tenant data space is and how it is created. |
| `data-model` | Which records must be created during provisioning and the FK dependency order between them. Read the erd and data-dictionary via spgr-read-artifact. |
| `billing-spec` | How a subscription record is created during provisioning. Read via spgr-read-artifact. |
| `auth-model` | How the first admin user is created and linked to the tenant. Read via spgr-read-artifact. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `tenant-provisioning-spec` | Envelope artifact covering the provisioning trigger, ordered steps, per-step error handling, idempotency, suspension, deletion, and a tenant health check endpoint. Written via spgr-write-artifact with inline spgr-validate-artifact. |

The artifact records the provisioning trigger (signup completion, manual admin action, or API call), the ordered provisioning steps with their dependency order, the compensating action and retry behavior per step, the idempotency contract on re-trigger, the suspension workflow, the deletion workflow with retention period and FK-safe ordering, and the tenant health check endpoint definition.

## Procedure

1. Read the inputs. Pull the tenancy model from the architecture model, the record set and FK order from the data-model via spgr-read-artifact, the subscription-creation step from the billing-spec, and the admin-user creation from the auth-model. If the tenancy model is undecided, the FK ordering is absent, or the billing or auth model does not define how its record is created, stop and raise spgr-escalate with the precise list of missing inputs. Do not guess a creation order.

2. Specify the provisioning trigger. State which event starts provisioning (signup completion, manual admin action, or API call) and the payload it carries. A single named entry point keeps re-trigger behavior testable.

3. Order the provisioning steps by FK dependency. The default order is tenant record, then subscription record, then admin user, then default workspace, then onboarding state. Each step may only depend on records created by an earlier step. Derive the exact order from the data-model FK graph rather than assuming the default fits every tenancy model.

4. Define error handling per step as a saga. For each step, state the compensating action that undoes or marks the partial work if that step fails, and whether the tenant can complete provisioning on retry from that point. A failed step must never leave a tenant in a partially initialized state that reads as fully initialized.

5. Specify the idempotency contract. Running provisioning twice for the same tenant must either resume from where it left off and complete, or return a clear already-provisioned response. It must never create duplicate records. State the idempotency key and the per-step existence check that enforces this.

6. Define the suspension workflow. State exactly what is disabled when a tenant is suspended (API access, login, data access) and what is preserved, and the reverse action that restores the tenant. Suspension is reversible and must not delete data.

7. Define the deletion workflow. State the data retention period after cancellation before hard deletion, the hard-deletion steps, and the deletion order. Order deletion to avoid FK constraint violations, deleting dependent records before their parents, and include dependent records outside the primary database (storage objects, external billing or auth accounts) so nothing is orphaned.

8. Specify the tenant health check endpoint: an internal endpoint that verifies a tenant's provisioning is complete by checking that every required record and configuration exists. State the checks it runs and its pass and fail responses, so it serves both production debugging and E2E provisioning verification.

9. Log each consequential choice with spgr-log-decision, capturing the decision, the rationale, the alternatives, and the downstream impact, so the saga order and deletion order are not re-litigated later.

10. Write the tenant-provisioning-spec via spgr-write-artifact, which runs spgr-validate-artifact inline before the write completes. On a validation failure, fix the reported issues and re-validate. Do not write a partial artifact.

11. Where a step implies an amendment to a horizontal agent's artifact (for example a subscription creation order that the billing-spec does not support, or an admin-user linkage the auth-model does not define), route the recommendation through spgr-tag-vertical-agent as a consultation rather than editing that artifact.

## Notes

- Output type is an envelope artifact (`tenant-provisioning-spec`). Its content schema is registered in a later increment, so envelope-only validation applies for now: spgr-validate-artifact still checks the header, confidence map, decision log, and version.
- Reference the artifact schema registry rather than restating field lists. Read inputs via spgr-read-artifact and write the output via spgr-write-artifact.
- Mark each section with a confidence signal. A step ordering derived from a confirmed FK graph is confirmed, an ordering set without firm data-model input is proposed, and any section blocked on a missing input is needs-human-input.
- On revision after a new provisioning step is added or after the data model changes the FK order, re-version through spgr-version-artifact.
