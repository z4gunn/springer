---
name: spgr-write-nfr
description: Produce an nfr artifact that states non-functional requirements as specific, measurable, testable targets across performance, availability, security, compliance, scalability, accessibility, data retention, and platform support, then flag the items that need a vertical specialist before architecture. Use when the PM Agent has gathered NFR inputs from a human and the Architect Agent needs concrete targets to design toward, or whenever a requirement set lists quality attributes that must become hard thresholds rather than aspirations.
---

# write-nfr

## Purpose

Turn a human's quality-attribute inputs into an nfr artifact whose every line is a target an architect can design toward and a QA agent can test against. NFRs decide whether the product is worth using once it is technically functional, and a vague NFR ("the app should be fast") produces architecture that cannot be tested or held to account. The contract here is the format every requirement must follow and the rule that a missing target is marked proposed and surfaced for confirmation rather than invented. NFRs drive architecture, so a round trip from the Architect saying the NFRs are vague is expensive. Get them specific at this stage.

## Inputs

| Field | Description |
|-------|-------------|
| `performance_targets` | Response time, throughput, and concurrency targets |
| `uptime_sla` | Required availability percentage and maximum acceptable incident duration |
| `compliance_needs` | Regulatory frameworks to comply with, for example GDPR, CCPA, SOC 2, HIPAA, PCI-DSS |
| `scale_targets` | Expected user count, data volume, and request rate at launch and at 12 months |
| `security_posture` | Auth model, data encryption, vulnerability disclosure policy |
| `platform_constraints` | Mobile OS versions, browser versions, accessibility standard and WCAG level |
| `data_retention` | Data retention and deletion requirements |

## Outputs

| Artifact | Description |
|----------|-------------|
| `nfr` | Structured NFR specification covering performance, availability, security, compliance, scalability, accessibility, data retention, and platform support |
| `architecture_constraints` | Summary of the NFR items most likely to constrain architecture choices, carried as a field of the nfr artifact |
| `vertical_flags` | NFR items that require a vertical agent review before architecture proceeds, surfaced through spgr-tag-vertical-agent |

## Procedure

1. Read each input field. For any field a human did not supply, do not invent a number. Set a minimum acceptable threshold, mark that section confidence `proposed`, and add the item to a list for human confirmation.
2. Write every requirement in the format `[dimension]: [specific threshold] at [specific load condition] measured by [specific method]`. Example: "API latency: p99 < 200ms at 1,000 concurrent authenticated users, measured by synthetic load test in staging." Reject any line that lacks a threshold, a load condition, or a measurement method, and rewrite it.
3. Map the inputs into the nfr schema sections: performance, availability, security, compliance, scalability, accessibility, data_retention, and platform_support. Treat compliance as high impact on architecture. GDPR data residency, HIPAA audit logging, and PCI-DSS network segmentation each reshape system design, so state their obligations explicitly.
4. Write the architecture_constraints summary, naming the NFR items most likely to drive or constrain the architecture so the Architect Agent sees them first.
5. Produce the artifact with spgr-write-artifact, which stamps the shared envelope, records per-section confidence, initializes the decision log, and runs spgr-validate-artifact against the registered nfr schema inline before write. Do not hand-build the envelope.
6. Determine vertical flags. Any compliance framework listed triggers a flag to the Compliance Agent. Any auth model other than standard OAuth or OIDC triggers a flag to the Security Agent. Immediately after the write, invoke spgr-tag-vertical-agent for Security, Compliance, Performance, and Accessibility to review their respective sections before the architecture phase begins.
7. If inputs contradict each other, or a required dimension cannot be made testable even as a proposed threshold, stop and raise spgr-escalate with a precise list of what is missing or conflicting rather than shipping an untestable NFR.
8. Log any consequential modeling choice, for example a proposed threshold or a resolved conflict, with spgr-log-decision so the reasoning is traceable. Surface the proposed-threshold list to the human through spgr-notify-human when the gathered set is ready for confirmation.

## Notes

- The nfr artifact type is registered in the schema registry at `schemas/` as `nfr-v1.json`. Reference field requirements through spgr-validate-artifact rather than inlining them here.
- A proposed threshold is a valid output state, not a failure. Mark the section `proposed` and confirm it with the human. An invented number presented as confirmed is the failure.
- Vertical flags gate the architecture phase. The nfr is not treated as ready for the Architect until the flagged verticals have reviewed their sections.
