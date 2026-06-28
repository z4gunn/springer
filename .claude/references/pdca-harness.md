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
- Human gates
- Escalations
- Self-improvement: advisory learnings
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

## Human gates

Pause only at the five enumerated checkpoint types: architecture-options
-selection, architecture-confirmation or prd-approval, design-direction
-selection, pr-merge, and security-compliance-flag, plus scope-change. Inventing
an implicit sixth gate violates minimal-human-in-the-loop. At a gate the harness
writes the hil-checkpoint with pipeline_status paused, fires spgr-notify-human,
records the pending batch in the cycle artifact, and terminates.

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

## Determinism scripts

Two scripts keep the deterministic work out of the model.
- `scripts/derive-ready-queue.py <run-dir>` prints the readiness snapshot. Pure
  function of the store. Makes no routing decision.
- `scripts/rebuild-projection.py <run-dir> [--validate]` rebuilds run-state.json
  by replaying the cycle log. Run it after every Act, and any time the projection
  is lost or suspected stale.

## Increment status

The current build runs the sequential spine with the full Check: single-unit Plan
to Do to Check (validate plus the read-only audit fan-out and the expected-versus
-actual comparison) to Act, with the fix-and-retry branch on a fail verdict,
terminate at a gate, rehydrate on entry. WIP-bounded parallel Do and the
self-improvement loop are wired in later increments. The run-state wip_board is
reconstructed structurally once parallel Do lands. Until then rebuild-projection
carries the board forward from the prior projection.
