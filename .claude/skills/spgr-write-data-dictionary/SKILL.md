---
name: spgr-write-data-dictionary
description: Produce a data-dictionary artifact defining every entity, field, type, constraint, and PII classification as the single source of truth that the API spec, migrations, and code all match. Use when the Architect Agent has an approved ERD and downstream agents need authoritative field names and types.
---

# write-data-dictionary

## Purpose

Produce the one authoritative document that names every data field, fixes its type and constraints, and classifies its PII status. Downstream agents reference this artifact rather than inferring field names from context. Field names here, in the ERD, in migrations, in the API spec, and in application code must match exactly. Any discrepancy is a bug. PII classification on each field drives encryption at rest, access logging, retention policy, and export and deletion handling under GDPR and CCPA, so every field carries an explicit classification, including the value not-PII.

## Inputs

| Field | Description |
|-------|-------------|
| `erd` | Approved entity-relationship diagram artifact. Source of entities, relationships, and foreign keys. |
| `domain_model` | Domain entities and their meaning, used for field descriptions and to confirm naming. |
| `compliance_classification` | Compliance inputs that set the PII classification per field. Tag the Compliance vertical when a field's class is unclear. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `data-dictionary` | Per entity: name, description, and a field list. Each field carries name, type, constraints, description, PII classification, and any foreign-key reference. Includes a changelog of dated additions and modifications. |

## Procedure

1. Read the ERD and domain model with spgr-read-artifact. Confirm both validate before consuming them. List every entity and its fields, and resolve each foreign-key relationship to the referenced entity field.
2. For each field, set the field name, data type, and constraints (not null, unique, default, length). Take the field name from the ERD verbatim. Do not rename or normalize a name that the ERD already fixed.
3. Assign a PII classification to every field from the compliance classification input. Never leave a field unclassified. A field with no PII is recorded with the explicit value not-PII.
4. When a field's PII classification is ambiguous or absent from the input, tag the Compliance vertical with spgr-tag-vertical-agent and record its recommendation before marking the field confirmed. Do not guess a classification.
5. Cross-check every field name against the ERD. If a name in the ERD, domain model, or an upstream artifact does not match, stop and raise spgr-escalate with the exact mismatched names rather than silently choosing one.
6. Record the changelog entry for this write with the date and a short description of what was added or modified.
7. Capture any consequential naming or typing choice with spgr-log-decision, including the alternatives considered.
8. Write the artifact with spgr-write-artifact, which runs spgr-validate-artifact against the registered schema inline before the write completes. On a validation failure, fix the reported fields and rewrite. Do not hand off an artifact that fails validation.

## Notes

- The artifact type is `data-dictionary`, registered in the schema registry at `schemas/`. Reference the registered schema through spgr-validate-artifact rather than inlining the field list here.
- Keep the dictionary in sync with the ERD. When the ERD changes, update the dictionary in the same commit and add a changelog entry. Use spgr-version-artifact to stamp the revision.
- This dictionary is the single source of truth for field names and types. Direct other agents to read it rather than infer names from context.
- Phase 2 build follow-on, recorded here for traceability and not implemented by this skill: a CI check validates migration field names against the dictionary, and API schema descriptions are generated from the dictionary to remove duplication.
