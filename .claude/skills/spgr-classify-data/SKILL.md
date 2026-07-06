---
name: spgr-classify-data
description: Produce a data-classification artifact that sorts every data field into a sensitivity tier with per-tier encryption, retention, access-control, and breach-notification requirements. Use when the Compliance Agent has a data model and compliance scope, or when the Auth Agent needs the classification for RBAC boundaries.
---

# classify-data

## Purpose

Classify every data field into a sensitivity tier so that all downstream data-protection work has a single authoritative map to read. You cannot set a retention policy without knowing whether a field is PII, cannot set access controls without knowing what is sensitive, and cannot assess breach-notification obligations without knowing what was exposed. Classify at the field level, not the table level, because one table mixes tiers. Attach to each tier the encryption, retention, access, and breach-notification requirements, and emit enforcement annotations so the data model can apply column-level encryption and audit logging automatically.

## Inputs

| Field | Description |
|-------|-------------|
| `data-model` | The ERD or schema definitions listing every entity and field. Read via spgr-read-artifact when an erd artifact exists. |
| `product-description` | What data the system collects and why, used to resolve fields the schema alone does not explain. |
| `compliance-scope` | The compliance scope document naming the regimes in force (for example GDPR, CCPA, HIPAA) that set tier obligations. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `data-classification` | A field-level registry. Each field carries a tier (1 Restricted, 2 Confidential, 3 Internal, 4 Public), the reason for the tier, and the per-tier encryption, retention, access-control, and breach-notification requirements. Includes enforcement annotations: column-level encryption on Tier 1 fields, audit logging on Tier 1 and Tier 2 field access. |

## Procedure

1. Read the data model, product description, and compliance scope. If any of the three is missing or the data model lists fields with no description that you cannot classify by name alone, call spgr-escalate with the precise list of missing inputs rather than guessing.
2. Enumerate every field across every entity. Classify each field, not each table. A single table can hold Tier 1, Tier 2, and Tier 3 fields, and each gets its own classification.
3. Assign one tier per field. Tier 1 Restricted: PHI, financial account data, credentials, government IDs. Tier 2 Confidential: PII such as name, email, address, phone, plus behavioral and usage data subject to GDPR or CCPA rights. Tier 3 Internal: business data with no personal information. Tier 4 Public: content intentionally made public.
4. When a field could plausibly hold PII and the inputs do not confirm otherwise, classify up to Tier 2. Record the assumption in the field reason and confirm it through spgr-escalate or spgr-tag-vertical-agent rather than silently downgrading.
5. Record per-tier requirements: encryption, retention limit, access-control requirement, and breach-notification obligation, each traced to the compliance regimes in the scope document.
6. Emit enforcement annotations. Mark every Tier 1 field for column-level encryption. Mark every Tier 1 and Tier 2 field for access audit logging. Tier 2 fields also require at-rest encryption at the storage level.
7. Tag the Compliance vertical for review of any tier assignment that turns on a regulatory judgment call by calling spgr-tag-vertical-agent, and log each consequential tier decision with spgr-log-decision.
8. Write the artifact with spgr-write-artifact, which runs inline validation through spgr-validate-artifact before the write completes. On a validation failure, fix the reported fields and rewrite. Do not mark the artifact confirmed while any field tier is unresolved.

## Notes

- The data-classification artifact is written via spgr-write-artifact. Its registered schema is not yet in the registry and is added in a later build increment, so validation runs against the shared envelope until the type-specific schema lands.
- This classification is the binding input to retention policy, RBAC boundaries, and encryption decisions. Revising a tier after downstream work has consumed it is a change that goes through spgr-version-artifact and may require spgr-notify-human if it widens scope.
