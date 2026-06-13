---
name: spgr-write-tech-stack-decision
description: Produce a tech-stack-decision artifact that documents the selected technology stack layer by layer, with a pinned version, selection rationale, rejected alternatives, version-pinning decision, upgrade policy, and dependency-audit schedule for each layer, traced back to the approved architecture and its ADRs. Use when the Architect Agent has an approved architecture option and team and budget constraints and must turn an implicit technology choice into an explicit, reviewable record before the project is scaffolded.
---

# write-tech-stack-decision

## Purpose

Turn an implicit technology choice into an explicit, reviewable decision the project will be scaffolded from. The contract here is that every layer carries a pinned version, an honest record of the alternatives that were rejected, a version-pinning decision, and an upgrade policy, so future contributors do not have to guess the reasoning and the stack does not accumulate two libraries that solve the same problem. This document must match the scaffold-project output exactly, so every entry is concrete and versioned rather than aspirational.

## Inputs

| Field | Description |
|-------|-------------|
| `approved_architecture` | The architecture option the human approved, read from its artifact |
| `team_constraints` | Existing expertise, hiring market, tooling familiarity |
| `budget_constraints` | Licensing costs and hosting costs that bound the choices |

## Outputs

| Artifact | Description |
|----------|-------------|
| `tech-stack-decision` | Layer-by-layer record covering language and version, primary framework, database (primary and any secondary), cache layer, message queue or event bus, infrastructure and hosting, mobile platform if applicable, and key libraries and tooling |

## Procedure

1. Read the approved architecture artifact with spgr-read-artifact so the stack is selected against the architecture the human approved, not against an unconstrained field of options. If the architecture is not yet human-approved, stop and raise spgr-escalate. The stack must not be decided ahead of its gate.
2. Identify every layer the architecture requires. For each layer, produce one entry. Do not select two technologies that solve the same problem within a layer. If the architecture implies that overlap, resolve it to one choice and record the reason in the entry. A language layer that runs on a JavaScript runtime (Node, browser, or a JS-based mobile runtime) must record TypeScript, never plain JavaScript, per the Generated Code Standards hard rule in CLAUDE.md and the baseline in `.claude/references/typescript-standards.md`. Recording plain JavaScript is an escalation, not a valid decision.
3. For each entry, record the selected technology with its exact version, the rationale for selection weighed against the team and budget constraints, and the alternatives considered with the reason each was rejected. The alternatives record must be honest. At minimum the most obvious competitor to each choice appears and explains why it lost. "We did not consider alternatives" is not an acceptable entry.
4. For each entry, record the version-pinning decision as one of pin to major only, pin to minor, or pin to exact, and state the stability against security-patch-delivery tradeoff that drove it.
5. For each entry, record the upgrade policy: how often the layer is reviewed for upgrades, who approves an upgrade, whether minor and patch upgrades are automated, and a dependency-audit schedule for catching known vulnerabilities in the layer's transitive dependencies.
6. Link each entry back to the relevant ADR or architecture-decision artifact that drove the choice, so the stack is traceable to the decision that constrained it.
7. Produce the artifact with spgr-write-artifact, which stamps the shared envelope, records per-section confidence, initializes the decision log, and runs spgr-validate-artifact against the registered tech-stack-decision schema inline before write. Do not hand-build the envelope.
8. Log each consequential selection, particularly a close call between a chosen technology and a rejected alternative, with spgr-log-decision so the reasoning is preserved and not re-litigated downstream.
9. If a layer cannot be decided because the architecture is ambiguous, the team and budget constraints conflict (for example a required technology exceeds the budget or no team member can support it), or no honest alternative can be named, stop and raise spgr-escalate with a precise list of what is missing or conflicting rather than picking a technology on an assumption.

## Notes

- The tech-stack-decision artifact type is registered in the schema registry at `schemas/`. Reference field requirements through spgr-validate-artifact rather than inlining them here.
- This artifact feeds spgr-scaffold-project. The scaffold must match the selected technologies and pinned versions exactly, so an aspirational or unversioned entry is a defect, not a placeholder.
- A licensing or budget conflict on a layer is a constraint conflict, not a detail to absorb silently. Escalate it so the human can adjust the budget or accept a different technology.
