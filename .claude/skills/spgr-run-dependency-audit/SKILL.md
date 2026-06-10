---
name: spgr-run-dependency-audit
description: Produce a dependency-audit report that scans direct and transitive dependencies for known CVEs, records each with its CVSS score, severity, and remediation path, tracks time-limited accepted exceptions, adds a dependency-freshness metric, and returns a PASS or GATE verdict that blocks release on any unremediated Critical or High CVE in a direct dependency. Use when the Security Agent runs a pre-release dependency scan, or when the DevOps Agent wires automated dependency scanning into the CI pipeline and needs the current vulnerability posture before a vulnerable package reaches production.
---

# run-dependency-audit

## Purpose

Scan the project's locked dependency tree for known vulnerabilities and produce one actionable, severity-prioritized remediation plan. Third-party dependencies are the largest attack surface in a modern application, and the set of known CVEs changes daily, so this audit is a continuous tracked concern rather than a one-time check. The report is the gate input that decides whether a release proceeds and the running record that lets the team watch severity counts and dependency age trend across audits.

## Inputs

| Field | Description |
|-------|-------------|
| `lockfiles` | One or more package lock files (`package-lock.json`, `yarn.lock`, `Pipfile.lock`, `go.sum`, and the like), read via spgr-read-file. Lockfiles are required so the scan resolves exact pinned versions across the full transitive tree. |
| `accepted-exceptions` | Previously accepted vulnerability exceptions, each with a justification and an expiry date, read via spgr-read-artifact when a prior audit exists. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `dependency-audit` | Envelope artifact written via spgr-write-artifact, listing every known CVE in direct and transitive dependencies with CVSS score, severity, and remediation path, the active accepted exceptions with justification and expiry, the dependency-freshness metric, severity counts by category for trend tracking, and a PASS or GATE verdict. |

## Procedure

1. Confirm the inputs. Read each lockfile via spgr-read-file and the prior exceptions via spgr-read-artifact. If no lockfile is present, or a declared dependency is not pinned to an exact version, stop and call spgr-escalate, because dependency pinning is required to prevent supply-chain substitution where a new version is published between CI and deploy.

2. Run the scanner that matches each ecosystem. Use `npm audit` for npm, `pip-audit` for Python, `govulncheck` for Go, or Snyk across all ecosystems for one consistent CVSS-scored output with upgrade paths. Resolve findings against both direct and transitive dependencies.

3. Record each CVE with its CVSS score, severity (Critical, High, Medium, Low), whether the affected package is a direct or transitive dependency, and a remediation path: upgrade to version X, switch to alternative package Y, or no fix available.

4. Reconcile accepted exceptions. For each prior exception, check its expiry. An exception is time-limited: 30 days maximum for Critical, 90 days maximum for High. An expired exception is no longer valid and its CVE returns to the open findings until re-accepted or remediated.

5. Compute the dependency-freshness metric. Track the average age of the dependency tree and flag the project when the tree has not been updated in more than 90 days.

6. Tally severity counts by category (Critical, High, Medium, Low, split by direct and transitive) so the trend is visible across audits.

7. Decide the verdict. Return GATE if any Critical or High CVE in a direct dependency is neither remediated nor covered by a current valid exception. Critical and High CVEs in transitive dependencies are addressed when a remediation path exists, and an unaddressed transitive Critical or High with a known fix also gates. Otherwise return PASS.

8. Write the report via spgr-write-artifact with inline spgr-validate-artifact. Log the verdict and any exception decisions via spgr-log-decision. On a GATE verdict, call spgr-escalate so the blocking findings reach the release owner before the release proceeds.

## Notes

- Output type is an envelope artifact (a findings report with a gate verdict). The `dependency-audit` type has no registered content schema yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered. Still call it inline.
- Version each successive audit via spgr-version-artifact so severity counts and the freshness metric form a trend rather than a single snapshot.
- The gate threshold is exact: unremediated Critical or High in a direct dependency blocks the release. Do not soften it to a recommendation.
- Exception expiry windows are hard limits, 30 days for Critical and 90 days for High. Record both the justification and the expiry on every accepted exception so the next audit can reconcile it.
- When a GATE verdict touches DevOps or Architecture concerns (for example a transitive CVE with no fix that forces a package swap), tag the relevant role via spgr-tag-vertical-agent.
