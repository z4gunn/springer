---
name: spgr-generate-erd
description: Produce an erd artifact that captures the full data model as entities with typed attributes and constraints, relationships with cardinality, junction tables for M:N, audit fields on every entity, and explicit PII markers, rendered as portable Mermaid. Use when the Architect Agent has data requirements from the PRD and user stories plus a compliance classification and needs the authoritative data model before any migration, data dictionary, or API spec work begins.
---

# generate-erd

## Purpose

Build the single shared data model the whole team designs against. The erd artifact is the source of truth for migrations, the data dictionary, and the API spec, so any drift between it and those documents is a bug, not a stylistic difference. The contract here is what every entity and attribute must carry: a complete type and constraint set, a cardinality on every relationship, audit fields from the first version, and a PII classification on every field so the Security and Compliance agents can drive encryption, access control, and retention from the model rather than guessing later.

## Inputs

| Field | Description |
|-------|-------------|
| `data_requirements` | Data needs drawn from the PRD and user stories, naming the entities the product must store and how they relate |
| `domain_model` | The domain entities and their relationships as understood from discovery |
| `compliance_classification` | Which data is PII, PHI, financial, or otherwise regulated, used to mark fields and drive downstream controls |

## Outputs

| Artifact | Description |
|----------|-------------|
| `erd` | Entity relationship model with entities, typed attributes, constraints, relationships with cardinality, junction tables, audit fields, PII markers, and a Mermaid rendering |
| `data_dictionary_stub` | First-pass data dictionary generated from the erd entities and attributes, handed to the Data Dictionary work as a starting point |

## Procedure

1. Read each input field. Derive the entity list from the data requirements and the domain model. If the requirements name a relationship or an entity the inputs do not define well enough to type, do not invent the missing structure. Mark that section confidence `proposed` and add the gap to a list for confirmation.
2. For every entity, define all attributes with a concrete data type and the full constraint set: primary key, foreign key, unique, nullable, and default. A foreign key attribute must name the entity it references.
3. Add the audit fields `created_at`, `updated_at`, and `deleted_at` to every entity from the start. Use `deleted_at` as a nullable timestamp for soft delete, which is the default. Switch an entity to hard delete only when an input states an explicit hard-delete requirement, and record that choice with spgr-log-decision.
4. Define every relationship with a cardinality of `1:1`, `1:N`, or `M:N` and state its optionality. For each `M:N` relationship, create a junction table with its own surrogate primary key, carrying any attributes the relationship itself holds.
5. Mark a PII classification on every attribute using the compliance classification input, for example PII, PHI, financial, or not-PII. Do not leave an attribute unclassified. If an attribute's classification is not derivable from the inputs, mark it `proposed` and surface it for confirmation rather than defaulting it to not-PII.
6. Render the model in Mermaid ERD syntax for portability. Keep field names, types, and relationships identical to the structured entity and relationship data, because the same names must hold across the erd, the API spec, and migrations.
7. Generate the data dictionary stub from the entities and attributes so the downstream Data Dictionary work starts from the model rather than a blank file.
8. Run a consistency check against the active migration history if one exists. Report any entity, attribute, type, or relationship in the migrations that the erd does not match, and any erd element the migrations have not yet implemented, so drift surfaces early. Carry the result as a field on the artifact.
9. Produce the artifact with spgr-write-artifact, which stamps the shared envelope, records per-section confidence, initializes the decision log, and runs spgr-validate-artifact against the registered erd schema inline before write. Do not hand-build the envelope.
10. Tag the verticals on the PII surface. Invoke spgr-tag-vertical-agent for the Security Agent and the Compliance Agent to review the PII-classified fields before the erd is treated as ready for migration or API work.
11. If inputs contradict each other, if a required entity cannot be typed even as a proposed structure, or if the consistency check finds drift the agent cannot reconcile from the inputs, stop and raise spgr-escalate with a precise list of what is missing or conflicting rather than shipping an inconsistent model.

## Notes

- The erd artifact type is registered in the schema registry at `/Users/gunderer/Repos/springer/schemas/` as `erd-v1.json`. Reference field requirements through spgr-validate-artifact rather than inlining them here.
- The erd, the API spec, and the migrations must agree on every field name, type, and relationship. An inconsistency between them is a defect to escalate, not a variant to tolerate.
- Soft delete by way of a nullable `deleted_at` is the default. Hard delete is an exception that requires an explicit input requirement and a logged decision.
- A proposed structure or a proposed PII classification is a valid output state, not a failure. The failure is an invented entity or an unmarked PII field presented as confirmed.
