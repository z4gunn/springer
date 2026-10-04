---
name: spgr-run-harness
description: Drive a Springer run autonomously through the Plan-Do-Check-Act loop, pausing only at the human gates its autonomy level fires. Use to start a run, advance it, or resume it after a checkpoint. Run this in the main session, never as a subagent, because it dispatches the orchestrator and domain agents as subagents.
---

# run-harness

## Purpose

Turn the orchestrator from a one-shot router into a running loop. The orchestrator
decides the next unit of work and stops. This skill is the engine around it: it
reads run state, asks the orchestrator what runs next, dispatches the work,
checks the result, persists the transition, and loops, pausing only at the
human gates the run's autonomy level fires. It runs in the main session and owns all run-state writes, so there
is exactly one delegation hop and one writer. For the state machine, the
rehydration algorithm, the parallel barrier, and the learnings rules, see
[../../references/pdca-harness.md](../../references/pdca-harness.md).

## Inputs

| Field | Description |
|-------|-------------|
| `run_id` | The run to drive. A new run-id creates the store, an existing one resumes it |
| `problem_statement` | Required only when creating a new run, the seed the first phase consumes |
| `mode` | `run` drives until a gate or completion, `tick` runs one cycle and returns |
| `autonomy` | Optional on a new run. `supervised`, `standard`, or `autopilot`, recorded in the run brief `flags.autonomy`. Defaults to standard on brochure and small and supervised on saas and mobile. See Autonomy levels in the reference |
| `profile` | Required on a new run. One of `brochure`, `small`, `saas`, `mobile`. Scales the phase set, the story and criteria caps, and the PR unit per the run-profiles table in the reference. Recorded in the run brief and read from there on resume |

## Outputs

| Artifact | Description |
|----------|-------------|
| `pdca-cycle` | One immutable record per tick, the run's source of truth |
| `run-state` | The derived projection, refreshed after every tick |
| `hil-checkpoint` | Written when the loop pauses at a human gate |
| `run-retrospective` | Written at run completion |
| `run-brief` | `runs/<run-id>/run-brief.json`, the profile, flags, pinned rulings, and operative artifact list, refreshed at Act |
| `pending-defaults.md` | `runs/<run-id>/pending-defaults.md`, one line per deferrable decision a unit took by default, reviewed in a batch at the next gate |

## Procedure

1. Rehydrate. On every entry, claim the run with
   `scripts/claim-run.py <run-dir> claim <session-id>`. If it exits 1 another
   session holds the run: stop and report the holder. Then run
   `scripts/derive-ready-queue.py <run-dir> --session <session-id>`. If
   the snapshot lists `unjoined_dispatches`, stop: an agent from a prior cycle
   has no completion event, and planning against a tree it may still be writing
   is forbidden. Wait for it, or append an `agent_abandoned` event with its
   tool_use_id to `events.jsonl` once it is known dead, then re-enter. For each
   gate in `answered_gates`, stamp its hil-checkpoint resumed, consume the
   response (mark accepted defaults, open a fold-in for each overturned one),
   and add its held batch to this tick. If the snapshot is blocked by a gate
   that holds all work, stop and report that the run is waiting on a human. A
   gate that holds only some work does not stop the run. Start and resume are
   the same path. Read the run brief
   and the story briefs the pending batch names. Do not re-read the artifact
   corpus. On a new run only, run `scripts/preflight.py --profile <profile>`
   and record its table in the run brief, write the run brief with the profile
   from the problem statement's `profile:` line and the autonomy level, and
   pin the advisory learnings set once with `scripts/pin-learnings.py` over the
   available prior run-retrospective artifacts, and record it in
   run-state.learnings_pinned so the run is reproducible. Whenever the run will
   continue past this step, run `scripts/launch-dashboard.py <run-dir>`. The
   dashboard is opt-in: the launcher opens it in a separate terminal window
   only when the developer has turned it on, is a no-op when a dashboard is
   already watching the run, and always exits 0, so it never blocks the run.
   When the human asks to turn the run dashboard on or off, run
   `scripts/launch-dashboard.py on` or `off`, which persists the choice in
   runs/_dashboard/config.json.
2. Plan. Pass the readiness snapshot and every open escalation to the
   spgr-agent-orchestrator subagent. The snapshot carries the profile, the
   autonomy level, and the `held` list of what open gates hold. The
   orchestrator holds any unit outside the profile's phase set and any unit an
   open gate holds, and routes everything else. Each tick re-runs
   `derive-ready-queue.py` first and consumes any gate newly in
   `answered_gates` as step 1 does, because the human may answer while the
   loop is still running. Receive a routed
   batch: each unit names the
   agent, its input artifact refs, and the expected outcome. Enforce the phase
   gate the orchestrator reports, do not route into a new phase while a prior
   -phase artifact is unconfirmed. Pass the pinned learnings too. The orchestrator
   may cite a learning as proposed rationale in the cycle decision log, but every
   routing decision derives from the artifacts and config, never from a learning
   alone. When a unit's story touches UI error or retry paths, cascade or
   foreign-key delete paths, or pagination, the batch carries the pre-build
   vertical consultations ahead of the build unit, per the reference.
3. Do. Dispatch each routed unit to its domain agent as a subagent. When the
   batch holds several independent units, dispatch them in one turn so they run in
   parallel, in the foreground and never with `run_in_background`, and do not
   proceed to Check until every dispatched agent has
   returned. If a background dispatch is ever used, append an `agent_joined`
   event with its tool_use_id to `events.jsonl` when its task notification
   arrives, because the hook cannot see a background agent finish. Every unit
   prompt names the files to read in order, the binding rulings, the gating
   check command, the working directory (the unit's own worktree under
   `.worktrees/` whenever the batch holds more than one build unit, created
   by spgr-create-branch in worktree mode) with the absolute run-store path,
   and the report format, and every report pastes its
   verification output and quotes any unmet obligation verbatim, per the
   dispatch contract in the reference. A report that describes a check rather
   than pasting it counts as unverified. Write the brief to
   `runs/<run-id>/dispatch/<cycle-id>/<unit-id>/brief.md` and point the
   prompt at it, require the full report in `report.md` beside the brief and
   a return under fifteen lines carrying a status of DONE,
   DONE_WITH_CONCERNS, BLOCKED, or NEEDS_CONTEXT, and before any review unit
   cut the diff with `scripts/review-package.py <base> <head> --out
   <unit-dir>/review.md` so the reviewer reads the package and this session
   never reads the diff. The turn boundary is the fork-join barrier, and because all run-state
   writes happen here in the main session after the barrier, there is a single
   writer. Collect the artifacts each agent wrote. Agents never write run state.
   Dispatch under the token-economy rules and the dispatch-tier table in
   [../../references/pdca-harness.md](../../references/pdca-harness.md). A
   bounded fix goes to a FRESH agent with a tight prompt, never a resumed
   heavy-transcript agent. Units point at the story brief plus cited artifact
   sections rather than the full corpus. Mechanical units (version, archive,
   render-doc, story-brief refresh, chore commits) go to a haiku subagent
   through the model override, never inline in this session. Units verify with
   scoped test runs and leave whole-suite proof to CI.
4. Check, mechanical first. Validate every produced artifact by running
   `python3 schemas/validate.py <artifact>` directly, and open
   spgr-validate-artifact only when the script reports a failure, so the green
   path costs no model tokens. Run the project check script or the scoped test
   files the unit named, and read CI on the PR head. Do not re-run an agent's
   verification by hand, re-derive a finding it reported, or open artifacts to
   re-read claims a script covers. A claim no script can check is recorded as
   unverified. Run each command in a code-review artifact's `cannot_verify`
   list and fold the result into the verdict. Dispatch a vertical audit only when the diff touches that
   vertical's surface, as read-only subagents in parallel, and wait for all to
   return. On brochure and small, the Code Reviewer carries the Accessibility
   checklist in its pass and Accessibility is dispatched only to re-check a
   fix by execution. A change touching only `runs/`, `docs/`, or the run ledgers gets no
   review and no audit. Compare the actual
   outcome against the expected outcome from Plan. Reduce to one verdict: pass,
   fail, gate, or blocked. An audit that returns GATE, or any open Critical or
   High finding, forces a hard stop, never an advance. See Mechanical Check in
   the reference.
5. Act. Append one pdca-cycle artifact with the plan, the dispatched batch, the
   check verdicts, and the act transition. Refresh the projection with
   `scripts/rebuild-projection.py <run-dir>`. Version or archive any superseded
   artifact with spgr-version-artifact and spgr-archive-artifact. Append each
   default a unit report lists to `pending-defaults.md` as one DEF line, per the
   defaults ledger in the reference. When
   `runs/_linear/config.json` exists with `backlog_provider` set to `linear`,
   also refresh the Linear board projection with
   `npx tsx scripts/linear-sync.ts sync-run <run-dir>`. A sync failure is
   logged in the cycle decision log and never blocks the transition, because
   the board is a projection, not run state. When the cycle changed a story's
   operative contract or rulings, refresh the story context brief
   (`artifacts/story-brief-<story-id>.json`, a few thousand tokens: operative
   refs, pinned rulings, open conditions, merge-bar state) so later units read
   it instead of the full artifact corpus. Refresh the run brief when a ruling
   landed or an artifact was versioned. Remove the worktree of every unit
   whose PR is now open with `git worktree remove .worktrees/<branch>`,
   keeping the branch, and report a refused removal rather than forcing it. Record a fold-in as one line and apply
   it through a haiku unit in this cycle or defer it, per the fold-in policy in
   the reference. Keep the cycle record to roughly 2k tokens. Then take the
   transition: advance and loop, retry, escalate by routing per the orchestrator
   rules, or pause. On a fail verdict, retry by filing a bug report with
   spgr-write-bug-report and a regression test, then routing the fix to the
   developer agent that owns the artifact. Bound retries: after two failed retries
   on the same unit, stop retrying and escalate to the human rather than looping.
   The first retry is a fresh agent at the unit's tier, the second a fresh
   agent one tier up that is told a prior implementer attempted the fix.
   Bound review the same way: one review pass and one scoped re-review that
   verdicts each prior finding ADDRESSED or NOT ADDRESSED, then adjudicate per
   the bounded fix loop in the reference: P0 and P1 go to the human at the
   gate as a list, and under standard or autopilot a P2 or P3 is parked as a
   defaults-ledger line with its cost if wrong.
6. Gate. Fire only the gates the autonomy level fires, per the autonomy table
   in the reference. Under standard and autopilot, hold the PRD approval, the
   intake questions, the architecture option, and the design direction for one
   direction-review checkpoint once both option units return, and fire no
   architecture-confirmation gate. Write the hil-checkpoint with pipeline_status
   paused, its `holds` per the holds table in the reference, and the units it
   holds as `held_batch`. Carry every intake question and every open line of
   `pending-defaults.md` in its `decisions`. Fire spgr-notify-human. Then keep
   looping on the work the gate does not hold. When the gate holds all work, or
   the orchestrator returns an empty batch while a gate is open, set the act
   transition to pause and terminate cleanly. Resuming is step 1 on the next
   entry. Render `docs/` for the artifacts this gate reads, and only those,
   through a haiku spgr-render-doc unit. A pr-merge gate fires once per batch
   or per page, not per story. When the run brief sets `auto_merge_on_green`
   on a brochure or small profile, or the run is on autopilot, a Code Reviewer
   APPROVE plus fully green required checks merges the PR with
   `gh pr merge --squash` and the run advances without a gate, unless the PR
   carries a `TODO(DEF-<n>)` placeholder or an open blocking question. Otherwise, for a pr-merge gate, first publish: once all automated sign-offs pass, commit
   the change on its story branch, push to origin, and open the PR with
   spgr-create-pr against the protected base. Then wait for the remote CI checks
   on the PR head and confirm every required check passes BEFORE writing the
   checkpoint, because a green local suite is not sufficient. CI runs the live-DB,
   integration, and other jobs the local Check skips (for example DB-gated
   D-suites), and those jobs are the real gate on that work. If any required check
   fails, treat it as a Check failure on this cycle, diagnose it from the CI logs,
   route the fix as a bounded retry to the owning agent (same two-retry bound,
   then escalate), push, and re-verify, before pausing. Only on a fully green
   required-check set write the checkpoint carrying the PR URL and pause. Never
   pause or report the story ready while a required check is failing or pending.
   Outside auto-merge the harness pushes and opens but never merges. The human
   merge is the gate and is read as the checkpoint response on resume. While it
   is open, the next file-disjoint batch builds on its own branch in its own worktree. A local-only unpushed branch is
   used only when a human explicitly asks for it. See the pr-merge gate rule in
   [../../references/pdca-harness.md](../../references/pdca-harness.md).
   When the Linear board is active, attach the PR to the story's issue with
   `npx tsx scripts/linear-sync.ts link-pr <story-id> <pr-url>` after opening
   it. The story's move into the wip_board review column carries the issue to
   In Review through the Act-step sync, and the merge read on resume moves the
   story to the done column, which carries the issue to Done the same way.
7. Complete. When the orchestrator reports no further work, write the
   run-retrospective summarizing the run's learnings, each tagged with its
   category, its evidence cycle refs, and a requires_human_promotion flag that is
   true for any learning that would change a rule. Under autopilot, send the
   completion notice through spgr-notify-human with every open line of
   `pending-defaults.md` as a numbered list. Set the final cycle transition to
   complete, and stop.
8. Loop control. In `run` mode repeat from step 2 until a pause or completion,
   where a pause is a gate that holds all work or an empty batch while a gate
   is open, re-claiming the run at each tick so the lock heartbeat stays live. In
   `tick` mode return after one Act. Release the run with
   `scripts/claim-run.py <run-dir> release <session-id>` before terminating at
   a gate, at completion, or on any exit. Never exceed a WIP limit to make
   progress.

## Notes

- This skill must run in the main session. The orchestrator and domain agents are
  its subagents. A subagent cannot run this skill, because it would need to spawn
  its own subagents. See ADR-002.
- The pdca-cycle log is the source of truth. run-state is a rebuildable cache,
  never edited by hand, always regenerated by `rebuild-projection.py`. See ADR-001.
- Pause only at the checkpoint types the schema enumerates, and only at those
  the autonomy level fires. Inventing a gate violates minimal-human-in-the-loop.
  A deferrable decision is a defaults-ledger line under standard and autopilot,
  never a pause.
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
- The harness session runs on sonnet by default. The main session writes run
  state and the cycle record and dispatches. It does not verify by hand and does
  not author narratives.
- Session limits are account-wide: every subagent's spend shares the main
  session's window. The token-economy section of the reference is the operative
  rule set. Its origin case is a test-bed story where resumed heavy-transcript
  agents doing small fixes were the two most expensive dispatches of the run
  and both session-limit deaths.
