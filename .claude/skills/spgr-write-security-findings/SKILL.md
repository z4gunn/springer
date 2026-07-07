---
name: spgr-write-security-findings
description: Produce a security-findings artifact consolidating SAST, DAST, dependency-audit, threat-model, and auth-audit results into one prioritized, deduplicated report with a release gate status and a remediation per finding. Use when the Security Agent needs the single source of truth that gates the release-checklist security sign-off.
---

# write-security-findings

## Purpose

Security testing produces raw output from several tools and manual reviews that no downstream agent can act on directly. This skill consolidates and normalizes that output into one security-findings report that states what issues exist, which block release, and how each is remediated. The report is the artifact that gates the release-checklist security sign-off, so its release gate status must be unambiguous and its remediation guidance must be specific enough to act on without a second pass.

## Inputs

| Field | Description |
|-------|-------------|
| `sast_findings` | Static analysis results from spgr-run-sast |
| `dast_findings` | Dynamic analysis results from spgr-run-dast |
| `dependency_audit` | Dependency vulnerability results from spgr-run-dependency-audit |
| `threat_model` | Threat model read for coverage verification, that each modeled threat has a corresponding test or finding |
| `auth_audit` | Auth implementation audit results from spgr-audit-auth-implementation, when an auth surface exists |
| `release_version` | The release the report version-tracks with, for example v1.4.0 |
| `accepted_risks` | Prior accepted-risk records carried forward, each with justification, owner, and review expiry |

## Outputs

| Artifact | Description |
|----------|-------------|
| `security-findings` | Consolidated report with an executive summary, a deduplicated finding inventory, the release gate status, accepted-risk records, and a Critical/High trend across releases |

## Procedure

1. Read every supplied input through spgr-read-artifact. For each source that the spec expects but that is missing, do not treat absence as a clean result. Record the gap and carry it to the escalation step.
2. Normalize each raw finding into a common record with a finding ID, title, severity (Critical, High, Medium, Low), source tool, file or URL, description, and remediation recommendation. Keep the source tool on each record so provenance is traceable.
3. Deduplicate findings that describe the same issue across tools. List the issue once and note every tool that flagged it. Do not let the same vulnerability appear as separate Critical and High records that inflate the counts.
4. Write each remediation recommendation as a specific action, naming the package, version, or code location and the exact change. Write "upgrade lodash to 4.17.21 to resolve CVE-2021-23337", not "upgrade dependencies". Reject and rewrite any recommendation that does not name what to change and to what.
5. Verify threat-model coverage. For each threat in the model, confirm a corresponding finding or an explicit clean result exists. Record any threat with no coverage as a coverage gap and carry it to the escalation step, because an unassessed threat is not a passed threat.
6. Resolve accepted risks. A finding with a current accepted-risk record (unexpired review date, named owner, recorded justification) is tracked but not release-blocking. A finding whose acceptance has passed its review expiry returns to its base severity and is re-evaluated against the gate.
7. Compute the release gate status. The status is BLOCK when any open Critical or High finding has no current accepted exception. The status is PASS only when no open Critical or High finding remains without an accepted exception. Medium and Low findings are tracked and never set the gate on their own.
8. Write the executive summary with total finding counts by severity and the blocking versus non-blocking split, then the release gate status as the first scannable line.
9. Build the posture trend. Read the Critical and High counts from prior releases' findings reports in the artifact store and plot this release against them so a reader can see whether the security posture is improving or degrading over time.
10. Produce the artifact with spgr-write-artifact, which stamps the shared envelope, records per-section confidence, initializes the decision log, and runs validation inline before write. Do not hand-build the envelope. Stamp the report to release_version with spgr-version-artifact so the v1.4.0 report is retained for the audit trail and is not overwritten by the next release.
11. If a required input is missing, if threat-model coverage has a gap, or if inputs conflict (for example a tool reports a finding the audit marks fixed), stop and raise spgr-escalate with a precise list of what is missing or contradictory rather than issuing a PASS on incomplete evidence.
12. When the gate status is BLOCK, or any Critical or High finding is newly accepted as a risk, route the report to the human through spgr-notify-human, because the security gate is a required human-in-the-loop checkpoint. Log each consequential call, a dedup decision, a coverage judgment, or an accepted risk, with spgr-log-decision so the reasoning is traceable in the audit trail.

## Notes

- The security-findings artifact is written via spgr-write-artifact, and its registered schema is added to the schema registry at `schemas/` in a later build increment. Until then, validate structure through spgr-write-artifact rather than inlining field lists here.
- A BLOCK gate is a correct output, not a failure of this skill. The failure is a PASS issued without complete evidence or with an uncovered threat.
- The findings report is release-scoped and immutable once stamped. Each release keeps its own report for audit, so never edit a prior release's report to reflect a later fix.
