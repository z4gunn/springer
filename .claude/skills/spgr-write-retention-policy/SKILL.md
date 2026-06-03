---
name: spgr-write-retention-policy
description: Produce a retention-policy artifact that sets a retention period, retention trigger, deletion trigger, deletion mechanism, deletion verification, and right-to-erasure handling for each data classification tier, satisfying regulatory minimums and maximums while staying implementable in the system's data architecture. Use when the Compliance Agent has a data classification registry and a compliance scope and must define how long each data type is kept and how it is deleted before the product launches, or when a new framework, jurisdiction, or business-driven retention need requires the policy to be revised.
---

# write-retention-policy

## Purpose

Define per-tier data retention and deletion rules so the system keeps data long enough to meet legal minimums and not longer than legal maximums. Retention policy has two failure modes that this artifact must close: keeping data too long, which raises breach scope and breaks GDPR storage limitation, and deleting data too soon, which breaks HIPAA and financial-record obligations. The policy must be implementable in the actual data model, so every rule names the data it governs, the trigger that starts and ends retention, the mechanism that removes the data, and the check that confirms removal.

## Inputs

| Field | Description |
|-------|-------------|
| `data-classification-registry` | The per-tier classification of stored data, including PII markers. One retention rule is produced per tier. |
| `compliance-scope` | The in-scope frameworks and the retention minimums and maximums each imposes (GDPR, HIPAA, financial regulation, and so on). |
| `product-requirements` | Any business-driven retention need, for example a seven-year financial record hold, that is not stated by a framework. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `retention-policy` | One retention rule per data classification tier. Each rule states retention period (minimum and maximum, with regulatory source), retention trigger (account creation, last activity, contract end), deletion trigger (retention expiry, user deletion request, account closure), deletion mechanism (hard delete, anonymization, cryptographic erasure for encrypted data), deletion verification (audit log entry, database record check), and right-to-erasure handling under GDPR Article 17 (request processing, thirty-day timebox, exceptions). |

## Procedure

1. Read the inputs with spgr-read-artifact. List every data classification tier from the registry. Produce one retention rule per tier so no tier is left without a rule.
2. For each tier, set the retention period as a minimum and a maximum, and cite the regulatory source for each bound. Where a framework minimum and a GDPR maximum overlap on the same data, record both bounds and the controlling source. If a minimum exceeds a maximum on the same data, the requirements conflict and you must not pick one. Stop and raise spgr-escalate with both sources named.
3. Set the retention trigger and the deletion trigger for each rule. State the trigger as a concrete event in the data model, not as a vague condition.
4. Set the deletion mechanism. Treat "delete" as unrecoverable: not a soft delete with a `deleted_at` timestamp, not a record left in a retained backup. State explicitly whether the mechanism is hard delete, anonymization, or cryptographic erasure for encrypted data.
5. Constrain backups against the retention period. Backup retention must not exceed the governed data's retention maximum. If the system's current backup retention is longer than a tier allows, record the conflict and raise spgr-escalate to the architecture or DevOps owner rather than writing a policy the system cannot meet.
6. Where anonymization replaces deletion, document the anonymization method and an adequacy assessment that re-identification is not feasible. Only then may the anonymized data be treated as outside personal-data scope.
7. Write the right-to-erasure handling for personal-data tiers: which tables and fields are affected, cascade behavior, the thirty-day completion timebox, and any lawful exception that overrides erasure. Flag that this technical path is designed before launch, not retrofitted after the first request.
8. Specify automated retention enforcement as part of the policy: a nightly background job that finds records past their retention date and queues them for deletion. State the queue, the deletion mechanism it calls, and the verification it records. Manual enforcement does not scale and is not an acceptable enforcement mechanism.
9. Record consequential choices with spgr-log-decision, in particular a chosen deletion mechanism, an anonymization adequacy call, and any retention bound that resolves competing sources.
10. Before finalizing any rule that turns on a framework interpretation, an erasure exception, or an anonymization adequacy judgment, consult the Compliance specialist with spgr-tag-vertical-agent and fold the recommendation into the rule.
11. Write the artifact with spgr-write-artifact, then confirm it with spgr-validate-artifact. If validation fails or any input is missing or contradictory, raise spgr-escalate with a precise list of what is missing rather than filling the gap with an assumption.

## Notes

- The retention-policy type is not yet in the schema registry at `/Users/gunderer/Repos/springer/schemas/`. Write it through spgr-write-artifact under the shared envelope. Its registered JSON Schema is added in a later build increment, after which spgr-validate-artifact checks it by type.
- This skill produces the policy only. It does not classify data and it does not write the audit-trail spec. If the classification registry is missing tiers or PII markers, stop and escalate to the classify-data owner.
- A rule is implementable only if its trigger and mechanism map to real entities and fields. A rule that cannot be expressed against the data model is not confirmable and must be escalated to architecture.
