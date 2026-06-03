---
name: spgr-validate-release-readiness
description: Produce a release-readiness verdict artifact (GO or NO-GO) by independently verifying that every release checklist item is actually complete, that all required agent sign-offs exist, and that CI is green on the release branch, with each NO-GO blocker naming its owning agent, the evidence needed to close it, and whether a human waiver is acceptable. Use when the DevOps Agent reaches the final gate before authorizing a deployment, or when the Orchestrator needs an evidence-backed GO or NO-GO before invoking the deployment, or when more than 24 hours have elapsed since the last readiness check and the state must be re-verified.
---

# validate-release-readiness

## Purpose

Verify, independently, that a release is safe to deploy. This is the last gate before deployment begins and is distinct from writing the checklist. Writing the checklist defines what must be true. This skill confirms that each item is actually true, not just marked complete. Checklists get checked off prematurely, so do not trust self-reported status. Collect evidence programmatically (artifact checksums, CI status, test result summaries) and verify it against the checklist. The output is a GO or NO-GO verdict that the Orchestrator gates the deployment on. A NO-GO is the system working correctly, not a failure. It is the last chance to stop a deployment that would have ended in a rollback.

## Inputs

| Field | Description |
|-------|-------------|
| `release-checklist` | The completed release checklist, every item with a claimed-complete status. Read with spgr-read-artifact. |
| `sign-off-artifacts` | Required agent sign-offs to verify against, for example the Security findings report, QA test results, and Compliance sign-off. Read each with spgr-read-artifact. |
| `ci-status` | Current CI status for the release branch, pulled at check time, not self-reported. |
| `release-branch-commit` | The exact commit the deployment will be built from, so CI status maps to the right source state. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `release-readiness-verdict` | Envelope artifact carrying a single verdict of GO or NO-GO. On NO-GO, a list of blocking items, each with the owning agent, the specific artifact or evidence needed to close it, and whether a human waiver is acceptable. Written via spgr-write-artifact. |

## Procedure

1. Read the release checklist with spgr-read-artifact. Record each item and its claimed status. Do not treat a claimed-complete item as complete yet.
2. Collect evidence independently rather than trusting self-report. Read each sign-off artifact with spgr-read-artifact and confirm its checksum and version match what the checklist references. Pull the CI status for the release branch at check time. Pull the test result summaries. An item is verified only when the evidence confirms it, not when the checklist says so.
3. Confirm CI is green on the release branch at the release commit. A red CI on the release commit is always a blocker, with no waiver.
4. For every checklist item, compare the claimed status against the collected evidence. Mark an item as a blocker when evidence is missing, stale, or contradicts the claim, or when a required sign-off artifact is absent or fails its own envelope validation.
5. If no blockers remain, set the verdict to GO. If any blocker remains, set the verdict to NO-GO. For each NO-GO blocker, name the owning agent, the specific artifact or evidence needed to close it, and whether a human waiver is acceptable.
6. Write the verdict via spgr-write-artifact and run spgr-validate-artifact inline. Record the verdict and its supporting evidence with spgr-log-decision.
7. On NO-GO, do not authorize deployment. Tag each owning agent with spgr-tag-vertical-agent so the blocker is routed, and raise spgr-escalate when a blocker needs a human waiver decision. Return the verdict to the Orchestrator so it gates the deployment invocation.
8. Re-run this skill from step 1 if more than 24 hours have elapsed between the last readiness check and the actual deployment window. State can change, so a stale GO is not valid.

## Notes

- Output type is an envelope artifact (a GO or NO-GO verdict report). The release-readiness-verdict type has no registered content schema yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered. Still call spgr-validate-artifact.
- Evidence is collected programmatically and verified, never accepted on self-report. Artifact checksums, CI status, and test summaries are pulled at check time.
- A red CI on the release commit is an unconditional blocker. No waiver applies.
- A NO-GO is a correct outcome. The goal is to catch issues before deployment, not to rubber-stamp the checklist.
- Use spgr-notify-human when the Orchestrator needs to surface a NO-GO or a waiver request to the human gate.
