---
name: spgr-write-release-checklist
description: Produce a release-checklist artifact for one release version, listing every gate category with a named owner and a pending, complete, or waived status auto-populated from agent artifacts. Use when the DevOps Agent prepares a release and needs the explicit shippable gate, or when the Orchestrator Agent enforces a hard release gate.
---

# write-release-checklist

## Purpose

Produce the release-gate checklist that makes the criteria for shippable explicit and machine-verifiable for one named release version. Without it, every release is a judgment call by whoever coordinates it, and the meaning of ready drifts between releases. The checklist holds each release to the same standard and surfaces any gap before the deployment window. Scope the checklist to the release tier, since a patch release carries a shorter list than a major release. Write it as an envelope artifact for one release version, not as a reusable template.

## Inputs

| Field | Description |
|-------|-------------|
| `release-scope` | Which features, fixes, and infrastructure changes are in this release, and the release tier (patch, minor, major). Read via spgr-read-artifact. |
| `project-nfrs` | Which non-functional requirements are gate criteria for this release tier. Read via spgr-read-artifact (nfr). |
| `agent-sign-off-status` | Sign-off state from each relevant agent (QA, Security, Compliance, Accessibility, Observability, Documentation). Read each agent's artifact via spgr-read-artifact. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `release-checklist` | Envelope artifact for one release version. Gate categories below. Write via spgr-write-artifact with inline spgr-validate-artifact. |

Each gate category lists its items, and every item carries an owner (the agent or human responsible for sign-off) and a status of pending, complete, or waived with justification. The categories are:
- Code quality: all PRs merged to main, no open critical or high issues in code review.
- Test coverage: unit, integration, and E2E suites passing, coverage at or above the floor.
- Security: Security Agent sign-off, no open Critical or High findings, SAST and dependency scan clean.
- Compliance: Compliance Agent sign-off when in scope.
- Accessibility: Accessibility Agent sign-off on any UI changes.
- Observability: dashboards and alerts updated for new metrics and services.
- Documentation: API docs, changelog, and release notes current.
- Operational readiness: deployment runbook written, rollback plan written and tested in staging, on-call briefed.

## Procedure

1. Read the release scope, project NFRs, and each relevant agent's sign-off artifact through spgr-read-artifact. If the release scope does not name the release tier or every changed feature, fix, and infrastructure change, stop and call spgr-escalate, because an incomplete scope yields a checklist that misses a gate.
2. Select the gate categories and items for the release tier. Include a category only when it applies to this release. Drop the accessibility category when the release has no UI change, and drop compliance when no regulated data or framework is in scope. Keep the project NFRs that the tier names as gate criteria.
3. Assign each item an owner. The owner is the agent or human responsible for that sign-off, not the DevOps Agent compiling the list. Reference the deployment-runbook from spgr-write-deployment-runbook for the operational-readiness items.
4. Auto-populate each item's status from the owning agent's artifact. Read the artifact through spgr-read-artifact and mark the item complete only when that artifact records the passing state. A Security Agent artifact with a clean SAST and dependency scan and no open Critical or High finding marks the security item complete. An item with no supporting artifact, or one whose artifact records a failing or pending state, stays pending. Do not mark an item complete from inference.
5. For any item that must be waived, record the status as waived with a written justification and the human sign-off that approved it. A waiver requires explicit human sign-off through spgr-notify-human and a justification stored on the artifact. Never mark an item complete to skip it, and never waive an item without the recorded human approval.
6. Tag the vertical agent that owns any category whose status cannot be auto-populated through spgr-tag-vertical-agent, so the owner supplies the sign-off rather than the checklist guessing it.
7. Version the checklist to the release it describes through spgr-version-artifact, tying the version field to the release tag and following semantic versioning. A checklist written for one version is not reused for the next without review.
8. Validate the artifact inline with spgr-validate-artifact and log completion with spgr-log-decision. The checklist is a hard release gate, so do not signal ready while any item is pending or while any waiver lacks its recorded human sign-off.

## Notes

- Output type is an envelope artifact. There is no registered content schema for release-checklist yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered. Still call it.
- The checklist is a hard gate. The Orchestrator Agent blocks deployment while any applicable item is pending.
- A waiver is never a silent skip. It requires a written justification and explicit human sign-off stored on the release artifact.
- Status is auto-populated from the owning agent's artifact, never from inference. An item with no supporting artifact stays pending.
- Scope the checklist to the release tier. A patch release carries fewer gate items than a major release.
