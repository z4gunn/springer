---
name: spgr-write-audit-trail-spec
description: Produce an audit-trail-spec artifact that defines which events are audited, the log entry schema, tamper protection, per-framework retention, and access controls on the log store. Use when the Compliance Agent must settle audit logging requirements before retention, access control, or observability work proceeds.
---

# write-audit-trail-spec

## Purpose

Specify the audit trail so it survives both a compliance audit and a security incident. An audit trail fails when it is incomplete (a required event never logs), mutable (an entry can be deleted or altered), or inaccessible (stored where compliance cannot query it). This skill settles the event taxonomy, the per-entry schema, tamper protection, retention, access controls on the log store, and the query interface, all driven by the data classification and the applicable frameworks. Audit logs are not application logs. Application logs are for debugging and have short retention and broad developer access. Audit logs are for compliance and forensics and have long retention, restricted access, and write-once storage. Keep the two contracts separate.

## Inputs

| Field | Description |
|-------|-------------|
| `data-classification` | The classification registry from spgr-classify-data. Restricted and Confidential tier fields require access logging. |
| `compliance-scope` | The scope artifact from spgr-assess-compliance-scope. Each applicable framework sets framework-specific audit and retention requirements. |
| `auth-model` | The auth model from spgr-design-auth-model. Identifies which operations require resolvable user-identity tracking. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `audit-trail-spec` | An envelope artifact covering the event taxonomy, log entry schema, tamper protection, retention per framework, access controls on the log store, and query interface requirements. Written via spgr-write-artifact. |

## Procedure

1. Read the three inputs with spgr-read-artifact. If the data classification, compliance scope, or auth model is missing or unconfirmed, stop and call spgr-escalate naming which input is absent. Do not infer which data is sensitive or which frameworks apply.
2. Build the event taxonomy. Audit at least authentication, data access, data modification, permission changes, and admin actions. Add a logged-access entry for every Restricted and Confidential tier field named in the data classification. Cross-check the auth model so every operation that requires user-identity tracking has a matching audited event.
3. Define the log entry schema. Each entry captures actor ID, action, resource type, resource ID, timestamp with timezone, outcome, IP address, and request ID. The actor must be a resolvable identity, not just an IP address. Name every API service account. Do not allow an anonymous actor.
4. Specify tamper protection. The log store is append-only. Require write-once storage (AWS CloudTrail, immutable S3 with Object Lock, or an append-only database) and log signing. State that entries are never deleted or modified, only appended.
5. Set the retention period per applicable framework, taking the longest where frameworks overlap. SOC 2 recommends one year. HIPAA requires six years. Record the framework that drives each retention value.
6. Define access controls on the audit log itself. Name who can read it and state that no role can delete an entry. These controls differ from application-log access. Tag the Auth Agent with spgr-tag-vertical-agent to confirm the read-access roles against the RBAC policy.
7. Specify the query interface. Require retrieval of all actions by a given actor, all access to a given resource, and all events within a time window. Specify audit log streaming to a SIEM system so compliance can query the trail without direct database access.
8. Write the artifact with spgr-write-artifact and run spgr-validate-artifact inline. Record per-section confidence (confirmed, proposed, needs-human-input) and log each material choice with spgr-log-decision. On a validation failure, fix the artifact and re-validate before returning. Version the result with spgr-version-artifact.

## Notes

- Output type is an envelope artifact. The `audit-trail-spec` content type is not registered in the schema registry, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered. Still call it.
- Reference the schema registry for the artifact envelope shape rather than restating its fields here.
- Tamper protection and write-once storage are not optional for compliance-grade trails. If the confirmed architecture provides no append-only or write-once store, mark the tamper-protection section needs-human-input and escalate with spgr-escalate rather than downgrading the requirement.
- Keep the audit-log contract distinct from the operational logging schema produced by spgr-write-logging-schema. Different retention, different access, different storage.
