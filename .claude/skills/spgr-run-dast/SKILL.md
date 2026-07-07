---
name: spgr-run-dast
description: Run dynamic application security testing against a running staging environment, unauthenticated and authenticated as each role, producing a dast-findings report with per-finding evidence and a gate verdict that blocks on Critical and High findings. Use when the Security Agent runs DAST before a major release or architecture change.
---

# run-dast

## Purpose

Find vulnerabilities that only manifest at runtime. SAST reads source code, this skill exercises a running application, so it catches the configuration, deployment, and runtime-behavior flaws SAST misses, including broken access control between roles. DAST is active probing (crawling, fuzzing, attack injection), so it runs against staging only and never against production, where fuzzing or injection can contaminate real user data in a way that is not recoverable. This skill produces the per-run dast-findings evidence the Security Agent consolidates through spgr-write-security-findings. It does not consolidate or set the release security sign-off itself.

## Inputs

| Field | Description |
|-------|-------------|
| `staging_url` | The running staging environment to probe. Must not be a production URL |
| `test_credentials` | Authenticated test-account credentials per role type, injected from secrets at run time, never hardcoded or written into the report |
| `api_spec` | The API spec read via spgr-read-artifact, used to enumerate API endpoints for scanning |
| `scope_definition` | The URLs and API paths in scope for active testing, plus the exclusion list |

## Outputs

| Artifact | Description |
|----------|-------------|
| `dast-findings` | Report stating the tool and version used, every finding with severity, URL, parameter, attack type, and evidence, confirmed vulnerabilities with reproduction steps, false-positive assessments, the role-based access-control results, and the blocking gate verdict. Written via spgr-write-artifact with inline spgr-validate-artifact |

## Procedure

1. Read the inputs through spgr-read-file and spgr-read-artifact. Confirm `staging_url` resolves to a staging target. If it points at production, or is ambiguous, stop and raise spgr-escalate. Never run active probing against production.

2. Inject `test_credentials` from secrets at run time. If a credential for a role under test is missing, stop and raise spgr-escalate with the named role rather than skipping that role's access-control test silently.

3. Build the scan scope from `scope_definition` and `api_spec`. Enumerate API endpoints from the spec. Exclude logout endpoints, since repeated logout creates session noise, password reset endpoints, since repeated calls send email spam, and any endpoint that sends real notifications. Record the exclusion list in the report so a reader knows what was not probed.

4. Run the scan with OWASP ZAP in API scanning mode with authenticated sessions as the baseline tool. Burp Suite Pro is acceptable for a more thorough pass. Record the exact tool name and version in the report.

5. Run an unauthenticated pass first to find vulnerabilities reachable with no session.

6. Run an authenticated pass for each role type in `test_credentials`. For each role, test that permission enforcement prevents access to resources and actions outside that role, not only that an anonymous caller is blocked. A resource one role can reach that it should not is a broken-access-control finding. Record the role, the target URL, and the access result per check.

7. Capture per finding: severity, URL, parameter, attack type (for example SQL injection, reflected XSS, broken access control), and the request and response evidence. For each confirmed vulnerability, record reproduction steps precise enough to replay without a second scan.

8. Assess false positives. Mark each scanner finding as confirmed or false positive with the reason. A finding handed downstream without a confirmed-or-false-positive verdict is incomplete.

9. Set the gate verdict. Map severity by CVSS, Critical at or above 9.0 and High 7.0 to 8.9. The verdict is GATE when any confirmed Critical or High finding is open, and PASS when none remains. Medium and Low are tracked and do not set the gate on their own.

10. Produce the dast-findings artifact through spgr-write-artifact with inline spgr-validate-artifact. Record consequential calls, the tool choice, each false-positive verdict, and the gate decision, through spgr-log-decision. On a GATE verdict or any confirmed Critical or High finding, route to the Security Agent through spgr-tag-vertical-agent and notify the human through spgr-notify-human, since the security gate is a required human-in-the-loop checkpoint.

## Notes

- Output type is an envelope artifact. No content schema is registered for dast-findings yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered. Reference the schema registry at schemas/ rather than inlining field lists here.
- DAST is not a per-PR check. It is slow and needs a running environment, so it runs at minimum before each major release and after a significant architecture change. The continuous per-PR gate is spgr-run-security-scan.
- This skill runs scanners and reports results. It does not modify application code to fix a finding. Remediation is a separate developer change verified by spgr-run-tests and CI.
- Credentials are read from secrets at run time and never written into the report or the decision log. A GATE verdict is a correct output, not a failure of this skill.
