---
name: spgr-write-risk-register
description: Produce a risk-register artifact that lists each known project risk with a category, likelihood, impact, computed risk score, mitigation, owner, status, and a likelihood-by-impact heat map, then update it at each phase gate. Use when the Product Manager Agent has scope, technical decisions, and external dependencies and must name and track project threats before a go/no-go or phase gate, when the Architect Agent contributes technical risk entries, or when a newly discovered risk must be added to an existing register.
---

# write-risk-register

## Purpose

Convert vague anxiety about what might go wrong into a structured, reviewable list of named risks, each with a likelihood, an impact, a computed score, a mitigation, an owner, and a status. A risk is something that might happen, not something that already has. Keep this register separate from any issue log. The register is a living artifact, so produce a new version at each phase gate and whenever a risk is discovered, rather than treating it as a one-time deliverable.

## Inputs

| Field | Description |
|-------|-------------|
| `scope` | Project scope from the PRD and NFR artifacts, read via spgr-read-artifact |
| `technical-decisions` | Architecture, tech-stack decision, and third-party dependencies, read via spgr-read-artifact |
| `external-dependencies` | External APIs, compliance requirements, and team or schedule constraints |

## Outputs

| Artifact | Description |
|----------|-------------|
| `risk-register` | Envelope artifact written via spgr-write-artifact, one entry per risk plus a likelihood-by-impact heat map |

Each risk entry carries these fields.

| Field | Description |
|-------|-------------|
| `risk-id` | Stable identifier, sequential within the register |
| `title` | Short name for the risk |
| `description` | What could go wrong |
| `category` | One of technical, compliance, schedule, external, resource |
| `likelihood` | Low, Medium, or High |
| `impact` | Low, Medium, or High |
| `risk-score` | Likelihood times impact, mapping Low=1, Medium=2, High=3 |
| `mitigation` | Action that reduces the likelihood or the impact |
| `owner` | The agent or human responsible for the mitigation |
| `status` | One of open, mitigated, accepted, closed |

## Procedure

1. Read the scope, technical decisions, and external dependencies via spgr-read-artifact. If a prior risk-register version exists, read it so this run extends it rather than replacing its history.
2. Identify candidate risks across all five categories. For each, write a description that names a future event, not a past one. If an input describes something that has already happened, treat it as an issue and exclude it from this register.
3. Assign a likelihood and an impact from the Low, Medium, High scale to each risk. Compute the risk score as likelihood times impact using Low=1, Medium=2, High=3, so scores range from 1 to 9.
4. Write a mitigation for each risk that reduces either its likelihood or its impact, and assign an owner, naming the responsible agent or the human.
5. Set each status to open, mitigated, accepted, or closed. Carry closed risks forward in the register for retrospective value rather than deleting them.
6. Build the heat map: plot every open risk on a 3-by-3 grid with likelihood on one axis and impact on the other, so the score distribution is visible at a glance. Place each open risk in its likelihood-impact cell by risk-id.
7. Record the confidence map for each section, marking entries as confirmed, proposed, or needs-human-input. Mark any risk proposed for accepted status as needs-human-input, since accepting a risk is a human decision.
8. For any risk you intend to set to accepted, escalate via spgr-escalate to obtain explicit human sign-off before the status is confirmed. Do not record a risk as accepted on agent judgment alone.
9. Tag the Architect Agent via spgr-tag-vertical-agent when a technical risk needs an entry that depends on architecture or third-party-dependency detail outside this skill's inputs.
10. Write the register via spgr-write-artifact and run spgr-validate-artifact inline. If validation fails, correct the artifact and re-validate before returning. Log the register decision via spgr-log-decision and version the artifact via spgr-version-artifact at each phase-gate update.

## Notes

- Output type is an envelope artifact (risk-register). The risk-register content type is not yet registered in the schema registry, so spgr-validate-artifact applies envelope-only validation, checking the header, confidence map, decision log, and version, until a content schema is registered.
- A risk is not an issue. An issue has already happened, and a risk might happen. Keep them in separate registers and exclude issues from this one.
- Accepted risks require explicit human sign-off via spgr-escalate. Accepting a risk means choosing to proceed despite it with full awareness of the consequence.
- Re-run this skill at each phase gate and on each new discovery, versioning via spgr-version-artifact so the register stays current and its history stays recoverable.
