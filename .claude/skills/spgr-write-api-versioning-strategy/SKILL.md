---
name: spgr-write-api-versioning-strategy
description: Produce an api-versioning-strategy artifact that fixes how the API absorbs breaking changes, covering the versioning scheme with rationale, the breaking-versus-non-breaking change definition, the deprecation window, the sunset notification process, migration support obligations, the internal-versus-external distinction, and the automated deprecation-header injection rule. Use when the API Design Agent must settle versioning policy before the first breaking change is needed, or when a backend or architect agent asks the API Design vertical to advise on a version bump, a deprecation timeline, or a sunset commitment.
---

# write-api-versioning-strategy

## Purpose

Define how the API handles breaking changes before the first one is needed, not after a client has already broken. The API Design Agent owns this skill and operates as a vertical consultant, auditor, and gate. The strategy fixes the versioning scheme, the definition of a breaking change, the deprecation window, the sunset notification process, and the migration support the project commits to. Downstream backend, architect, and DevOps agents read this artifact to decide whether a change needs a version bump and what headers and timelines apply. A version bump or sunset date is a customer commitment, so the strategy is the gate that those commitments pass through.

## Inputs

| Field | Description |
|-------|-------------|
| `consumer-types` | API consumer categories: internal consumers, public third-party consumers, embedded clients |
| `change-velocity` | How often breaking changes are anticipated |
| `product-sla` | Product SLA and existing customer commitments that bound the deprecation window |
| `api-spec` | The OpenAPI spec, read to locate endpoints and to wire the deprecation-header rule |

Read each input through spgr-read-artifact or spgr-read-file. Do not infer a missing consumer type or SLA.

## Outputs

| Artifact | Description |
|----------|-------------|
| `api-versioning-strategy` | Policy document with the versioning scheme and rationale, breaking-change definition, deprecation window, sunset notification process, migration obligations, internal-versus-external distinction, and the automated deprecation-header injection rule |

Write the artifact with spgr-write-artifact and validate it inline with spgr-validate-artifact. Record each consequential choice (scheme selection, window length) with spgr-log-decision.

## Procedure

1. Read the consumer types, change velocity, product SLA, and API spec. If any is missing or a stated SLA contradicts a proposed deprecation window, stop and raise spgr-escalate with the precise list of what is missing or conflicting. Do not pick a default to fill the gap.
2. Select the versioning scheme. Recommend URL path versioning (`/v1/`, `/v2/`) over header versioning for most projects, since it is simpler to implement, test, and communicate. Record the rationale and the rejected alternative with spgr-log-decision. If a stated constraint forces header versioning (`Accept: application/vnd.api+json;version=2`), document why.
3. Write the breaking-change definition. Non-breaking changes (additive fields, new optional parameters, new endpoints) do not require a version bump. Breaking changes (removing fields, changing types, altering response structure, changing required parameters) always require a version bump. State both lists explicitly so a backend agent can classify a change without asking.
4. Set the deprecation window. Use a minimum of 6 months for public APIs. Permit an expedited window for internal-only APIs and state the internal-versus-external distinction. During the window, the old version returns a `Deprecation` header pointing to the migration guide.
5. Define the sunset notification process: how consumers are notified of an upcoming version removal and how far ahead. Treat a stated removal date ("we will remove v1 on [date]") as a binding commitment. Only write a date the project intends to keep.
6. State the migration support obligations: whether migration guides, compatibility shims, or migration assistance are provided, and for which consumer types.
7. Specify the automated deprecation-header rule. When an endpoint is marked deprecated in the OpenAPI spec, middleware adds the `Deprecation` and `Sunset` headers to every response from that endpoint. Describe the trigger (the spec annotation), the headers injected, and the migration-guide link target. This is a policy specification in the artifact, not the middleware code. The backend or DevOps agent implements it from this rule.
8. Validate the artifact with spgr-validate-artifact. On a confirmed version, stamp it with spgr-version-artifact.
9. When this strategy constrains a section of another agent's artifact (for example an API spec endpoint or an ADR), route the recommendation through spgr-tag-vertical-agent as a consultation rather than editing the other artifact directly. At the required human gate (a scope change or a sunset commitment that affects customers), pause with spgr-notify-human.

## Notes

- Output type is a policy envelope artifact (api-versioning-strategy). Its content schema is registered in a later increment, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, and version).
- Mark each section confidence as confirmed, proposed, or needs-human-input. A sunset date or deprecation window not yet approved by a human stays needs-human-input until spgr-notify-human returns approval.
- The vertical advises through the consultation contract. Do not write a version bump into another agent's API spec. Recommend it through spgr-tag-vertical-agent and let the owning agent apply it.
