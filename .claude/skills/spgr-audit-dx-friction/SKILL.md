---
name: spgr-audit-dx-friction
description: Produce a developer-experience friction audit report that scores the development cycle against four friction surfaces (CI timing and flakiness, local setup, error-message quality, and tooling-automation gaps), records per-surface findings with a measured cost, tracks CI duration, flaky-test rate, and onboarding time across releases, and returns a prioritized improvement list ordered by impact-to-effort with a PASS or GATE verdict that gates on a fast CI suite over the time budget or a flaky-test rate above the threshold. Use when the DevOps Agent runs a DX health sweep at sprint start or before a release, or when a developer agent reports recurring workflow friction and needs evidence to justify a CI, setup, error-message, or tooling fix.
---

# audit-dx-friction

## Purpose

Developer-experience friction compounds. Every minute waiting for CI, debugging a local setup failure, or decoding a cryptic error is a minute not spent building, and the cost is paid on every pull request by every developer. Produce one audit report that locates the highest-friction points across the development cycle, attaches a measured cost to each, tracks the trend across releases, and ranks fixes by impact-to-effort so the DevOps Agent can eliminate friction systematically rather than one anecdote at a time.

Operate as the Developer Experience vertical in auditor mode. The report is advisory across most surfaces and a gate on two measured thresholds: a fast CI suite that exceeds its time budget, and a flaky-test rate above the failure-rate threshold. Both train developers to distrust signal, so both block until fixed or quarantined.

## Inputs

| Field | Description |
|-------|-------------|
| `ci_timing` | Build time per CI stage and the flaky-test failure frequency, from CI run history. Used for the CI friction surface and the duration and flakiness trend. |
| `developer_feedback` | What developers report as the most frustrating parts of the workflow. Ground truth, taken seriously even when the cause looks minor from outside. |
| `local_setup` | The local setup process: total time, manual-intervention steps, platform-specific issues, and how often it fails. Used for the setup friction surface and onboarding-time trend. |
| `error_quality` | A sample of developer-facing error messages from CI, build, and runtime, assessed for whether each is actionable or cryptic. |
| `prior_report` | The previous dx-friction-audit artifact, read for the per-surface trend (improving, stable, or degrading). Absent on the first run. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `dx-friction-audit` | An envelope artifact carrying per-surface findings with measured cost, the DX health trend (CI duration, flaky-test rate, onboarding time across releases), a prioritized improvement list ordered by impact-to-effort, and a PASS or GATE verdict. Written via spgr-write-artifact with inline spgr-validate-artifact. |

## Procedure

1. Read each input through spgr-read-file, and read the prior dx-friction-audit through spgr-read-artifact when one exists. If `ci_timing` and `developer_feedback` are both missing, the audit has no ground truth. Stop and raise spgr-escalate naming the missing inputs rather than auditing on assumption.

2. Audit the CI friction surface. Flag any fast-suite stage over the 5-minute time budget, any test with a failure rate above 1 percent without a code change, and any sequential stage that could run in parallel. CI timing is the surface that pays back fastest. A 20-minute pipeline costs every PR 20 minutes of waiting and discourages small focused PRs, so weight CI findings highest in step 7.

3. Audit the local-setup friction surface. Flag every step that needs manual intervention, every platform-specific failure, and a total setup time over 15 minutes. Record the failure rate of the setup process when `local_setup` reports it.

4. Audit the error-message friction surface. Flag cryptic errors that give no actionable next step and missing-config errors that omit the variable name. Quote the offending message and state the actionable form it should take.

5. Audit the tooling-automation gap surface. Flag common tasks performed by hand that have no one-command path, for example a missing database-reset command or a missing single-module test runner. Each gap is a candidate automation in the improvement list.

6. Compute the DX health trend. For CI duration, flaky-test rate, and onboarding time, compare this run against `prior_report` and mark each as improving, stable, or degrading. On the first run, record the baseline and mark the trend as baseline.

7. Build the prioritized improvement list. Score each finding by impact (the per-PR or per-developer time it costs, multiplied by frequency) over effort, and order the list by that ratio. Attach the measured cost to every entry so a reader can confirm the ranking.

8. Set the verdict. Return GATE when any fast-suite stage exceeds the 5-minute budget or any test exceeds the 1 percent flaky threshold, because both erode trust in CI signal. Flaky tests must be fixed or quarantined immediately, so list the specific tests and the required action. Return PASS when neither gate condition holds. All other findings are advisory and do not block.

9. Write the report through spgr-write-artifact with inline spgr-validate-artifact, set the per-surface confidence (confirmed for measured findings, proposed for findings inferred without data, needs-human-input where developer feedback is required and absent), and record the gate-threshold choices through spgr-log-decision. Version the report through spgr-version-artifact so the trend in step 6 has a stable predecessor.

10. Route fixes that another agent owns through a consultation rather than editing that agent's artifacts. Use spgr-tag-vertical-agent or the consultation artifact to hand CI-config and pipeline fixes to the DevOps Agent, error-message wording to the owning developer agent, and any cross-cutting gap to its owner. On a GATE verdict, raise spgr-notify-human only if the gate blocks a release in progress, otherwise leave the verdict for the consuming agent to act on.

## Notes

- Output type is an audit or review report (envelope artifact) carrying findings by surface and a PASS or GATE verdict. spgr-validate-artifact applies envelope-only validation to the `dx-friction-audit` type for now (header, confidence map, decision log, version); its content schema is registered in a later increment.
- Gate thresholds are exact and not negotiable per run: fast-suite stage over 5 minutes, flaky-test rate over 1 percent without a code change. These are the only two blocking conditions. Every other finding is advisory.
- A vertical recommendation reaches a horizontal agent through the registered consultation artifact (spgr-tag-vertical-agent), not by editing the other agent's output.
- Take developer feedback as ground truth even when the named friction looks minor from outside. A surface that developers report but the metrics do not yet show is a needs-human-input finding, not a dismissal.
