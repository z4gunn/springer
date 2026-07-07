---
name: spgr-tag-vertical-agent
description: Consult a vertical specialist agent on a specific artifact section, capturing a structured recommendation and any required amendment. Use when a PM, Architect, or Developer agent reaches a decision in a vertical's domain (security, compliance, auth, accessibility, performance, billing) and needs specialist review before finalizing.
---

# tag-vertical-agent

## Purpose

Move specialist review to design time instead of after the fact. A horizontal agent has broad responsibility but limited depth in every vertical. This skill creates a focused consultation: the vertical receives only the section context and the question, returns a structured recommendation with a confidence signal, and the horizontal agent incorporates it or escalates if it conflicts with another constraint. Proactive tagging prevents the expensive rework of discovering a vertical concern after implementation.

## Inputs

| Field | Description |
|-------|-------------|
| `vertical_agent` | Agent slug to consult, for example `security`, `compliance`, `auth`, `accessibility`, `performance` |
| `section` | The artifact section under review |
| `question` | The specific concern the vertical must address |
| `context` | A self-contained excerpt. The vertical must not need the whole artifact to answer |
| `artifact_ref` | ID or path of the source artifact |
| `response_urgency` | `blocking` (the horizontal agent waits) or `non-blocking` (continue with a flag) |

## Outputs

| Artifact | Description |
|----------|-------------|
| `consultation` | Artifact of type `consultation`: `consultation_id`, `vertical_agent`, `question`, `artifact_ref`, `section`, `recommendation`, `confidence`, `action_required`, `amended_section` |

## Procedure

1. Confirm `context` is self-contained. If it cannot be written concisely, the section under review is too large and should be split before tagging.
2. Write the consultation request with `spgr-write-artifact` (type `consultation`).
3. Route to the vertical agent. For `blocking`, halt finalization of the section until the vertical responds. For `non-blocking`, finalize the section with a `proposed` confidence signal and incorporate the response in a later revision pass.
4. Record the vertical's `recommendation`, `confidence`, `action_required`, and any `amended_section`. Log it with `spgr-log-decision`.
5. After the response, check `amended_section` against constraints other verticals recorded on the same artifact. If they conflict, escalate with `spgr-escalate` rather than choosing arbitrarily.

## Notes

- Use `blocking` for the high-stakes verticals: security, compliance, auth. Use `non-blocking` where a later revision pass is acceptable.
- A subagent cannot spawn a subagent. When the main agent is the Orchestrator, it performs the consultation as a routed handoff. The vertical's response returns as a consultation artifact, not a nested agent call.
