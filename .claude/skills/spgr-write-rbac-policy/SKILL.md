---
name: spgr-write-rbac-policy
description: Produce an rbac-policy artifact defining the role hierarchy, the role-by-resource-by-action permission matrix, the enforcement point per permission, and a privilege-escalation analysis, with one enforcement test per permission row. Use when the Auth Agent must establish the access-control contract before any permission check is coded.
---

# write-rbac-policy

## Purpose

Write the project's role-based access control policy as the single contract between what the product promises about access and what the code enforces. Without a written policy, permission boundaries drift, new features add ad-hoc checks that do not align with the role model, and no one can answer "what can a user with role X do?". Produce a complete, queryable permission model and a per-permission enforcement test set so the policy is verifiable, not aspirational.

## Inputs

| Field | Description |
|-------|-------------|
| `auth_model` | The access control approach, from spgr-design-auth-model. |
| `user_types` | User types and personas the roles must cover. |
| `feature_inventory` | Features from the PRD with the access requirement per feature. |
| `data_classification` | PII and sensitivity markers from the Compliance Agent, if available. Drives least-privilege decisions on sensitive resources. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `rbac-policy` | Role definitions (name, description, intended user type), the permission matrix (role by resource by action: read, write, delete, admin), the role hierarchy with inherited permissions, the enforcement point for each permission, and a privilege-escalation analysis. |
| `enforcement tests` | One generated test per permission matrix row: a user without the permission receives 403, a user with it receives the expected response. Returned alongside the artifact for the QA and Developer agents. |

## Procedure

1. Read the inputs with spgr-read-artifact. If the auth model, the user types, or the feature inventory with access requirements is missing or contradictory, stop and raise spgr-escalate with the precise list of what is missing. Do not invent roles or access requirements to fill the gap.
2. Derive the role set from the user types and personas. Write each role with a name, a description, and the intended user type. Map each role to the features it must reach from the feature inventory.
3. Build the permission matrix as role by resource by action across read, write, delete, and admin. Assign the minimum permissions each role needs for its function. Do not grant a convenient catch-all. A sensitive or PII-classified resource gets least privilege by default.
4. Define the role hierarchy where roles inherit from a parent. State the inherited permissions explicitly so the effective permission set of every role is readable from the policy alone.
5. Enumerate admin permissions specifically, resource by resource. A "superuser has access to everything" definition is not a policy, it is a statement that RBAC is not implemented for admins. Each admin grant is a named row in the matrix.
6. Assign an enforcement point to each permission. Enforcement happens at the service layer, not only the API layer. A check at the HTTP handler that is not also enforced at the service layer is bypassable by any code path that calls the service directly. Record the API middleware, service layer, and data layer points for each permission.
7. Write the privilege-escalation analysis: how a user can change roles, which transitions require human approval, and which are self-service. Tag any change that touches an admin role or a sensitive resource for spgr-tag-vertical-agent review by the Compliance Agent before the artifact is marked confirmed.
8. Generate one enforcement test per permission matrix row. Each test asserts a 403 for a user without the permission and the expected response for a user with it. Cover every row, including admin rows.
9. Write the artifact through spgr-write-artifact, log consequential role and least-privilege tradeoffs with spgr-log-decision, and version with spgr-version-artifact. If any input was proposed rather than confirmed, mark the affected section needs-human-input and route it through spgr-notify-human rather than asserting it as confirmed.

## Notes

- Output type is an envelope artifact written via spgr-write-artifact. The rbac-policy type has no registered content schema yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered. Still call it on every write, and check structural completeness against this procedure in addition.
- Least privilege is the governing rule. Every grant must trace to a feature access requirement. A grant with no requirement is removed, not retained for convenience.
- The policy is queryable by design. The effective permission set of any role must be answerable from the role definitions, the matrix, and the hierarchy without reading application code.
