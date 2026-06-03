---
name: spgr-write-platform-permissions
description: Implement mobile platform permission request flows as source code, one handler per required permission, with a pre-prompt rationale screen, the OS request call, grant and graceful-denial handlers, a settings-redirect path for the don't-ask-again state, a before-every-use status check, and a per-permission grant-rate metric. Use when the Mobile Developer agent has confirmed permission requirements from the PRD and NFRs and a platform target (iOS, Android, or both) and must build the permission flow test-first, or when the QA or code-reviewer agent needs the handlers built against acceptance criteria before review.
---

# write-platform-permissions

## Purpose

Build the mobile permission flow for one feature so a permission is requested correctly on the first attempt. On iOS the OS dialog is a one-shot prompt and a denial is recoverable only through the Settings app, so a value explanation must precede the OS dialog. Each handler degrades gracefully on denial, re-checks status before every use because a permission can be revoked from Settings at any time, and records a grant-rate metric so under-converting prompts surface. The output is source code, not an envelope artifact.

## Inputs

| Field | Description |
|-------|-------------|
| `permission-requirements` | The permissions the product needs and the user-facing value of each, from the PRD and NFRs. Read with spgr-read-artifact. |
| `platform-targets` | iOS, Android, or both. Determines which platform APIs and version-specific behaviors apply. |
| `acceptance-criteria` | The confirmed Given/When/Then set for the permission story, from spgr-write-acceptance-criteria. The handlers are built only to satisfy these. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Permission handler source | One handler per required permission, written via spgr-write-file: pre-prompt rationale UI, OS request call, grant handler, denial handler, settings redirect, before-every-use status check, and grant-rate metric instrumentation. |
| Failing-then-passing tests | A test per permission covering granted, denied-recoverable, and denied-don't-ask-again states, written failing before any handler code. |

## Procedure

1. Read the permission requirements and acceptance criteria with spgr-read-artifact, and confirm the platform targets. If a requested permission has no stated user-facing value, no acceptance criterion, or no platform target, do not invent one. Call spgr-escalate with the precise list of what is missing and stop.

2. Confirm each permission enables an optional feature, not the core experience. If any requirement makes core app functionality depend on a permission that gates an optional feature, call spgr-escalate. The app must run fully without an optional-feature permission.

3. Write the failing test first for each permission, one per state: granted enables the dependent feature, denied-recoverable degrades and offers re-request where the platform allows, denied-don't-ask-again degrades and routes to Settings. Run them with spgr-run-tests and confirm they fail before writing any handler code.

4. Implement the pre-prompt rationale UI shown before the OS dialog. State the value of the permission in product terms. Trigger the OS request only after the user acknowledges the rationale.

5. Implement the OS permission request call for each platform target. On Android 13 and later, use the per-notification permission. On iOS 14 and later, request approximate location when full precision is not needed. Do not request a coarser or finer scope than the feature requires (YAGNI).

6. Implement the grant handler to enable the dependent feature, and the denial handler to disable the dependent feature and show a non-blocking explanation of what was lost without interrupting the core flow.

7. Implement the settings redirect for the denied-but-recoverable state. On iOS, open the app Settings page. On Android, show educational UI and re-request if the system still allows it, otherwise open Settings.

8. Implement the status check that runs before every use of a permission-gated feature, not only on first launch, so a permission revoked from Settings is detected.

9. Instrument a grant-rate metric per permission type at the point of the OS response, so prompts that under-convert are identifiable. Build only the metric the requirements name (YAGNI).

10. Run spgr-run-tests and confirm every test now passes. Format and lint clean, then commit one logical change with spgr-git-commit. Log any non-obvious flow decision with spgr-log-decision.

## Notes

- The output is mobile source code verified by spgr-run-tests and CI, not by an envelope schema.
- Test-first is required. The state tests must be confirmed failing before any handler code is written, per step 3.
- A permission grant-rate dashboard in the developer debug menu, covering all permission states, is deferred until a debug-menu surface exists. Note the deferral and do not build it speculatively.
- One commit per logical change. Keep the rationale UI, the request call, and the handlers in a single coherent change for one permission rather than splitting across unrelated commits.
