---
name: spgr-run-security-scan
description: Run SAST, dependency vulnerability, and secrets scanning against the codebase and package manifests, then produce a prioritized scan-report with CWE and CVE references, per-finding remediation, and a blocking summary of the Critical and High findings that gate the PR or release. Use when the QA, developer, or code-reviewer agent needs an automated security gate on a PR or scheduled sweep, before a PR is allowed to merge or a release is signed off.
---

# run-security-scan

## Purpose

Execute the automated security gate for a PR or scheduled sweep. Run static application security testing (SAST), dependency vulnerability scanning, and secrets scanning, then consolidate the raw tool output into one prioritized scan-report with a concrete remediation per finding and an explicit blocking list. This skill enforces the security baseline continuously. It does not replace the security design review owned by the Security Agent through spgr-write-threat-model and spgr-write-security-findings. It produces the per-run scan evidence those activities consume.

## Inputs

| Field | Description |
|-------|-------------|
| `codebase` | Source files to scan with SAST and secrets scanning |
| `dependency_manifest` | package.json, requirements.txt, go.mod, Gemfile.lock, or equivalent for the dependency scan |
| `scan_trigger` | `pr`, `scheduled`, or `pre-commit`, which selects the scan set and gate behavior |
| `prior_baseline` | Optional prior scan-report read via spgr-read-artifact, to report new findings only as a delta |

## Outputs

| Artifact | Description |
|----------|-------------|
| `scan-report` | Source-code-derived report with an executive summary (counts by severity, blocking vs non-blocking, delta to baseline), SAST findings, dependency findings, secrets findings, and a blocking summary. Written via spgr-write-artifact once its schema is registered |
| `bug-report` | One bug-report per actionable finding, written via spgr-write-artifact with inline spgr-validate-artifact against the bug-report schema |

## Procedure

1. Read the inputs through spgr-read-file and, when a baseline is supplied, spgr-read-artifact. Confirm the dependency manifest and a lockfile are present. If the manifest or lockfile is missing, stop and raise spgr-escalate with the precise missing path rather than scanning a partial dependency tree.

2. Run SAST with Semgrep as the primary tool and SonarQube as the supplementary deep pass. Capture per finding: tool name, severity, CWE reference, file path and line number, description, and a code snippet.

3. Run the dependency scan with Snyk preferred, Dependabot as the GitHub-native fallback, and OWASP Dependency-Check as the offline option. Capture per finding: package name and version, CVE, severity, vulnerable version range, patched version, and whether the dependency is direct or transitive.

4. Run secrets scanning with TruffleHog or GitLeaks. On `pre-commit` this is the only required step and it blocks the commit on any verified credential, so no secret reaches the remote. On `pr` and `scheduled` it runs alongside the other scans.

5. Map each finding to a severity tier by CVSS. Critical is CVSS at or above 9.0 and is a P0 bug that blocks all deployment. High is CVSS 7.0 to 8.9 and is a P1 bug that blocks release. Medium is CVSS 4.0 to 6.9 and is a P2 bug that must be scheduled. Low and Informational are P3 and are batched. Any verified committed secret is treated as Critical.

6. Write a concrete remediation per finding, not a generic flag. Name the version bump or code change, for example update lodash from 4.17.15 to 4.17.21 to fix CVE-2021-23337, prototype pollution, CVSS 7.2. Reject any finding entry that lacks at least one specific fix option.

7. Honor false-positive suppressions only when they are inline at the finding location with an explaining comment, for example a nosemgrep line for the specific rule id. Treat a blanket scan-wide suppression as invalid and report it as an unresolved finding.

8. Build the executive summary and the blocking summary. The blocking summary lists every Critical and High finding with its remediation status. When a baseline was supplied, report new findings as the delta and flag a rising High count across runs for the Security Agent to review.

9. Apply the gate for the trigger. On `pr`, surface findings as inline PR comments at the file and line, and report a fail gate status when any Critical or High finding is present and unresolved. On `scheduled`, a newly disclosed Critical CVE against an existing dependency raises a notification to the Security Agent through spgr-notify-human and spgr-tag-vertical-agent even with no code change.

10. File a bug-report per actionable finding through spgr-write-artifact with inline spgr-validate-artifact. Record the gate decision and any accepted suppression through spgr-log-decision. Where a finding needs a judgment on false-positive status or complex remediation, hand it to the Security Agent through spgr-tag-vertical-agent rather than deciding it here.

## Notes

- The scan-report is source-code-derived evidence, not a registered envelope artifact yet. Write it via spgr-write-artifact with its registered schema added in a later increment. The per-finding bug-reports validate against the registered bug-report schema through spgr-validate-artifact.
- Reference field lists through the schema registry at schemas/ via spgr-validate-artifact rather than inlining them here.
- Accepted findings are not permanently acceptable. Track each in a security backlog and schedule it for remediation so the baseline never silently degrades.
- This skill runs scanners and reports results. It does not modify application code to fix a finding. Remediation is a separate developer change that follows test-first discipline and is verified by spgr-run-tests and CI.
