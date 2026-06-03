---
name: spgr-run-compliance-audit
description: Produce a compliance-audit report that checks the implemented system against its compliance scope, classifying each in-scope control as implemented, partially implemented, or not implemented with specific verifiable evidence, recording gaps with regulatory-violation severity and remediation, building a control mapping matrix that links each framework requirement to the code or configuration that implements it, scoring readiness per framework, and returning a PASS or GATE verdict that blocks release for any project in scope for a regulated framework until the gaps are closed. Use when the Compliance Agent runs an internal readiness assessment before a formal external audit (SOC 2 readiness, GDPR DPA review, HIPAA), or when a regulated project needs the audit sign-off the release checklist requires.
---

# run-compliance-audit

## Purpose

Compliance specifications describe intent. Compliance audits verify implementation. The gap between them is where violations live. Run this audit internally before a formal external audit so gaps surface when they are cheapest to fix, before they become audit findings, enforcement actions, or customer-reported violations.

This skill operates the Compliance Agent in auditor and gate mode. The audit is evidence-based and verifiable. It does not accept that a control "looks configured." For each in-scope control it locates the specific code, database schema, or infrastructure configuration that implements the control and cites it as evidence. The audit scope covers the Minimum Security Baseline for each applicable framework, not the entire framework, and it records which controls are in scope and why.

## Inputs

| Field | Description |
|-------|-------------|
| `compliance-scope` | The frameworks that apply to the project and the per-framework requirements summary. Read with spgr-read-artifact (compliance-scope from spgr-assess-compliance-scope). Drives which controls are audited. |
| `data-classification` | The per-field sensitivity tiers and their encryption, retention, access-control, and breach-notification requirements. Read with spgr-read-artifact (data-classification). |
| `retention-policy` | The data retention and deletion rules to verify against implemented deletion and purge jobs. Read with spgr-read-artifact (retention-policy). |
| `audit-trail-spec` | The audit logging requirements to verify against implemented audit logging. Read with spgr-read-artifact (audit-trail-spec). |
| `implemented-system` | The code, database schema, and infrastructure configuration where controls are verified. Located with spgr-search-codebase and read with spgr-read-file. |
| `release-scope` | Optional. The changes in the pending release, used to scope the gate verdict to what is shipping. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `compliance-audit` | Audit report envelope artifact written via spgr-write-artifact. Carries the in-scope control list with rationale, a per-control assessment (implemented, partially implemented, not implemented) with cited evidence, the control mapping matrix, gaps with severity and remediation, a per-framework readiness score, and a PASS or GATE verdict. |

## Procedure

1. Read the inputs. Load the compliance scope first, because it sets which frameworks and controls are audited. If the compliance scope, the data classification, or access to the implemented system is missing, stop and raise spgr-escalate with the precise list of what is absent. Do not infer applicable frameworks or invent controls.

2. Build the in-scope control list. For each applicable framework in the compliance scope, list the Minimum Security Baseline controls that are in scope and record why each is in scope. Document controls excluded from the baseline so the audit boundary is explicit. Do not audit the entire framework.

3. Assess each control against the implemented system. For each in-scope control, locate the code, database schema, or infrastructure configuration that implements it. Classify the control as implemented, partially implemented, or not implemented. Treat every partial implementation as not compliant until the gap is closed. A retention policy that covers PII but not PHI does not satisfy HIPAA, and is recorded as not implemented for the PHI gap.

4. Cite specific, verifiable evidence for each control. Evidence names the exact artifact, not a summary. "Encryption at rest is configured" is not evidence. "AWS S3 bucket `prod-user-data` has default encryption enabled with KMS key `arn:aws:kms:...`" is evidence. For a control with no locatable implementation, record the absence as the finding.

5. Build the control mapping matrix. For each framework requirement, link to the code, configuration, or process that implements it. This matrix is the deliverable that accelerates evidence collection for the later formal audit, so make each link specific enough to verify directly.

6. Record gaps with severity and remediation. For each control that is partially implemented or not implemented, record a gap with a severity that reflects regulatory-violation risk and a specific remediation recommendation. A gap that exposes the project to an enforcement action or a reportable breach is highest severity and blocking.

7. Score readiness per framework. Compute a readiness score per applicable framework from the ratio of fully implemented in-scope controls to total in-scope controls. Report partial implementations as not compliant in this score.

8. Set the verdict. For a project in scope for any regulated framework, the blocking threshold is any in-scope control that is not fully implemented. If `release-scope` is supplied, score the verdict against only the controls the release touches. The verdict is GATE if any in-scope control is partially implemented or not implemented, otherwise PASS.

9. Write and validate the report. Write the `compliance-audit` artifact via spgr-write-artifact with inline spgr-validate-artifact. Record the verdict rationale and each blocking gap with spgr-log-decision. Version the report with spgr-version-artifact when it supersedes a prior audit.

10. Route remediation, do not patch other artifacts. For each gap owned by another agent (an auth control, an encryption configuration, a retention job, an audit log gap), route the recommendation through a consultation with spgr-tag-vertical-agent rather than editing that agent's artifact or code directly. A regulated project cannot release without Compliance Agent sign-off on this audit, so on a GATE verdict for a pending release surface the decision to the human gate with spgr-notify-human, since a compliance gap is a compliance flag.

## Notes

- Output type is a compliance audit report (envelope artifact). Its content schema is registered in a later increment, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, version).
- Blocking threshold: for a project in scope for a regulated framework, any in-scope control that is partially implemented or not implemented yields a GATE verdict. Partial implementations are not compliant until the gap is closed.
- Audit scope is the Minimum Security Baseline per applicable framework, not the entire framework. Record which controls are in scope and why.
- This audit reads, assesses, and reports only. It does not add encryption, write retention jobs, or change access control. Recommendations to other agents flow through spgr-tag-vertical-agent.
- Compliance audit results feed the release checklist. A regulated project cannot release without Compliance Agent sign-off on these results.
