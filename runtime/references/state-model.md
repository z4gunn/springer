# Springer Harness State Model

Date: 2026-11-01
Status: reference for the harness daemon, with its schemas under runtime/schemas/.

## Contents

- Scope
- Principles carried over
- What changes
- Entities
- Unit lifecycle
- Unit directory
- Session lifecycle
- Gate requests
- Events
- Gate record (hil-checkpoint-v2)
- Run projection (run-state-v2)
- Worktree claim and lock
- Usage window
- Scheduler tick
- Crash recovery
- Schemas to add
- Validation and evals

## Scope

This reference defines the durable state the Springer harness daemon reads and writes: the entities, their lifecycles, where each lives on disk, who may write it, how the daemon recovers after a crash, and what changes relative to the current in-session harness. It extends the existing model (the append-only pdca-cycle log as the source of truth, run-state as a regenerable projection, hil-checkpoint and escalation as artifacts, events.jsonl as the dispatch ledger) rather than replacing it. Everything that already validates keeps validating.

## Principles carried over

1. The cycle log is the source of truth. Every durable change is a cycle record or an event. run-state.json and the harness SQLite index are projections and are rebuilt from the log at any time.
2. One writer per run. The daemon holds the run lock and is the only process that appends to the log. Anything else that wants to change a run goes through the daemon API.
3. State lives in files, addressed by path, readable by a cold process. A fresh daemon reconstructs every run from disk with no memory of the previous process.
4. Completion is a property of artifacts, receipts, and merges, never of a transcript.

## What changes

1. The unit becomes a first-class entity with an id, a directory, a lifecycle, and its own records. Today a unit is a work_item nested in a cycle record with no identity of its own.
2. Cycles may overlap. The current rule, no new cycle is planned while any prior dispatch lacks a completion, exists because the main session cannot know which files an in-flight unit touches. The daemon can, from the unit spec, so it plans a new cycle whenever the ready queue is non-empty and WIP and usage-window room exist, and checks disjointness against in-flight units. A cycle still closes only when every unit it routed is terminal. This is the one rule change to pdca-harness.md, and it displaced the barrier paragraph.
3. Gates carry a risk level (L0 to L3) and the list of unit ids they hold. hil-checkpoint-v2 adds level and narrows holds to unit ids. An L2 gate holds the merge of the units it names and nothing else.
4. Sessions are tracked as their own records, because a unit may run across more than one session (a handoff at the context threshold) and a session may die without returning.
5. The lock is daemon-level with a heartbeat, in the same file and format claim-run.py uses, so the in-session shim and any stray Claude Code session see the lock and refuse to write.

## Entities

| Entity | Id | Lives at | Written by |
|--------|----|----------|------------|
| Project | slug | ~/.springer/projects.json | onboard, register |
| Run | run_id | runs/<run_id>/ in the project | daemon |
| Brief | brief_version | docs/brief.md, projected to runs/<run_id>/run-brief.json | human, daemon projection |
| Cycle | CYCLE-nnnn | runs/<run_id>/artifacts/ as pdca-cycle artifacts, as today | daemon at Plan and at Act |
| Unit | U-nnnn | runs/<run_id>/units/U-nnnn/ | daemon writes spec and state, the session writes outputs |
| Session | S-nnnn | runs/<run_id>/units/U-nnnn/sessions/S-nnnn/, including gate-request.json when the session needs a person | daemon and the session |
| Gate | G-nnnn | runs/<run_id>/artifacts/ as hil-checkpoint-v2 | daemon, answered through the API |
| Escalation | E-nnnn | runs/<run_id>/artifacts/ as today | daemon |
| Receipt | per gating command | runs/<run_id>/units/U-nnnn/sessions/S-nnnn/check/receipts/ for the commands the harness runs at Check, which are the evidence. A session may write its own while it works | receipt.py, run by the daemon at Check |
| Event | monotonic seq | runs/<run_id>/events.jsonl | daemon and the session hooks |
| Worktree | unit id | ~/.springer/worktrees/<project>/U-nnnn/ | daemon |
| Usage window | provider account | ~/.springer/usage/<provider>.json | daemon |
| Index | none | ~/.springer/index.sqlite | daemon, rebuildable |
| Audit log | op_id | ~/.springer/audit.jsonl, every applied operation, including one with no run | daemon |

## Unit lifecycle

States, in the order a healthy unit passes through them, with the side exits.

| State | Meaning | Enters when | Leaves when |
|-------|---------|-------------|-------------|
| planned | Named in a cycle's routed batch with a spec written | Plan closes | Dependencies, WIP, and window checks run |
| ready | Dispatchable now | Dependencies merged or open as a stackable PR, WIP room in its workstream, usage window has room, no file overlap with an in-flight unit | The scheduler claims it |
| running | A session is alive for it | Worktree allocated, session spawned, dispatch event written | Session exits with a result or a handoff, or is found dead |
| returned | A result, a handoff, or receipts exist on disk | Session exited | Check begins |
| checking | The unit's gating commands run at the branch head, validation, failure classification, review package, risk scoring | Returned | A verdict is reached |
| gated | Its PR is open and a gate decides the merge | Check passed and the unit produced a PR | Auto-merge (L0, L1) or the human answers (L2), in either case only after the Code Reviewer's verdict |
| done | Merged, or the artifact it produced is confirmed | Merge or confirmation recorded | Terminal |
| retry | Check found a defect, one bounded retry is spent | Classify returned defect | A fresh session at the unit's tier, second retry one tier up |
| redispatch | Check found a transient, environment, or context failure, no retry spent | Classify returned one of those, or the session was abandoned | A fresh session, narrower brief on context |
| blocked | An escalation or a missing provisioned input holds it | Classify returned blocked, or a dependency is L3 | The escalation is resolved |
| abandoned | The session died without a return | Heartbeat lost and process gone | Redispatch |
| cancelled | A human cancelled it | API call | Terminal |

Every PR gets a review unit before it can merge. When a unit reaches gated with a PR, the daemon cuts the review package with `review-package.py` and opens a unit for spgr-agent-code-reviewer on the PR head, with `review_of` naming the reviewed unit. The PR waits while that review unit is not terminal. Its result.json carries `verdict` (approve or request_changes), `findings`, and `code_review`, the artifact whose gate-tag dispositions Check verifies. Approve lets the merge go on with the findings attached to the gate. request_changes sends the reviewed unit to retry with the findings in its notes, once. A second request_changes raises the PR to L2, so a person decides. A review unit never integrates or merges anything.

retry, redispatch, and blocked return to ready when their condition clears. A unit that reaches done, cancelled, or exhausts its retries is terminal. A cycle closes when every unit it routed is terminal, and its Act record lists the terminal state of each.

The existing Act transitions (advance, retry, escalate, pause, complete) stay at the cycle level. The unit states are the finer grain under them.

## Unit directory

```
runs/<run_id>/units/U-0412/
  spec.json          the dispatch contract, written once by the daemon
  state.json         current state, timestamps, retry count, session ids, written by the daemon
  retrieved.json     what retrieval supplied to the brief
  sessions/
    S-0001/
      stream.jsonl   the session's stream-json, captured by the daemon
      usage.json     tokens, context percent at exit, cost at list price
      brief.md       the unit's brief plus the output contract, written by the provider at spawn
      return.txt     the session's final text, as today
      result.json    the typed result Check reads: status, outcome, pr, touched_paths, failure_class, detail
      handoff.md     written by the session on a context-threshold exit
      gate-request.json  written by the session when it needs a person, see Gate requests
  receipts/          as today
  review/            the review package (on a review unit) and each review verdict JSON (on the reviewed unit)
  risk.json          baseline level from the rules file, raised by reviewers, never lowered
```

spec.json holds: unit_id, cycle_id, agent, role prompt reference, model tier, brief (the compact context brief), input artifact refs, expected outcome, workstream, declared paths (the files the unit may touch, used for disjointness), allowlist, mcp config reference, budget (tokens and wall clock), risk baseline, dependencies (unit ids), the executable check, and on a review unit review_of and review_session (the reviewed unit and the session whose PR head it grades).

state.json holds: state, entered_at, history (state, at, reason), retries_spent, sessions (ids), pr (number, branch, base), merge (sha, at), cancelled_by, and reviews (the review unit ids opened for its PR).

## Session lifecycle

| State | Enters when |
|-------|-------------|
| spawned | The provider started the process, pid and provider session id recorded |
| streaming | First stream event received |
| handoff | The session wrote handoff.md and exited cleanly at the context threshold |
| exited | The process ended with a code and a return |
| killed | The daemon ended it (cancel, budget, or shutdown) |
| dead | The process is gone with no exit event, found at heartbeat or at daemon start |

A session that needs a person writes gate-request.json and returns. See Gate requests.

A unit in running has exactly one session not in a terminal state. A handoff spawns the next session for the same unit with handoff.md in its brief and the unit stays in running. A dead session puts the unit in abandoned.

## Events

events.jsonl keeps its current line format and its existing event names (agent_dispatched, agent_completed, agent_backgrounded, agent_stopped, agent_joined, agent_abandoned, product_check). The daemon adds these, each carrying run_id, unit_id, session_id where applicable, and a monotonic seq.

| Event | Payload |
|-------|---------|
| unit_state | from, to, reason |
| session_started | provider, pid, model, tier |
| session_usage | input tokens, output tokens, context percent, cost (periodic, from the stream) |
| session_exited | code, outcome (return, handoff, killed, dead) |
| worktree_claimed, worktree_released | path, branch |
| worktree_kept | path, reason git refused the removal |
| gate_opened | gate_id, level, holds |
| gate_answered | gate_id, response, by |
| merge | unit_id, pr, sha |
| merge_failed | unit_id, pr, detail. A conflict sends the unit back to its builder, any other refusal blocks it for a person |
| restacked, restack_failed | unit_id, pr, and onto or detail. After a squash merge, a stacked branch keeps only its own commits |
| tick_failed | detail, written once per distinct error so a stalled run is visible in its ledger |
| retrieval | unit_id, record ids supplied |
| window_sample | provider, used fraction, resets at |
| operation_applied | op_id, type, actor, args. A secret value is never in args |

A human intervention is recorded as operation_applied rather than as a cycle record, because a cycle record requires a plan, do, check, and act. Lines written by the session hooks carry no seq, so the API orders a stream by a cursor over the ledger and not by seq. The event ledger is what the TUI run screen and the dashboard read. The projection and the index are rebuilt from the cycle log plus the event ledger.

## Gate record (hil-checkpoint-v2)

Changes from v1: checkpoint_type gains discovery-go-no-go, structure-confirmation, scope-review, taste-review, production-release, provisioning-required, and routine-decision, level (L0, L1, L2, L3) is added, holds narrows from phase names and ids to the unit ids whose merge or start waits and becomes required, options stay as they are and are ordered recommended first, digest (true when the gate is informational and closes on view) is added, channel_refs (where it was sent) is added, response (option chosen, free text, rule change, by, at) is added. A gate with holds empty and level L1 is a digest entry, not a pause, so a digest gate records pipeline_status resumed.

## Gate requests

This section is used to define how a headless session asks for a person. A session has no question tool and holds no API token, so it cannot open a gate or reach a channel. It can only leave a request, and the daemon decides what the request becomes.

The session writes gate-request.json in its own session directory, sets result.json to status pass with detail waiting on a person, and exits. spgr-notify-human writes the file in this mode. The file is one JSON object.

| Field | Required | Content |
|-------|----------|---------|
| checkpoint_type | Yes | A hil-checkpoint-v2 checkpoint_type (e.g. scope-change, security-compliance-flag) |
| decision_prompt | Yes | The question, in one or two sentences |
| options | Yes | One or more `{option, consequence, recommended_because}`, recommended first. recommended_because is optional |
| decisions | No | `{decision_id, kind, prompt}` items, kind being question, prd-approval, architecture-options-selection, design-direction-selection, or default-review |
| artifact_ref | No | The artifact the person should read, or none |
| unlock_paths | No | `{path, reason}` items naming protected config files the work must change. The gate gets an `unlock` option, and picking it writes each path with its reason to runs/_config-unlock.json |

Check reads gate-request.json before result.json, so a request is never treated as a pass. A valid request opens a gate at L3 holding the requesting unit, and the unit moves to blocked. The gate's context records `gate_request: U-nnnn/S-nnnn`, and Check opens no second gate for the same key, so a Check repeated after a crash asks once. A request the schema would refuse (an unknown checkpoint_type, no prompt, no options, an option without a consequence) is a defect in the session: Check opens no gate and sends the unit back with the reason, so the question is never lost. An option written as `{label}` is read as `{option}`. An unlock_paths entry with no path or no reason is refused the same way.

When the person answers, the unit returns to ready and the answer is appended to its redispatch notes as one line naming the prompt, the option chosen, any free text, and each decision's answer. The next session's brief carries that line, so the session that continues the work reads the decision rather than asking again.

## Run projection (run-state-v2)

Keeps every v1 field, changes open_gates from checkpoint ids to objects (id, level, holds, age), drops the v1 cap on the wip_board stages because the scheduler enforces WIP and an L2 hold never blocks the agent, and adds: paused, waiting_on, last_tool_call on each in_flight row, units (count by state), in_flight (unit id, session id, agent, model, started at, context percent, cost), worktrees (unit id, path), mvp_line (feature ids above and below), deferred (feature ids), window (provider, used fraction, resets at), generated_from_seq (the last event seq reflected). regenerable stays true.

## Worktree claim and lock

The daemon allocates ~/.springer/worktrees/<project>/<unit_id> with git worktree add on the unit's branch, cut from the base the spec names (main, or the open PR branch of a dependency for a stacked unit). The claim is recorded as an event and in the unit state. The run store is never inside a worktree. A session writes artifacts to the project's runs/<run_id>/ by the absolute path in its brief, as today.

A worktree is released at Act after the PR is open, with git worktree remove. A removal git refuses is logged and left for the human, never forced. A unit in retry or redispatch reuses its worktree when the branch is intact and rebuilds it otherwise.

Disjointness: two units may be in flight at once only when their declared paths do not overlap and they are in different workstreams or the WIP limit allows both. The scheduler computes this from spec.json, which is what lets cycles overlap.

The run lock is runs/<run_id>/.lock in claim-run.py's format. The daemon writes session_id as daemon:<host>:<pid> and refreshes it at every scheduler tick. The in-session shim and derive-ready-queue.py keep treating a live lock held by another id as blocked, so a Claude Code session opened in the project cannot write to a run the daemon owns. The stale threshold stays thirty minutes.

## Usage window

Per provider account, ~/.springer/usage/<provider>.json holds the current window's start and reset time, the used fraction from the provider's usage signal, the daemon's own token count for the window as a cross-check, and the dispatch rate the scheduler derived. The scheduler reads it before claiming a ready unit, lowers concurrency as the window fills, and parks the scheduler until the reset when the window is exhausted. Parked is a daemon state, not a run state, and every affected run shows waiting on usage window in the TUI. Window samples are also written to the event ledger of any run with in-flight units so the retrospective can see them.

## Scheduler tick

1. Refresh the run lock.
2. Read the usage window. If exhausted, park and return.
3. Reconcile sessions: for each unit in running, check the session's liveness. A dead session moves the unit to abandoned and then to redispatch.
4. Join returns: for each session that exited, move its unit to returned and queue Check.
5. Run Check for each returned unit: validate artifacts, read receipts, classify any failure, build the review package, run risk scoring, dispatch the verticals the diff touches, collect verdicts. Move the unit to gated, retry, redispatch, blocked, or done.
6. Resolve gates: auto-merge L0 and L1 units that are gated with green checks, open L2 gates and notify, close cycles whose units are all terminal and write their Act record.
7. Derive the ready queue from planned, retry, redispatch, and blocked-now-resolved units: dependencies, WIP, disjointness, window room.
8. If the ready queue is empty and no unit is in flight, ask the orchestrator agent for the next batch (Plan) and write the cycle record. Otherwise, if WIP and window room remain, Plan may also run to add a batch, with disjointness checked against in-flight units.
9. Claim and dispatch ready units up to the concurrency the window allows: allocate the worktree, assemble the brief with retrieval, spawn the session, write the events.
10. Refresh the projection and the index from the ledger.

Every step is idempotent against the ledger, so a tick interrupted anywhere is safe to run again.

## Crash recovery

On daemon start, for every registered project and every run under it that is not complete:

1. Rebuild run-state from the cycle log and the event ledger. The last event seq is the recovery point.
2. For every unit the projection shows in running: the daemon's child processes died with it, so every such session is dead. Write session_exited with outcome dead, move the unit to abandoned, then to redispatch. No retry is spent. If the session left handoff.md, the redispatch brief carries it.
3. For every unit in checking: Check is idempotent and is run again from the files on disk.
4. For every unit in gated: re-read the PR state from the source host. A merged PR moves the unit to done, an open PR stays gated, a closed unmerged PR moves to blocked with an escalation.
5. For every worktree directory under ~/.springer/worktrees/<project>/ with no unit in running or retry: remove it if git allows, otherwise log it.
6. Take over the run lock if it is stale or held by a previous daemon id. A live lock held by a non-daemon id (a Claude Code session) leaves the run alone and the TUI shows it as externally held.
7. Resume the scheduler tick.

Nothing in recovery asks a human. Everything it decides is written as events so the retrospective can see a crash happened.

## Schemas to add

| Schema | Purpose |
|--------|---------|
| unit-spec-v1.json | spec.json, the dispatch contract |
| unit-state-v1.json | state.json |
| session-v1.json | usage.json plus the session record fields |
| events-v1.json | the event line shapes, one definition per event name, including the existing names |
| hil-checkpoint-v2.json | v1 plus level, holds, options, digest, channel_refs, response |
| run-state-v2.json | v1 plus the fields listed above |
| usage-window-v1.json | the per-provider window file |

pdca-cycle-v1 stays v1. The work_item definition gains an optional unit_id so a cycle can reference the units it routed, and a cycle written by the daemon always sets it. A dispatch status gains pending, because the daemon writes the cycle at Plan, before anything has run.

## Validation and evals

validate.py --self-check picks up the new schemas from the registry directory, and tests/test_state_schemas.py proves each one accepts a valid record and rejects an invalid one. The harness test suite, against the mock provider, covers: every unit transition in the table, overlapping cycles with a disjointness conflict, a handoff across two sessions, a dead session at reconcile, a daemon restart with units in each state, an exhausted window parking and resuming, and a stale lock takeover. One eval scenario covers the shim: a Claude Code session in a project with a daemon-held run refuses to write and says why.
