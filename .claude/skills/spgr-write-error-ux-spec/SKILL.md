---
name: spgr-write-error-ux-spec
description: Produce an error-ux-spec artifact that maps each internal error category to its user-facing experience, covering the plain-language message, recovery actions, UI treatment, user-perceived severity, the empty-state versus error-state distinction, retry guidance, and a centralized error message registry ready for review and i18n. Use when the Resilience Agent has an error classification taxonomy and the user flows and must define how failures are communicated to users before any error UI is built, or when the Design Agent needs the error experience specified before translating it into components.
---

# write-error-ux-spec

## Purpose

Convert internal error categories into the user-facing experience for each one. Users do not need to know that a query failed or a request timed out. They need to know what happened in plain language, what they can do next, and that the product owns the failure. Produce one error-ux-spec artifact that the Resilience Agent owns and the Design Agent consumes. The spec is the source of truth for every user-facing error message, so it also seeds a centralized message registry that can be reviewed for consistency and translated for i18n.

This is a Resilience vertical artifact. The Resilience Agent defines the error categories and recovery options. The Design Agent translates them into UI components, so route the design-side recommendation through a consultation rather than editing the Design Agent's artifacts directly.

## Inputs

| Field | Description |
|-------|-------------|
| `error-taxonomy` | Error classification taxonomy from error standards, the list of internal error categories. Read via spgr-read-artifact or spgr-read-file. |
| `user-flows` | The user flows and the error states each flow can encounter. |
| `brand-voice` | Brand voice and tone guidelines that the messages must match. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `error-ux-spec` | Envelope artifact with one entry per error category, plus the message registry. Written via spgr-write-artifact, validated inline via spgr-validate-artifact. |

Each error category entry carries:
- User-facing message in plain language, no technical jargon, never blaming the user.
- Recovery actions available (retry, contact support, go back, try a different action).
- UI treatment (inline error, toast, full-page error, banner).
- User-perceived severity on two axes: blocking versus non-blocking, and permanent versus transient.
- Empty-state versus error-state distinction, since no results is not a system error and is treated differently.
- Retry guidance, present when the error is transient, telling the user it is temporary and offering a low-friction retry.

## Procedure

1. Read the inputs. Pull the error categories from the taxonomy via spgr-read-artifact, the affected flows, and the brand voice guidelines. If the taxonomy is missing, contradictory, or names categories with no recovery path defined, stop and raise spgr-escalate with the precise list of what is missing. Do not invent error categories.
2. For each error category, classify user-perceived severity on both axes (blocking or non-blocking, permanent or transient). This classification drives the message, the recovery actions, and the UI treatment.
3. Write the user-facing message for each category. Apply the message rules: never ship "Something went wrong" alone, since it gives no information and no recovery path. State what happened and what to do, for a generic 500 use a form like "We're having trouble loading this page. Try refreshing, and if the problem persists, contact support." Never blame the user for a server error. Own the failure on the product's behalf ("We couldn't process your request right now"), not on the user's ("Your request failed").
4. Assign recovery actions and UI treatment per category, matched to severity. A transient error offers a retry with minimal friction. A permanent error offers an alternative path or an escalation to support.
5. Separate empty states from error states. For any flow that can return no results, specify the empty-state copy and treatment distinctly from the error-state copy, and confirm the two are never collapsed into one message.
6. Build the error message registry: collect every user-facing message into a single keyed list inside the artifact so the messages can be reviewed for consistency, translated for i18n, and updated in one place rather than hunted through the codebase. Give each message a stable key.
7. Write the artifact via spgr-write-artifact and validate inline with spgr-validate-artifact. Set the per-section confidence map (confirmed, proposed, needs-human-input). Mark any category whose recovery path depends on an unbuilt support channel or an undecided alternative flow as needs-human-input. Record consequential choices with spgr-log-decision.
8. Route the design-facing recommendation to the Design Agent through spgr-tag-vertical-agent as a consultation. Do not edit the Design Agent's component or design artifacts directly. If global reach is in scope, tag the i18n vertical so the registry keys feed translation.

## Notes

- Output type is a spec envelope artifact (error-ux-spec). Its content schema is registered in a later increment, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, version). Still call it.
- Version revisions with spgr-version-artifact when the error taxonomy changes or new flows add error states.
- A vertical recommendation to a horizontal agent flows through the registered consultation artifact, not through a direct edit of the receiving agent's artifact.
