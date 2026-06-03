---
name: spgr-diagnose-error
description: Produce an error-diagnosis from a stack trace, error log, or failing test output, with a root-cause statement, affected components, an evidence-backed confidence level, and a ranked list of remediation options. Use when the backend, frontend, mobile, or QA developer agent hits a failing test or a runtime error and must find the root cause from evidence before writing a fix, rather than guessing at a change.
---

# diagnose-error

## Purpose

Turn a stack trace, error log, or failing test output into a structured diagnosis that names the root cause, cites the evidence, states a calibrated confidence, and ranks the remediation options. The contract matters because an unstructured fix is a guess, and a guess can make the failure worse while hiding the real cause. This skill forces evidence before action and makes the fix decision auditable. It diagnoses only. It does not apply the fix.

## Inputs

| Field | Description |
|-------|-------------|
| `error_output` | The stack trace, error log output, or failing test output. Read existing log or test-output files with spgr-read-file. |
| `triggering_operation` | What operation triggered the error (the request, the test, the user action). |
| `environment` | Which environment the error occurred in (local, CI, staging, production), and the runtime versions in play. |
| `recent_changes` | Relevant recent code, dependency, or config changes, including the diff or commit range when available. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `error-diagnosis` | A diagnosis holding the root-cause statement, the affected component or components, a confidence level (high, medium, low) with rationale, the supporting evidence as specific lines from the trace or log, and a ranked list of remediation options each with its tradeoff. |
| `error-pattern-library/<signature>.md` | An optional entry added to or matched against the error pattern library, mapping a known error signature to its root cause and standard remediation. |

## Procedure

1. Read the error output. If it points to a file on disk, load that file with spgr-read-file. Capture the exact failing line, the exception type, and the innermost frame of the trace.
2. Check the environment first when the failure reproduces in one environment but not another. Record the environment differences (runtime version, config, feature flag state, data state) before reading any code. An "it works on my machine" report is not diagnosable until the relevant environment delta is captured.
3. Match the error signature against the error pattern library before investigating from scratch. On a match, start from the recorded root cause and standard remediation and confirm the evidence fits this instance.
4. Trace the failure from the innermost frame outward. Tie each step to a specific line in the trace or log. Do not assert a cause that the evidence does not support.
5. Escalate immediately, do not diagnose in place, when the error is security-relevant: an auth failure, a permission error, an injection-like pattern, or any leak of a secret or credential into the output. Raise it with spgr-escalate and tag the security or auth vertical with spgr-tag-vertical-agent. Stop here for that path.
6. Assign a calibrated confidence. High means the evidence strongly implicates one root cause and a fix is unlikely to need rework. Medium means the evidence implicates a cause but a fix may need one iteration. Low means the evidence is ambiguous.
7. Escalate, do not guess, when the evidence cannot support at least medium confidence. Raise a precise request for the missing input with spgr-escalate: more verbose logging, a minimal reproduction case, or the output of a named diagnostic step. Do not fill the gap with an assumed cause.
8. Rank the remediation options most-likely-to-fix first, each with its tradeoff. State for each whether it addresses the root cause or only the symptom.
9. Name the regression test that the fix must include: the test that would have caught this error. The fix is incomplete without it, and the developer agent writes it test-first with spgr-write-acceptance-criteria and spgr-run-tests when applying the fix.
10. Write the diagnosis with spgr-write-artifact and validate it inline with spgr-validate-artifact against its registered schema. Record the chosen root cause and the rejected alternatives with spgr-log-decision. On a new confirmed signature, add a pattern library entry with spgr-write-file.

## Notes

- The error-diagnosis is an envelope artifact written via spgr-write-artifact. Its registered schema is added to the schema registry at /Users/gunderer/Repos/springer/schemas/ in a later increment. Validate through spgr-validate-artifact rather than inlining a field list here.
- This skill does not write or apply the fix. It hands a ranked, evidence-backed diagnosis to the developer agent, which applies the fix test-first under XP discipline and writes the named regression test before the implementation.
- Confidence is a contract, not a courtesy. A medium or low confidence is a signal to the receiving agent that the fix may iterate, and a low confidence with a missing-input escalation is the correct output when the evidence is thin.
- The error pattern library accelerates known failure modes only. A library match still requires the current evidence to fit before the recorded root cause is asserted.
