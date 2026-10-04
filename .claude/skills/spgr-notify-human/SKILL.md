---
name: spgr-notify-human
description: Pause the pipeline at a human-in-the-loop checkpoint, deliver a scannable decision notification with options and consequences, and record the human response on return. Use when the pipeline reaches a required gate (architecture options, design-direction selection, PR merge, security or compliance flag, scope change) that needs human judgment.
---

# notify-human

## Purpose

Operate the human checkpoints that are the only required gates in Springer. The notification is formatted so a human can decide quickly: the decision prompt first, then options as a numbered list with the consequence of each. The pipeline pauses until a response returns, and the response is normalized and recorded so work can resume deterministically.

## Inputs

| Field | Description |
|-------|-------------|
| `checkpoint_type` | The gate, for example `direction-review`, `architecture-options-selection`, `prd-approval`, `design-direction-selection`, `pr-merge`, `security-compliance-flag`, `scope-change` |
| `artifact_ref` | The artifact the human is deciding on |
| `decision_prompt` | The single question the human must answer |
| `options` | List of `{option, consequence, cost_if_wrong}`, where `cost_if_wrong` names what it takes to reverse the choice later, and one option carries `recommended_because` |
| `context_summary` | Short context so the human need not open every artifact |
| `urgency` | `routine`, `urgent`, or `critical` |
| `decisions` | Optional. The separate decisions one sitting answers: intake questions, PRD approval, the architecture option, the design direction, and default-review items from `pending-defaults.md` |
| `holds` | What the gate holds, phase names, story or artifact ids, or `all`. Everything else keeps running |

## Outputs

| Artifact | Description |
|----------|-------------|
| `checkpoint` | Artifact of type `hil-checkpoint`: `checkpoint_id`, `checkpoint_type`, `artifact_ref`, `decision_prompt`, `options`, `context_summary`, `pipeline_status`, `response_received`, `resume_instruction`, `decisions`, `holds`, `held_batch`, `timestamp` |

## Procedure

1. Build the notification. Lead with the decision prompt, then the numbered options with consequences, each with its cost if wrong (what reversing it later takes) and exactly one marked recommended with the reason in one sentence, so the human can take the recommendation on a reversible choice and spend attention on the one-way doors, then the context summary and artifact links. When the checkpoint carries `decisions`, number every decision in one list, choices first (architecture option, design direction), then blocking questions, then non-blocking questions and default-review items each showing its recommended answer. Offer "accept all recommended" as a one-line answer, so the human only writes where they disagree. State what the gate holds and that other work continues.
2. Write the checkpoint with `spgr-write-artifact` (type `hil-checkpoint`) and set `pipeline_status` to `paused`.
3. Route by urgency. `critical` goes to a direct message plus push. `urgent` goes to a direct message. `routine` goes to a channel or the dashboard queue.
4. On response, normalize it. A button click is already structured. A free-text reply is mapped to the matching option before recording. Store it in `response_received`, and set each decision's `response`. "Accept all recommended" sets every decision that has a `recommended` value. An architecture option or design direction is never answered by accept-all and stays open until the human picks one.
5. Set `pipeline_status` to `resumed`, write the `resume_instruction`, and record the outcome with `spgr-log-decision`.

## Notes

- The architecture gate is intentionally the slowest. Encourage review over hours or days, not minutes, and do not auto-resume it on a timer.
- A checkpoint left unanswered keeps the work it holds paused. It does not default to an option. Work it does not hold continues.
