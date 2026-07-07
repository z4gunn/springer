---
name: spgr-review-api-consistency
description: Produce an api-consistency review report that checks an API spec against the project's API design standards, returning a PASS or GATE verdict that blocks new or changed endpoints on any high-severity inconsistency. Use when the API Design Agent reviews a PR that adds or modifies API endpoints.
---

# review-api-consistency

## Purpose

Enforce that a developer consuming the API can correctly guess how a new endpoint behaves from how existing endpoints behave. Each individually defensible deviation compounds into a surface with no predictable pattern. This review compares the API spec against the project's API design standards, files every divergence as a severity-ranked finding, and gates new or modified endpoints on high-severity inconsistency. Operate as the API Design vertical in auditor and gate mode. The standard pattern always wins. When a deviation is an objectively better design, the remedy is to revise the API design standards through a consultation, not to approve the exception in this report.

## Inputs

| Field | Description |
|-------|-------------|
| `api-spec` | The OpenAPI or Swagger document under review, read via spgr-read-artifact or spgr-read-file. |
| `api-design-standards` | The project's API design standards document, read via spgr-read-artifact. The authority every finding is measured against. |
| `existing-endpoints` | The established endpoint set, read from the spec, used to evaluate consistency against patterns already in production. |
| `pr-scope` | The set of endpoints the PR adds or modifies, used to separate blocking new-endpoint findings from scheduled retroactive ones. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `api-consistency-review` | A review report envelope artifact written via spgr-write-artifact. Carries findings grouped by category and severity, the standard pattern and a corrected example per finding, the blocking threshold, and a PASS or GATE verdict. |
| `consultation` | When a deviation is the better design, a registered consultation via spgr-tag-vertical-agent recommending an api-design-standards revision, rather than an edit to the spec or the standards document. |

## Procedure

1. Read the api-design-standards via spgr-read-artifact and the api-spec via spgr-read-artifact or spgr-read-file. If either is missing, contradictory, or has no rule covering a checked category, stop and raise spgr-escalate with the precise list of what is missing. Do not fill gaps with assumptions.
2. Generate or run the lint rule set derived from the standards. Use Spectral or an equivalent OpenAPI linter to automate the naming-convention, HTTP-verb-usage, and response-envelope-shape checks. Treat lint output as evidence, not as the verdict.
3. Check naming consistency: endpoint path naming, HTTP verb usage against the action, and query-parameter naming. File each deviation as a finding.
4. Check resource modeling: nesting depth consistency across resources and ID representation consistency. File each deviation.
5. Check the response envelope: pagination shape and error envelope shape across endpoints. Check error response shape, pagination shape, and ID format first, since these three are the most impactful consistency targets.
6. For each finding, record category, the offending endpoint, the standard pattern it violates, a corrected example, and a severity. Set severity high when the deviation breaks consistency with the established pattern. Set severity low for stylistic inconsistency.
7. Apply the gate. Set the blocking threshold at any high-severity finding on an endpoint in pr-scope. New-endpoint high-severity findings are blocking before the endpoint ships. Findings on existing endpoints are scheduled, not blocking, and are recorded as retroactive remediation. Set the verdict to GATE when any blocking finding exists, otherwise PASS.
8. When a finding's deviation is an objectively better design than the standard, do not approve it here. Raise a consultation via spgr-tag-vertical-agent recommending the api-design-standards be revised, and keep the finding open until the standards change.
9. Write the report via spgr-write-artifact with inline spgr-validate-artifact. Record the gate decision and the blocking threshold via spgr-log-decision. On a GATE verdict, the report is the blocking signal to the PR. When a human decision is needed on a scope or standards change, route it via spgr-notify-human.

## Notes

- Output type is a review report (api-consistency-review), written as an envelope artifact. Its content schema is registered in a later increment, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, version).
- The standards document is the single authority. This report does not edit the api-spec or the standards document directly. It files findings and routes any standards change through a consultation.
- Blocking is scoped to pr-scope. A high-severity finding on a pre-existing endpoint outside the PR is scheduled remediation, not a gate.
