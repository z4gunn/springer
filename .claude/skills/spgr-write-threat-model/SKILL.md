---
name: spgr-write-threat-model
description: Produce a threat-model artifact that decomposes the system, draws trust boundaries, enumerates STRIDE threats per component and data flow, rates each by likelihood times impact, and maps an owned mitigation to each threat. Use when the Security Agent must establish the threat model before downstream security work or after an architecture change.
---

# write-threat-model

## Purpose

Produce the project threat model, the Security Agent's primary analytical artifact. The threat model makes security reasoning systematic rather than intuition-driven. Decompose the system, draw trust boundaries, then walk every component and every data flow against all six STRIDE categories so the attack surface is enumerated rather than left to whatever the reviewer happened to recall. Each threat carries a risk rating and a mitigation tied to that specific threat, not a generic security checklist. Downstream security findings, the auth model, and architecture review all read this artifact.

## Inputs

| Field | Description |
|-------|-------------|
| `system_diagram` | System architecture and component list, from the system-diagram artifact. |
| `data_flows` | Data flow descriptions showing how data moves between components. |
| `api_surface` | Endpoints and operations, from the api-spec artifact. |
| `auth_model` | User types and trust boundaries, from the auth-model artifact. |
| `compliance_constraints` | Known compliance classification and data-handling obligations. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `threat-model` | System decomposition (components, data stores, external entities, trust boundaries), a data flow diagram with trust boundary annotations, a STRIDE enumeration per component and data flow, a likelihood-times-impact risk rating per threat, and a mitigation mapped to each threat with an implementation owner. |

## Procedure

1. Read each input with spgr-read-artifact. If the system diagram, data flows, API surface, or auth model is missing or contradictory, or the compliance classification is absent, stop and raise spgr-escalate with the precise list of what is missing. Do not infer trust boundaries from an assumption.
2. Decompose the system. List every component, data store, and external entity. Record the privilege level of each.
3. Draw trust boundaries before enumerating any threat. Place a boundary at every point where data crosses between components of different privilege levels. Annotate the data flow diagram with these boundaries.
4. Enumerate threats with STRIDE. Evaluate every component and every data flow against all six categories: Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege. If a category does not apply to an element, record an explicit one-line justification. Silence is not allowed.
5. Rate each threat by likelihood times impact. State the rating basis so it can be reviewed.
6. Map a mitigation to each threat. Name the threat the mitigation addresses, the data flow or component it protects, and the implementation owner. Reject generic entries such as "use HTTPS". Write the targeted form, for example "encrypt the user to API data flow to prevent information disclosure from network interception".
7. Tag the Security Agent and any other relevant vertical with spgr-tag-vertical-agent where a mitigation falls in another vertical's domain (auth, compliance), and record the recommendation.
8. Record consequential analytical choices with spgr-log-decision. Write the artifact with spgr-write-artifact and validate inline. Version it with spgr-version-artifact on revision and on human approval.
9. When an upstream architecture change introduces a new service or new data flow, flag the threat model for review rather than letting it go stale. Re-run steps 2 through 8 against the changed elements.

## Notes

- Output type is an envelope artifact written via spgr-write-artifact. The threat-model type has no registered content schema yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered.
- Reference upstream artifact fields through spgr-read-artifact and the schema registry rather than restating them here.
- A skipped STRIDE category without a written justification is an incomplete model. Treat it as a validation failure and escalate.
