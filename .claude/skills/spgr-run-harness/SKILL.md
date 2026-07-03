---
name: spgr-run-harness
description: Drive a Springer run autonomously through the Plan-Do-Check-Act loop, advancing artifact to artifact between the five human gates and recording each tick as an immutable cycle record. Use to start a run, to advance an in-progress run to completion or the next gate, or to resume a run after a human has answered a paused checkpoint. Run this in the main session, never as a subagent, because it dispatches the orchestrator and domain agents as subagents.
---

# run-harness

## Purpose

Turn the orchestrator from a one-shot router into a running loop. The orchestrator
decides the next unit of work and stops. This skill is the engine around it: it
reads run state, asks the orchestrator what runs next, dispatches the work,
checks the result, persists the transition, and loops, pausing only at the five
human gates. It runs in the main session and owns all run-state writes, so there
is exactly one delegation hop and one writer. For the state machine, the
rehydration algorithm, the parallel barrier, and the learnings rules, see
[../../references/pdca-harness.md](../../references/pdca-harness.md).

## Inputs

| Field | Description |
|-------|-------------|
| `run_id` | The run to drive. A new run-id creates the store, an existing one resumes it |
| `problem_statement` | Required only when creating a new run, the seed the first phase consumes |
| `mode` | `run` drives until a gate or completion, `tick` runs one cycle and returns |

## Outputs

| Artifact | Description |
|----------|-------------|
| `pdca-cycle` | One immutable record per tick, the run's source of truth |
| `run-state` | The derived projection, refreshed after every tick |
| `hil-checkpoint` | Written when the loop pauses at a human gate |
| `run-retrospective` | Written at run completion |

## Procedure

1. Rehydrate. On every entry, run `scripts/derive-ready-queue.py <run-dir>`. If an
   open gate now carries a response, stamp its hil-checkpoint resumed, consume the
   response, and prepare to continue from the pending batch the paused cycle
   recorded. If an open gate still has no response, stop and report that the run
   is waiting on a human. Start and resume are the same path. On a new run only,
   pin the advisory learnings set once with `scripts/pin-learnings.py` over the
   available prior run-retrospective artifacts, and record it in
   run-state.learnings_pinned so the run is reproducible. Whenever the run will
   continue past this step, launch the live dashboard with
   `scripts/launch-dashboard.py <run-dir>`. The launcher opens the dashboard in
   a separate terminal window, is a no-op when a dashboard is already watching
   the run or when SPGR_NO_DASHBOARD is set, and always exits 0, so it never
   blocks the run.
2. Plan. Pass the readiness snapshot and every open escalation to the
   spgr-agent-orchestrator subagent. Receive a routed batch: each unit names the
   agent, its input artifact refs, and the expected outcome. Enforce the phase
   gate the orchestrator reports, do not route into a new phase while a prior
   -phase artifact is unconfirmed. Pass the pinned learnings too. The orchestrator
   may cite a learning as proposed rationale in the cycle decision log, but every
   routing decision derives from the artifacts and config, never from a learning
   alone.
3. Do. Dispatch each routed unit to its domain agent as a subagent. When the
   batch holds several independent units, dispatch them in one turn so they run in
   parallel, and do not proceed to Check until every dispatched agent has
   returned. The turn boundary is the fork-join barrier, and because all run-state
   writes happen here in the main session after the barrier, there is a single
   writer. Collect the artifacts each agent wrote. Agents never write run state.
4. Check. Validate every produced artifact with spgr-validate-artifact. Fan out
   the always-active vertical audits relevant to the produced artifact type as
   read-only subagents in parallel, and wait for all to return. Compare the actual
   outcome against the expected outcome from Plan. Reduce to one verdict: pass,
   fail, gate, or blocked. An audit that returns GATE, or any open Critical or
   High finding, forces a hard stop, never an advance.
5. Act. Append one pdca-cycle artifact with the plan, the dispatched batch, the
   check verdicts, and the act transition. Refresh the projection with
   `scripts/rebuild-projection.py <run-dir>`. Version or archive any superseded
   artifact with spgr-version-artifact and spgr-archive-artifact. Then take the
   transition: advance and loop, retry, escalate by routing per the orchestrator
   rules, or pause. On a fail verdict, retry by filing a bug report with
   spgr-write-bug-report and a regression test, then routing the fix to the
   developer agent that owns the artifact. Bound retries: after two failed retries
   on the same unit, stop retrying and escalate to the human rather than looping.
6. Pause at a gate. Write the hil-checkpoint with pipeline_status paused, set the
   act transition to pause, record the pending batch in the cycle artifact, fire
   spgr-notify-human, and terminate cleanly. Resuming is step 1 on the next entry.
7. Complete. When the orchestrator reports no further work, write the
   run-retrospective summarizing the run's learnings, each tagged with its
   category, its evidence cycle refs, and a requires_human_promotion flag that is
   true for any learning that would change a rule. Set the final cycle transition
   to complete, and stop.
8. Loop control. In `run` mode repeat from step 2 until a pause or completion. In
   `tick` mode return after one Act. Never exceed a WIP limit to make progress.

## Notes

- This skill must run in the main session. The orchestrator and domain agents are
  its subagents. A subagent cannot run this skill, because it would need to spawn
  its own subagents. See ADR-002.
- The pdca-cycle log is the source of truth. run-state is a rebuildable cache,
  never edited by hand, always regenerated by `rebuild-projection.py`. See ADR-001.
- Pause only at the five enumerated checkpoint types. Inventing a sixth gate
  violates minimal-human-in-the-loop.
- Every open escalation is fed into Plan each tick, so no blocked item sits
  unrouted. A constraint conflict with approved architecture routes to escalation,
  never an auto-fix that edits an ADR.
- Cross-run learnings are advisory and pinned by hash at run start. A learning
  never changes a rule on its own. A learning that would change a WIP limit, the
  gate set, or a routing policy carries requires_human_promotion and is applied
  only through a human gate. See ADR-004.
- The artifact contracts (pdca-cycle, run-state, run-retrospective) live in the
  schema registry at `schemas/`. Reference them through spgr-validate-artifact
  rather than restating field lists here.
