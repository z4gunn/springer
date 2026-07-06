---
name: spgr-run-sast
description: Produce a SAST findings report that runs static analysis against the codebase or a PR diff, triages each finding, and returns a PASS or GATE verdict that blocks merge or release on any unresolved confirmed Critical or High finding. Use when the Security Agent runs a full-codebase scan before a release or the DevOps Agent wires SAST into CI.
---

# run-sast

## Purpose

Run static application security testing against source code and produce one triaged, severity-prioritized findings report. SAST is the cheapest point in the lifecycle to find a vulnerability, because the fix is a code change rather than incident response. SAST tools also produce false positives, so this skill triages every finding rather than treating a raw scanner hit as a confirmed vulnerability. The report is the gate input that decides whether a PR merges or a release proceeds, and the running record of the project's source-level security posture across scans.

## Inputs

| Field | Description |
|-------|-------------|
| `scan-target` | The codebase for a full release scan, or a PR diff for a CI merge gate, read via spgr-read-file. The target selects the gate behavior in step 7. |
| `ruleset` | The SAST tool configuration: OWASP Top 10 rules, language-specific security rulesets, and the project's custom rule registry, read via spgr-read-file. |
| `suppressions` | Known false-positive suppressions from prior scans, each tied to a specific rule ID with a justification comment, read via spgr-read-artifact when a prior scan exists. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `sast-report` | Envelope artifact written via spgr-write-artifact, recording the tool and ruleset version, every finding with severity, file path, line number, rule ID, and description, the triage classification per finding (confirmed, false positive, needs-investigation), the Critical and High confirmed findings flagged for blocking resolution, severity counts for trend tracking, and a PASS or GATE verdict. |

## Procedure

1. Confirm the inputs. Read the scan target via spgr-read-file, the ruleset and custom rule registry via spgr-read-file, and prior suppressions via spgr-read-artifact. If the scan target or the ruleset is missing, stop and call spgr-escalate with the precise missing path rather than scanning against an incomplete ruleset.

2. Run the scanner. Use Semgrep with OWASP Top 10 and language-specific security rulesets as the recommended tool, or CodeQL for a GitHub-hosted project. Apply the project's custom rule registry alongside the standard rulesets so previously fixed anti-patterns are caught.

3. Record each finding with severity (Critical, High, Medium, Low), file path, line number, rule ID, and description. Capture the tool name and ruleset version on the report so the scan is reproducible.

4. Triage every finding. Classify each as confirmed, false positive, or needs-investigation. Do not treat a raw scanner hit as a confirmed vulnerability. A finding that requires judgment beyond this skill stays needs-investigation and is handed to the Security Agent via spgr-tag-vertical-agent.

5. Honor suppressions only when each is tied to a specific rule ID with a justification comment at the finding location. Mass suppression of an entire rule category is not acceptable. Treat a category-wide suppression as invalid and report the underlying findings as open.

6. Encode new anti-patterns as custom rules. When a security issue is found and fixed, add a Semgrep rule for that anti-pattern to the custom rule registry so it cannot recur. This is the project-specific rule registry that step 2 applies on every later scan.

7. Decide the verdict. Return GATE if any confirmed Critical or High finding is neither remediated nor covered by a valid suppression. Critical and High confirmed findings block the merge on a PR diff and block the release checklist on a full scan. Medium findings are tracked in the security backlog and do not gate. Otherwise return PASS.

8. Write the report via spgr-write-artifact with inline spgr-validate-artifact. Log the verdict, the triage decisions, and any accepted suppression via spgr-log-decision. On a GATE verdict, call spgr-escalate so the blocking findings reach the release owner, and on a PR diff surface the findings at the file and line.

## Notes

- Output type is an envelope artifact (a findings report with a gate verdict). The `sast-report` type has no registered content schema yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered. Still call it inline.
- Version each successive scan via spgr-version-artifact so severity counts form a trend rather than a single snapshot.
- The gate threshold is exact: a confirmed Critical or High finding that is not remediated or validly suppressed blocks the merge or release. Medium findings go to the security backlog. Do not soften the Critical or High gate to a recommendation.
- This skill runs the scanner and reports triaged results. It does not modify application code to fix a finding. Remediation is a separate developer change that follows test-first discipline and is verified by spgr-run-tests and CI.
- The CI scan on a PR diff gates merge and is DevOps-managed. The full-codebase scan at each release gates the release checklist and is Security-Agent-managed. When a finding touches another role's domain, tag it via spgr-tag-vertical-agent.
