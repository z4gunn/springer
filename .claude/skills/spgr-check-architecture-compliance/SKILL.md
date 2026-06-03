---
name: spgr-check-architecture-compliance
description: Produce an architecture-compliance report that checks a PR diff against the project's confirmed ADRs and tech-stack decision, with a per-ADR finding, a blocking-versus-advisory status on each deviation, and an overall PASS or FAIL verdict. Use when the code-reviewer agent runs PR review and must confirm a change does not drift from the approved architecture, or when the architect agent checks one ADR domain against a change.
---

# check-architecture-compliance

## Purpose

Turn confirmed ADRs from documentation into enforcement. Read a PR diff and check it against every confirmed ADR whose domain the diff touches, plus the tech-stack decision, and report each deviation as blocking or advisory. Architecture drifts when individually defensible exceptions accumulate, so each confirmed ADR becomes a testable claim against any change that touches its domain. A first-time deviation from a significant pattern signals that the architecture may need to evolve, so route it to the architect rather than reject it outright.

## Inputs

| Field | Description |
|-------|-------------|
| `pr_diff` | The changed files and hunks under review, read with spgr-read-file. |
| `adrs` | The project's active ADR artifacts, read with spgr-read-artifact. Only confirmed ADRs are enforcement targets. |
| `tech_stack_decision` | The tech-stack-decision artifact, read with spgr-read-artifact, naming the approved technologies and the ones ruled out. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `architecture-compliance` | Report listing each ADR evaluated, the finding per ADR, the blocking-or-advisory status of each deviation, and an overall PASS or FAIL verdict. Written via spgr-write-artifact. |

## Procedure

1. Read the PR diff with spgr-read-file. Read the ADR set and the tech-stack-decision with spgr-read-artifact, which validates each against its registered schema before you consume it.
2. Filter the ADR set to confirmed ADRs only. Treat proposed or superseded ADRs as informational and exclude them from enforcement. Record in the report which ADRs were excluded and why.
3. For each confirmed ADR, determine whether the diff touches its domain. Skip ADRs whose domain the diff does not touch and note them as not-applicable.
4. For each applicable ADR, check the diff against the ADR's stated decision and constraints. Where an ADR constraint can be encoded as a static-analysis rule, prefer that over manual reading. Encode import-restriction and dependency rules so enforcement moves from review time toward compile time. Examples of encodable rules: forbid direct database access from HTTP handler files, forbid a raw HTTP client where the ADR requires the API client abstraction, forbid an import of a technology the tech-stack-decision ruled out.
5. Classify each deviation. Mark a deviation blocking when it introduces a new dependency on a technology an ADR or the tech-stack-decision explicitly ruled out, bypasses a required abstraction layer, or violates a stated constraint. Mark a deviation advisory when it is a style or convention drift that no confirmed ADR forbids.
6. Set the overall verdict. Return PASS when no blocking deviation is found. Return FAIL with a specific violation description, the offending file and line, and the ADR identifier for every blocking deviation found.
7. When a deviation is the first significant departure from an established architectural pattern, do not reject it outright. Call spgr-escalate to route it to the architect agent, because the architecture may need to evolve into a new or revised ADR. Record the escalation reference in the report.
8. Write the report with spgr-write-artifact, which runs inline spgr-validate-artifact before the write completes. Record any consequential classification call with spgr-log-decision.

## Notes

- Enforcement targets are confirmed ADRs only. Never enforce a proposed or superseded ADR.
- The architecture-compliance report is not yet in the registered schema list, so write it via spgr-write-artifact with its registered schema added in a later increment.
- A blocking FAIL gates the PR. An advisory finding informs the reviewer but does not block on its own.
- First-time deviations from a significant pattern escalate to the architect via spgr-escalate rather than failing the PR outright.
