# PDCA harness reference

Detail for the spgr-run-harness skill: the per-tick state machine, the
rehydration algorithm, the parallel barrier and scheduling rules, gate and
escalation handling, the advisory-learnings mechanism, and the determinism
scripts. The skill body holds the loop. This file holds the rules behind it.

## Contents
- Roles and the single delegation hop
- The PDCA tick
- Verdict and transition table
- Rehydration: start equals resume
- Parallel Do: the barrier and disjoint scheduling
- Token economy and dispatch efficiency
- Pre-build vertical consultation
- Human gates
- Escalations
- Self-improvement: advisory learnings
- Linear board projection
- Determinism scripts
- Increment status

## Roles and the single delegation hop

The harness runs in the main session and is the only writer of run state. Each
tick it invokes the orchestrator agent for the routing decision and the routed
domain agents for the work, both as sibling subagents. The orchestrator returns
routing only and never invokes a domain agent. This keeps exactly one delegation
hop, so Springer's rule that a subagent cannot spawn a subagent holds by
construction. See ADR-002.

## The PDCA tick

Each tick runs four phases in order.

1. Plan. Run `derive-ready-queue.py` for the deterministic readiness snapshot
   (open gates, open escalations, confirmed-artifact inventory, latest phase,
   blocked flag). Pass the snapshot and the open escalations to the orchestrator.
   The orchestrator returns a routed batch (one unit in the sequential spine,
   several within WIP limits once parallel Do is enabled), each unit carrying the
   agent, its input artifact refs, and the expected outcome.
2. Do. Dispatch each routed unit to its domain agent. The agent reads its inputs
   and writes its artifact to the store. Agents return or write artifacts only.
   They never touch run state.
3. Check. Validate every produced artifact with spgr-validate-artifact. Fan out
   the always-active vertical audits read-only and in parallel. Compare the
   actual outcome against the expected outcome from Plan. Reduce to one verdict.
4. Act. Persist the transition: append one immutable pdca-cycle artifact, then
   refresh the projection with `rebuild-projection.py`, then version or archive
   any artifact that a transition supersedes. Carry out the transition the
   verdict implies, then loop back to Plan or terminate.

## Verdict and transition table

The Check verdict selects the Act transition.

| Verdict | Meaning | Act transition |
|---------|---------|----------------|
| pass | validation clean, audits PASS, outcome matched | advance, then loop |
| fail | validation failed or outcome mismatch | retry: route a fix, loop |
| gate | a human checkpoint is required | pause: write the checkpoint, terminate |
| blocked | an open escalation needs routing | escalate: route per the rules, loop or pause |

A complete transition is recorded when the orchestrator reports no further work
in any phase, which ends the run and triggers the retrospective.

An audit that returns GATE, or any open Critical or High finding, is a hard stop.
Act must route it and must never advance past it.

## Rehydration: start equals resume

The harness never blocks waiting on a human. It terminates at a gate and is
re-invoked later. Every entry, whether a fresh start or a resume, begins the same
way, so crash recovery and resume share one path. See ADR-003.

On entry:
1. Run `derive-ready-queue.py` to read the current store.
2. If an open gate now has a response, stamp that hil-checkpoint resumed, consume
   the response, and continue from the pending batch the paused cycle recorded.
3. If an open gate still has no response, exit immediately doing no work.
4. Otherwise resume the loop at Plan from the latest cycle's next phase.

The pending batch lives in the paused pdca-cycle artifact, not in checkpoint
prose, so resume is deterministic.

## Parallel Do: the barrier and disjoint scheduling

Multiple domain subagents dispatched in one main-session turn run concurrently.
The turn boundary is the fork-join barrier: the harness does not proceed to Check
or Act until every dispatched agent has returned. Because all run-state writes
happen in the main session after the barrier, there is a single writer and no
concurrent-write hazard.

Two rules keep a parallel batch safe.
- Disjoint work only. Co-scheduled units must be file-disjoint. If two units
  would edit the same file, the orchestrator serializes them instead.
- WIP limits are hard. At most two stories each in development, review, and
  validation, encoded as a maxItems cap in the run-state schema. Never exceed a
  limit to make progress. Queue the excess.

The read-only audit fan-out in Check parallelizes with zero contention and is the
low-risk half of parallelism.

## Token economy and dispatch efficiency

Session limits are account-wide and rolling: every subagent's spend counts
against the same window as the main session, so a story driven gate-to-gate in
one sitting can exhaust the window even when no single agent is oversized. The
reference case is one story in a test-bed run: roughly 3.7M subagent tokens and
two session-limit terminations, where the two most expensive dispatches were
resumed agents doing small fixes. A +18/-6 source fix cost 322k tokens because
resuming the implementation agent re-paid its ~300k transcript before any work
began. These rules keep a run inside its window without lowering the quality bar.

1. Fresh-by-default for bounded fixes. A bounded fix or follow-up dispatches a
   NEW agent carrying a tight prompt, the finding text, and artifact refs.
   Resume an existing agent only when its accumulated context is itself the
   input: the orchestrator across Plans, or an interrupted unit with
   substantial un-persisted work in its own transcript. Never resume a
   heavy-transcript agent for light work.
2. Story context brief. At Act, when a story's operative contract or rulings
   changed that cycle, the harness refreshes a compact brief at
   `runs/<run-id>/artifacts/story-brief-<story-id>.json`: operative artifact
   refs, pinned strings and rulings, open conditions, and merge-bar state, held
   to a few thousand tokens. Dispatched units read the brief first and open a
   full artifact only for a section the brief cites. The brief is a projection
   like run-state: derived, regenerable, never the source of truth. Its
   contract is `schemas/story-brief-v1.json`.
3. Scoped verification inside units. A unit runs the named test files its work
   touches with filtered output, and single-workspace typechecks when the diff
   is contained. Whole-suite, all-workspace proof belongs to CI at the publish
   step, not to every unit locally.
4. Effort and model tiering. Mechanical units (seed folds, doc renders, chore
   commits, artifact transcription) dispatch at reduced effort on a smaller
   model. Full effort is reserved for design, implementation, adversarial
   review, and vertical sign-off, where the depth has repeatedly paid for
   itself. The dispatch-tier table below is the operative assignment.
5. Recovery from a session-limit death. Resume the dead agent in place only if
   it held substantial un-persisted progress. Otherwise re-dispatch fresh under
   rule 1. When limits recur within a run, serialize the heavy units across
   ticks rather than stacking them in one parallel batch, and let the run span
   windows instead of forcing it through one.
6. Artifact diet. A producing agent writes what downstream consumers need and
   links the rest by reference. Folded-in history belongs to the archived prior
   version, not the operative artifact. An operative artifact that has grown
   past roughly 30k tokens is a smell the producing agent should flag.

### Dispatch tiers

A skill carries no model of its own. It runs at the tier of whatever invokes
it, so a skill the harness opens inline runs at the main-session model, the most
expensive tier. Assign every unit to a tier before dispatch. The Agent tool
takes a `model` override per dispatch, so a mechanical unit goes to haiku even
when the skill it uses is one an opus-pinned agent normally runs. A mechanical
unit is fresh every time under rule 1 and never inherits a transcript.

| Tier | Runs as | Units |
|------|---------|-------|
| Deterministic | Bash, no model | `schemas/validate.py`, `rebuild-projection.py`, `derive-ready-queue.py`, `pin-learnings.py`, `linear-sync.ts` |
| Mechanical | haiku subagent, fresh each time | spgr-version-artifact, spgr-archive-artifact, spgr-render-doc, story-brief refresh, spgr-write-bug-report from a captured failure, spgr-create-pr from a finished branch, chore commits, artifact transcription |
| Pinned agent | the agent's own `model` | every domain-agent unit at full effort: design, implementation, adversarial review, vertical sign-off |
| Inline main session | the session model, kept minimal | orchestrator dispatch, the Check comparison of expected versus actual, the verdict and transition, spgr-notify-human, run-state writes |

## Pre-build vertical consultation

A story whose scope touches UI error or retry paths, cascade or foreign-key
delete paths, or pagination runs its vertical consultations before the build
unit is dispatched, and folds their conditions into the acceptance criteria and
the developer handoff. The orchestrator routes the consultation units in the
batch ahead of the build unit through spgr-tag-vertical-agent: Accessibility
for focus management on error and retry paths, Performance and Multi-tenancy
for delete and cascade paths, API Design and Performance for pagination. The
build unit does not dispatch until the handoff carries the folded conditions.

The evidence behind the rule: in a test-bed run, seven build ticks gated at
their first Check on late Critical or High findings in exactly these classes
(WCAG 2.4.3 focus loss on error paths, unindexed foreign-key and cascade joins,
unbounded embeds and keyset-pagination correctness), each burning a bounded
retry after the code was written. The one story that ran its consultations
pre-build and folded the conditions into its acceptance criteria came back
APPROVE and PASS with zero retries on those classes. The rule was promoted from
a run retrospective through a human gate, per the self-improvement rules below.

## Human gates

Pause only at the five enumerated checkpoint types: architecture-options
-selection, architecture-confirmation or prd-approval, design-direction
-selection, pr-merge, and security-compliance-flag, plus scope-change. Inventing
an implicit sixth gate violates minimal-human-in-the-loop. At a gate the harness
writes the hil-checkpoint with pipeline_status paused, fires spgr-notify-human,
records the pending batch in the cycle artifact, and terminates.

### pr-merge gate: publish before pausing

The pr-merge gate is reached by remote pull request, never a local-only branch.
Before pausing at a pr-merge checkpoint the harness MUST, once all automated
sign-offs pass (Code Reviewer APPROVE with no open P0 or P1, and every triggered
vertical gate signed off): commit the change on its story branch, push the branch
to origin, and open a pull request via spgr-create-pr against the protected base.
Only then does it write the pr-merge hil-checkpoint (pipeline_status paused,
carrying the PR URL in the checkpoint) and fire spgr-notify-human. The run stays
paused until a human merges the PR. On the next entry the harness reads the merge
as the checkpoint response, stamps it resumed, and continues from the pending
batch. The harness pushes and opens the PR but never merges it and never bypasses
protection, because the human merge is the gate. This is the default for every
story PR. A local-only, unpushed branch is used only when a human explicitly
requests it for a specific change.

Verify CI green before pausing. After opening or updating the PR, the harness
MUST wait for the remote CI checks on the PR head to complete and confirm every
required check passes before it writes the paused pr-merge checkpoint. A green
local suite is NOT sufficient, because CI runs the live-DB, integration, and any
other jobs the local Check necessarily skips (for example DB-gated D-suites that
skip without a live Postgres), and those jobs are the real gate on that work. If
any required check fails, the harness treats it as a Check failure on this cycle:
diagnose the failure from the CI logs, decide whether it is a product defect or a
test-construction defect, route the fix as a bounded retry to the owning agent
(the same two-retry bound applies, then escalate), push, and re-verify CI. Only a
fully green required-check set permits the pause. The harness never pauses at a
pr-merge checkpoint, nor reports the story as ready to merge, while a required
check is failing or still pending. Non-required or advisory checks that fail are
recorded in the checkpoint rather than blocking, and the harness says so
explicitly instead of implying all of CI is green.

## Escalations

An escalation is a first-class artifact. The harness feeds every open escalation
into the Plan input each tick, so resolving one is a routing decision like any
other, never handled out of band. Route by the orchestrator's rules: ambiguity to
the upstream agent, technical conflict to the Architect, policy or compliance or
security to the human plus the specialist, an unresolvable block to the human. A
constraint conflict with approved architecture routes to escalation, never an
auto-fix that edits an ADR. See the orchestrator agent for the full routing map.

## Self-improvement: advisory learnings

At run end the harness writes a run-retrospective artifact. Future runs may
consult it, under three rules that prevent silent drift. See ADR-004.
- Advisory, never dispositive. A Plan step may cite a learning as proposed
  rationale in the cycle's decision log, but the decision still derives from
  current artifacts plus pinned config.
- Pinned per run. Freeze the learnings set by hash at run start and record it in
  run-state.learnings_pinned, so a re-run with the same pinned set is reproducible.
- Human-promoted rules. A learning that would change a rule (a WIP limit, the gate
  set, a routing policy) carries requires_human_promotion true and is applied only
  through a human gate, never by the loop.

## Linear board projection

Optional. When `runs/_linear/config.json` exists with `backlog_provider` set to
`linear`, the human-facing backlog and kanban is a Linear board, and the harness
maintains it as a second projection of run state alongside run-state.json. The
typed artifacts stay the source of truth. Linear is regenerable from them at
any time.

Setup, once per project: copy `assets/linear-config.template.json` (relative to
the spgr-run-harness skill) to `runs/_linear/config.json`, fill in the team,
project, state, and label ids from the workspace, set `LINEAR_API_KEY` in the
environment or the project's root `.env` (a personal API key, never committed),
and run `npx tsx scripts/linear-sync.ts ensure-labels` to create the `agent:*`
labels and record their ids. The script needs Node and runs through `npx tsx`.
For interactive triage a project may also register the Linear MCP server
(`https://mcp.linear.app/mcp`) in its `.mcp.json`. The harness does not use it.

- All Linear I/O goes through `scripts/linear-sync.ts`. Agents never call the
  Linear API directly, and the harness never treats Linear as the database.
- The Act step, after `rebuild-projection.py`, runs
  `npx tsx scripts/linear-sync.ts sync-run <run-dir>`: unpublished confirmed
  stories are created as issues, and each story present on the wip_board is
  transitioned to the mapped Linear state (config `wip_board_state_map`). A
  story absent from the board never demotes its issue, so a human dragging
  cards is not fought and an idle board changes nothing.
- A sync failure is recorded in the cycle decision log and never blocks the
  Act transition. A projection must not gate the pipeline it projects.
- At a pr-merge gate the harness attaches the PR to the story's issue
  (`link-pr <story-id> <pr-url>`) after opening it. The review column carries
  the issue to In Review. The merge, read on resume, moves the story to the
  done column and the issue to Done.
- So that Done accumulates on the board, a story that reaches done stays in
  the wip_board done column permanently. Done entries do not count against
  any WIP limit.
- An issue is moved to Done only when its work is complete and fully validated
  by the run (config `close_policy`). Work that needs human manual testing stays
  open with a comment saying what the human must verify.
- Intake runs the other way through `fetch-ready`: an issue carrying the
  `agent:ready` label, or assigned to the configured intake assignee, is the
  queue a human hands to the loop. A human edit to a story's scope made in
  Linear is surfaced by the intake side as a scope-change gate. The sync never
  reads Linear content back into artifacts silently.

## Determinism scripts

These scripts keep the deterministic work out of the model.
- `scripts/derive-ready-queue.py <run-dir>` prints the readiness snapshot. Pure
  function of the store. Makes no routing decision.
- `scripts/rebuild-projection.py <run-dir> [--validate]` rebuilds run-state.json
  by replaying the cycle log. Run it after every Act, and any time the projection
  is lost or suspected stale.
- `scripts/pin-learnings.py <retrospective.json> ...` freezes the advisory
  learnings set by content hash at run start. Pure function of the inputs. Makes
  no judgment about which learnings apply.
- `scripts/linear-sync.ts <command>` is the only channel for Linear I/O when the
  Linear board projection is on. It pushes repo state to Linear or reads Linear
  intake, and never treats Linear as the database.

The story brief (`artifacts/story-brief-<story-id>.json`) is a projection in the
same sense as run-state.json: derived from the operative artifacts, regenerable,
never the source of truth.

The store-reading scripts scan the active run-store subdirectories (artifacts,
escalations, checkpoints, consultations) and never archive, so a checkpoint or
escalation counts whether it sits in artifacts or in its own subdir, and a
superseded artifact cannot resurrect a gate or a block.

## Increment status

The current build runs the sequential spine with the full Check: single-unit Plan
to Do to Check (validate plus the read-only audit fan-out and the expected-versus
-actual comparison) to Act, with the fix-and-retry branch on a fail verdict,
terminate at a gate, rehydrate on entry. WIP-bounded parallel Do is live: the
orchestrator returns a ready-batch and the harness dispatches independent
file-disjoint units in one turn behind the fork-join barrier. The
self-improvement loop is live: learnings are pinned by hash at run start, cited
as advisory proposed rationale in Plan, and written to a retrospective at
completion, with rule changes gated on human promotion. The run-state wip_board
is maintained by the harness after each barrier, and rebuild-projection carries
it forward when replaying the log. The token-economy rules, the dispatch tiers,
the per-story brief, and the pre-build consultation rule are live. The Linear
board projection is opt-in per project.
