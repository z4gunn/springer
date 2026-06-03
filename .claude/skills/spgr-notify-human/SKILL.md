---
name: spgr-notify-human
description: Pause the pipeline at a human-in-the-loop checkpoint, deliver a scannable decision notification with options and consequences, and record the human response on return. Use at the required gates (architecture options, design-direction selection, PR merge, security or compliance flag, scope change) where work must not proceed without human judgment.
---

# notify-human

## Purpose

Operate the human checkpoints that are the only required gates in Springer. The notification is formatted so a human can decide quickly: the decision prompt first, then options as a numbered list with the consequence of each. The pipeline pauses until a response returns, and the response is normalized and recorded so work can resume deterministically.

## Inputs

| Field | Description |
|-------|-------------|
| `checkpoint_type` | The gate, for example `architecture-options-selection`, `prd-approval`, `design-direction-selection`, `pr-merge`, `security-compliance-flag`, `scope-change` |
| `artifact_ref` | The artifact the human is deciding on |
| `decision_prompt` | The single question the human must answer |
| `options` | List of `{option, consequence}` |
| `context_summary` | Short context so the human need not open every artifact |
| `urgency` | `routine`, `urgent`, or `critical` |

## Outputs

| Artifact | Description |
|----------|-------------|
| `checkpoint` | Artifact of type `hil-checkpoint`: `checkpoint_id`, `checkpoint_type`, `artifact_ref`, `decision_prompt`, `options`, `context_summary`, `pipeline_status`, `response_received`, `resume_instruction`, `timestamp` |

## Procedure

1. Build the notification. Lead with the decision prompt, then the numbered options with consequences, then the context summary and artifact links.
2. Write the checkpoint with `spgr-write-artifact` (type `hil-checkpoint`) and set `pipeline_status` to `paused`.
3. Route by urgency. `critical` goes to a direct message plus push. `urgent` goes to a direct message. `routine` goes to a channel or the dashboard queue.
4. On response, normalize it. A button click is already structured. A free-text reply is mapped to the matching option before recording. Store it in `response_received`.
5. Set `pipeline_status` to `resumed`, write the `resume_instruction`, and record the outcome with `spgr-log-decision`.

## Notes

- The architecture gate is intentionally the slowest. Encourage review over hours or days, not minutes, and do not auto-resume it on a timer.
- A checkpoint left unanswered keeps the pipeline paused. It does not default to an option.
