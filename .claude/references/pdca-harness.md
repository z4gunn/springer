# PDCA harness reference

Detail for the spgr-run-harness skill: the per-tick state machine, the
rehydration algorithm, the parallel barrier and scheduling rules, gate and
escalation handling, the advisory-learnings mechanism, and the determinism
scripts. The skill body holds the loop. This file holds the rules behind it.

## Contents
- Roles and the single delegation hop
- Run profiles
- The PDCA tick
- Mechanical Check
- Verdict and transition table
- Rehydration: start equals resume
- Parallel Do: the barrier and disjoint scheduling
- Token economy and dispatch efficiency
- Dispatch contract
- Main-session budget
- Fold-in policy
- Docs rendering policy
- Pre-build vertical consultation
- Human gates
- Autonomy levels
- Decision classes and the defaults ledger
- Intake question sweep
- Direction review
- Gates hold only dependent work
- Gate batching and auto-merge
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

## Run profiles

A run declares a profile when it opens, on a `profile:` line in the problem
statement and in `runs/<run-id>/run-brief.json`. The profile scales the
lifecycle to the product. The reference case is a one-page brochure site with a
written spec and a working prototype in hand that ran the full SaaS lifecycle:
29 stories, 55 criteria, seven ADRs, 32 fold-ins, nine human gates, and thirty
hours before the first visible content. Nothing in the harness said "small".

| Profile | Fits | Phases routed | Stories | Architecture | Criteria | PR unit |
|---------|------|---------------|---------|--------------|----------|---------|
| brochure | static site, landing page, docs site, no backend | requirements, design, development | at most 10, one per visible section or behavior | one architecture note (stack, file layout, constraints), no ADR set | one sentence plus one check command each | one PR per page |
| small | one service or app, one or two integrations, no tenancy or billing | requirements, architecture, design, development | at most 25 | ADRs only for decisions a later change would regret | statement plus check | one PR per co-scheduled batch |
| saas | multi-tenant product with auth, billing, or an API surface | the full lifecycle | as scoped by the PM | full ADR set | full Given/When/Then sets | per story or batch |
| mobile | store-distributed app | the full lifecycle plus the App Store vertical | as scoped | full ADR set | full sets | per story or batch |

Rules the profile carries:
- A phase outside the profile's set is not routed. Discovery runs on brochure
  or small only when the human asks for it. Compliance scope on brochure is one
  line in the requirements unit, not a consultation.
- NFR consultations on brochure and small fold into the PM unit as a checklist.
  A vertical is dispatched only when a later diff touches its surface.
- The definition of done on brochure is the CI check, which includes the SEO
  baseline from spgr-check-seo-baseline run strict on every built page. No DoD
  artifact is written.
- The orchestrator reads the profile from the readiness snapshot and holds any
  unit outside the profile's phase set. Changing the profile mid-run is a
  scope-change gate.
- The PM agent enforces the story and criteria caps at authoring time. A
  backlog over the cap is merged or cut before the prd-approval gate.
- Content sources are complete before the build. On brochure and small the
  requirements unit lists every fact the spec cites (figures, dates, names,
  URLs, tag lists) with its in-repo source under `docs/inputs/`. A fact that
  lives only outside the repository is an intake question put to the human at
  the first gate, never a discovery a build unit makes. Under supervised the
  orchestrator holds the build unit while any source is missing. Under standard
  and autopilot an unanswered fact is built as a visible placeholder under the
  defaults ledger, and the placeholder blocks the merge. See Decision classes
  and the defaults ledger. In the reference
  run the only findings left open after the page shipped were a date range, a
  LinkedIn URL, and a tag list, each referenced by the spec and held only in a
  private vault.

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

## Mechanical Check

Check is mechanical first. It runs `schemas/validate.py` on every produced
artifact, runs the project check script or the scoped test files the unit
named, and reads CI on the PR head. The main session never re-runs an agent's
verification by hand, never re-derives a finding an agent reported, and never
opens an artifact to re-read a claim the check script already covers. A claim
that no script or CI job can check is recorded as unverified. It is not
verified by the harness reading files. When a code-review artifact carries a
`cannot_verify` list, Check runs each named command and folds the result into
the verdict, so a check the reviewer could not run from the package is
answered by execution rather than by the implementer's word. The reviewer's
`declined_to_judge` list is carried into the cycle record unchanged.

A model-based audit is dispatched only when the diff touches a vertical's
declared surface: UI markup or styles for Accessibility, dependencies, headers,
or data handling for Security, a schema or a query for Performance. A change
that touches only `runs/`, `docs/`, or the run's own ledgers is never sent to
the Code Reviewer and never audited. Its check is validate plus a diff summary.
On brochure and small the Code Reviewer carries the Accessibility checklist
in its own pass rather than a separate audit being dispatched, because the two
overlapped on the same defects in the reference run. Accessibility is
dispatched separately only for a re-check by execution after a fix.

Review is bounded to one review pass and one re-review. A second
REQUEST_CHANGES routes the open findings to the human at the pr-merge gate as a
list. The bound exists because one docs-regeneration chore in the reference
case received three REQUEST_CHANGES passes, 45 findings, and five hours. The
bound controls the cost of a review. The pre-report gate in the Code Reviewer
agent controls its precision: a finding names its line, its failing input, and
the rule it violates, a blocking finding carries evidence the code-review
schema requires, and a known class of false findings is never raised. Under
auto-merge the reviewer's verdict is the last gate, so both bounds matter.

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
2. If a gate in `answered_gates` has a response, stamp that hil-checkpoint
   resumed, consume the response, and route its held batch.
3. If the snapshot is blocked by a gate holding all work, exit immediately
   doing no work. A gate that holds only some work does not stop the loop.
   See Gates hold only dependent work.
4. Otherwise resume the loop at Plan from the latest cycle's next phase. The
   loop exits waiting on a human only when the orchestrator returns an empty
   batch while a gate is open.

The held batch lives in the checkpoint's `held_batch` field, or in the paused
pdca-cycle artifact for a gate that holds all work, never in checkpoint prose,
so resume is deterministic.

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

Co-scheduled build units run in separate git worktrees. File-disjoint is not
checkout-disjoint: two units in one working tree that each run `git checkout
-b` on their own branch switch the tree out from under each other, and one
unit's commit carries the other's half-written files. spgr-create-branch in
worktree mode gives each unit `.worktrees/<branch>/`, a linked worktree on its
own branch cut from the protected base, and the dispatch prompt names that
path as the unit's working directory. Every command in the unit runs there.
The run store stays in the main worktree. A unit writes its artifacts to the
main worktree's `runs/<run-id>/` by the absolute path the prompt carries,
never to the copy under its own worktree, so there is still one store and one
writer. A linked worktree carries no ignored files (`node_modules`, `.venv`,
build output), so the unit installs dependencies the way CI does and runs its
scoped baseline tests before it writes code. At Act, after spgr-create-pr has
opened the unit's PR, the harness removes the worktree with `git worktree
remove .worktrees/<branch>` and keeps the branch. A removal git refuses is
left in place and reported, never forced. A batch with a single build unit
may still work in the main checkout.

A cycle is not closed while a unit it dispatched is still running, and a new
cycle is not planned while any dispatch from a prior cycle lacks a completion.
A background agent outlives the turn that dispatched it, so the turn boundary
alone does not enforce the barrier. `derive-ready-queue.py` reads
`events.jsonl`, reports `unjoined_dispatches`, and sets blocked while any exist.
The check keys on unmatched dispatch ids, never on elapsed time. When a dispatch
is known dead (a session-limit death, a killed agent), the harness appends an
`agent_abandoned` event carrying the same tool_use_id to release it. The
reference case planned a cycle against a tree that a fifty-minute unit from the
prior cycle was still writing, then blamed a different agent for the writes.

The run is single-writer at the session level too. On entry the harness
claims the run with `claim-run.py <run-dir> claim <session-id>` and re-claims
at every tick as a heartbeat, and `derive-ready-queue.py --session <id>` sets
blocked while another session's live lock exists. On exit the harness releases
it. A lock not refreshed for thirty minutes is stale and is taken over. In the
reference run a second session branched and committed from under a live loop
session, and nothing detected it.

Dispatch in the foreground. Several Agent calls in one turn already run in
parallel, and a foreground call returns when its agent finishes, so the hook's
completion event is a real join. A background dispatch (`run_in_background`)
returns at once, the hook logs it as `agent_backgrounded`, and it stays
un-joined until the harness appends `agent_joined` with its tool_use_id when
the task notification arrives. The reference run dispatched every unit in the
background, so every dispatch showed a completion two seconds later and the
log could not tell a finished agent from a running one.

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
   version, not the operative artifact. An operative artifact is capped at
   roughly 30k tokens. Fixtures, coverage gates, and check design live in the
   test suite and the check script, not in the criteria artifact. A producing
   agent that would exceed the cap splits the artifact or links by reference.
   The reference case let a criteria artifact grow to 45k tokens over seven
   versions, three criteria of which described a checker in more detail than
   the checker's own source.
7. Run brief. `runs/<run-id>/run-brief.json` holds the profile, the run flags,
   the pinned human rulings as one line each, and the operative artifact list
   with versions, held to a few thousand tokens. The harness refreshes it at
   Act whenever a ruling lands or an artifact is versioned. Rehydration reads
   the run brief and the story brief, not the corpus. Its contract is
   `schemas/run-brief-v1.json`.

### Dispatch tiers

A skill carries no model of its own. It runs at the tier of whatever invokes
it, so a skill the harness opens inline runs at the main-session model, the most
expensive tier. Assign every unit to a tier before dispatch. The Agent tool
takes a `model` override per dispatch, so a mechanical unit goes to haiku even
when the skill it uses is one an opus-pinned agent normally runs. A mechanical
unit is fresh every time under rule 1 and never inherits a transcript.

| Tier | Runs as | Units |
|------|---------|-------|
| Deterministic | Bash, no model | `schemas/validate.py`, `rebuild-projection.py`, `derive-ready-queue.py`, `pin-learnings.py`, `linear-sync.ts`, `capture-comps.py` (the comp and PR screenshot matrix plus the slop detector), `review-package.py`, `floor_guard.py` (the diff-scoped scan for a lowered quality bar) |
| Mechanical | haiku subagent, fresh each time | spgr-version-artifact, spgr-archive-artifact, spgr-render-doc, story-brief refresh, spgr-write-bug-report from a captured failure, spgr-create-pr from a finished branch, chore commits, artifact transcription |
| Pinned agent | the agent's own `model` | every domain-agent unit at full effort: design including the comp critique, implementation, adversarial review, vertical sign-off |
| Inline main session | the session model, kept minimal | orchestrator dispatch, the Check comparison of expected versus actual, the verdict and transition, spgr-notify-human, run-state writes |

## Dispatch contract

Every unit prompt carries the same things, and every unit report answers the
same things. The prompt names the files to read in order, the rulings
that bind, the check command that gates the work, the working directory (the
unit's worktree path, or the main checkout) with the absolute run-store path,
and the report format. The report lists the files written with line counts,
pastes the verification output rather than describing it, quotes verbatim
every obligation it could not satisfy with the reason, lists each default
taken as one defaults-ledger line, and never fills a gap with an unrecorded
assumption. In the reference run this contract produced honest gap lists from
every unit, where the earlier cycles had produced overstated claims the
harness then re-verified by hand. A report that describes a check instead of
pasting it is treated as unverified.

The contract travels in files, not in the prompt and not in the return value,
so neither the task text nor the diff transits the main session.

- The brief. For each routed unit the harness writes
  `runs/<run-id>/dispatch/<cycle-id>/<unit-id>/brief.md`: one line of
  context, the files to read in order (the story brief first), the rulings
  that bind, the interfaces the unit consumes from earlier units and produces
  for later ones with exact names and signatures, the check command, the
  working directory and run-store path, and the report path. The dispatch
  prompt is a few lines that name the brief as the unit's requirements. A
  unit reads its brief, never the whole plan or the whole corpus.
- The report. The unit writes `report.md` beside its brief with the full
  contract above, and returns under fifteen lines: a status, the commits, a
  one-line test summary, and concerns. The status is one of `DONE`,
  `DONE_WITH_CONCERNS`, `BLOCKED`, or `NEEDS_CONTEXT`. The harness reads the
  return, and opens the report only for the section Check needs, which is the
  pasted verification output. A `BLOCKED` or `NEEDS_CONTEXT` return names
  what is missing, and routes as an escalation.
- The review package. Before a review unit the harness runs
  `scripts/review-package.py <base> <head> --out <dir>/review.md`, which
  refuses a head that does not descend from the base and writes the commit
  list, the stat, and the diff with ten lines of context under a header that
  records both SHAs and whether the tree was dirty. The reviewer reads the
  brief, the report, and the package. The main session never reads the diff.
  The reviewer prompt never caps a severity, excludes an area, or says what
  not to flag. Pre-judging a finding is the harness grading the work itself,
  and the reviewer is told to ignore such a sentence and note it.

The `dispatch/` directory is run-store history like the cycle log. The
store-reading scripts do not scan it, and it is never an artifact.

### Bounded fix loop

Review is one pass and one re-review, and a unit gets two bounded retries.
Those counts stay. The loop inside them has a fixed shape.

1. A fix dispatch carries the finding text verbatim, the lines it names, and
   the brief. The first retry goes to a fresh agent at the unit's tier. The
   second retry goes to a fresh agent one tier up (sonnet to opus) with the
   statement that a prior implementer attempted the fix once and the new
   agent owns it now. A heavy-transcript agent is never resumed for a fix.
2. The re-review is scoped. It receives the prior findings and a review
   package cut from the fix commit, verdicts each prior finding `ADDRESSED`
   or `NOT ADDRESSED`, and raises a new finding only for breakage the fix
   diff introduced. It never re-reviews the whole PR.
3. At the bound the harness adjudicates each open finding rather than looping
   again. A P0 or P1 goes to the human at the gate as a list, as before. A P2
   or P3 under standard or autopilot is parked as one defaults-ledger line
   carrying the finding, the ruling, and the cost if the ruling is wrong, and
   is reviewed at the next gate with the other defaults. Under supervised
   every open finding goes to the human.
4. A finding the reviewer could not verify from the package (`cannot verify
   from diff`) is the harness's to resolve by running the named check, never
   the implementer's to argue away and never silently dropped.

## Main-session budget

The main session runs the harness on sonnet by default. It writes run state and
the cycle record, dispatches, and reads script output. The cycle record is
capped at roughly 2k tokens: the batch, the verdicts, the transition, and the
pending batch. A human ruling is recorded as the human's own words plus a
one-line list of the artifacts it changes. The harness never writes a findings
narrative longer than the diff it describes. In the reference case the main
session issued 771 shell commands and 2.26M output tokens on opus, more than
all 71 subagents combined, while the dispatch-tier table said it was kept
minimal.

The budget has a sensor. The `session-usage.py` hook, registered for
PostToolUse and Stop in the instance settings, reads the session transcript
incrementally and writes the main session's context size, cumulative tokens,
and model to `runs/_dashboard/sessions/<session-id>.json`. The dashboard shows
that line next to the subagent figures and prices both from
`assets/model-pricing.json` in the run-harness skill. When the context passes
60 percent of the window the hook injects one advisory telling the harness to
end the loop at the next clean Act. At 80 percent it injects one instruction to
finish the current Act, release the lock, and resume in a fresh session. Each
tier fires once per session. The hook observes and never blocks. Every
dispatch event also records the model the unit ran on, from the per-dispatch
override or the agent's frontmatter, so the cost figures are priced per tier
rather than guessed.

The instance settings installed by `new-project.sh` from
`templates/project-settings.json` carry a permission allowlist for the
commands the harness runs itself (validate, the harness scripts, the project
verification scripts, git add, commit, push, branch, and the gh pr commands)
and a denylist for the destructive git forms. Without it a run stalls at a
permission prompt on every commit, and the page batch in the reference run
stalled three times on its own commit, its CLAUDE.md note, and its hook sync.

## Fold-in policy

A fold-in is a correction to a confirmed artifact found downstream. It is one
line in `runs/<run-id>/pending-foldins.md`: id, target artifact, the change in
one sentence, and the story or gate that consumes it. It is applied by a haiku
unit in the same cycle it opens, or moved to a `deferred` list. A fold-in is
opened only when it changes shipped bytes or a criterion the next build unit
owns.

Not fold-ins: confidence markers, checksums, stale prose in an artifact nothing
reads next, doc fidelity, and any finding about the harness itself. Those are
one batched hygiene pass at a human gate, or skipped. A fold-in never has
another fold-in as its subject. A retraction is one line appended to the
original. In the reference case 30 of 32 fold-ins concerned artifacts, docs, or
the harness, one retracted another, one amended another's remedy, and the
93 KB ledger outgrew everything the site will ever ship.

## Docs rendering policy

`docs/` is a review copy rendered at a human gate for the artifacts that gate
reads, and only then. It is not refreshed on every artifact edit, and its
fidelity is not audited beyond the render skill's own validation step. A human
who wants a current copy of an artifact between gates asks for spgr-render-doc.
A doc that is stale between gates is expected and says so in its header. The
reference case spent one session of six regenerating and policing the mirror.

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

The gate types are fixed by the checkpoint schema: direction-review,
architecture-options-selection, architecture-confirmation, prd-approval,
design-direction-selection, pr-merge, security-compliance-flag, and
scope-change. The run's autonomy level decides which of them fire and which
are combined into one sitting. Inventing a gate outside this set violates
minimal-human-in-the-loop. At a gate the harness writes the hil-checkpoint with
pipeline_status paused, its `holds`, and its `held_batch`, fires
spgr-notify-human, and keeps running any work the gate does not hold.

Every gate that fires also carries the open lines of the defaults ledger as
default-review decisions, so reviewing defaults never costs a sitting of its
own.

## Autonomy levels

A run declares its autonomy in the run brief `flags.autonomy`. The level sets
how many times the human is interrupted. It never changes who decides: the
human always selects the architecture option and the design direction, and
always rules on a security or compliance flag.

| Gate | supervised | standard | autopilot |
|------|------------|----------|-----------|
| intake questions and PRD approval | prd-approval, its own sitting | inside direction-review | inside direction-review |
| architecture option | architecture-options-selection | inside direction-review | inside direction-review |
| architecture confirmation | architecture-confirmation | none, selection confirms | none, selection confirms |
| design direction | design-direction-selection | inside direction-review | inside direction-review |
| pr-merge | per PR unit | per PR unit, or auto-merge when `auto_merge_on_green` | auto-merge on approval plus green CI |
| security-compliance-flag | blocks | blocks | blocks |
| scope-change | blocks | blocks beyond the profile cap or on a profile change, a default within the cap | same as standard |
| deferrable decisions | each ruled in-cycle by the specialist, a human-constraint change escalates | defaults ledger, reviewed at the next gate that fires | defaults ledger, reviewed in the completion notice |

Defaults: standard on brochure and small, supervised on saas and mobile.
autopilot is allowed on brochure and small only, and a brief that names it
elsewhere runs at standard. Changing the level mid-run is a human instruction
recorded as a pinned ruling, not a gate.

Under standard and autopilot, the architecture downstream set is confirmed
without a second sitting when it validates and every routed gate vertical
(Auth, Security, Compliance) signs off. A vertical that cannot sign off fires
the security-compliance-flag gate, which blocks at every level.

## Decision classes and the defaults ledger

Every decision a unit meets is one of two classes.

Blocking, at every level:
- the architecture option and the design direction
- a Critical or High security or compliance finding
- a change to a stated human constraint, to the profile, or to scope beyond
  the profile's story cap
- anything that spends money, creates an external account or credential, or
  takes an irreversible external action (a store submission, a DNS change, a
  data deletion, mail to real users)

Deferrable: every other decision that is reversible within the profile and the
approved architecture, for example copy wording, a heading or section owner,
file layout, test-tier placement, a tooling choice inside the hard rules, and
a content fact the human has not supplied.

Under standard and autopilot a unit meets a deferrable decision by taking the
recommended option, recording it, and continuing. It never raises an
escalation for it and never pauses. The unit report lists each default taken
as one line, and the harness appends it at Act to
`runs/<run-id>/pending-defaults.md`:

```
- DEF-007 | decision | default taken | alternative | cost to reverse | artifact or file | open
```

A default is not an assumption filled in silently. It is named, visible,
recorded, and reviewed. A missing fact is never invented. Its default is a
visible placeholder marked `TODO(DEF-<n>)` in the built output, and a
placeholder blocks auto-merge, so a PR carrying one goes to a human pr-merge
gate that lists it.

At the next gate that fires, spgr-notify-human puts every open line in front
of the human as a numbered default-review list. The human accepts all or
overturns by number. An accepted line is marked accepted. An overturned line
becomes a fold-in carrying the human's words and is applied in the next cycle.
Under autopilot the list goes out in the completion notice instead, and an
overturn is a new run input.

Under supervised a deferrable decision is ruled in-cycle by the routed
specialist, as the Escalations section describes, and no ledger is kept.

## Intake question sweep

The human's facts, assets, and preferences are asked for once, at the first
gate, not discovered one at a time across the run. When the PM unit writes the
PRD it also sweeps the spec, the stories, and the downstream phases for
everything the run will need from the human: content facts, brand assets,
links, domain and deploy target, account access, tone, and any preference a
later unit would otherwise escalate. Each goes into the PRD `open_questions`
with a `recommended_default`, a `blocking` flag set per the decision classes,
and the story or phase that consumes it. The gate renders them as question
decisions, so "accept defaults" answers every non-blocking question in one
line. A blocking question left unanswered holds only its consumer.

In the reference run twenty-three human decisions landed across three days.
Eight of them were facts and small picks (the tagline, a years figure, the
photo, two links, an h2 owner, the script language twice) that a day-one sweep
or a logged default settles without a sitting of its own.

## Direction review

Under standard and autopilot the PRD approval, the intake questions, the
architecture option, and the design direction are one sitting. When the PM
unit validates, the orchestrator routes the architecture-options unit and the
design-directions unit in the same batch, both reading the PRD and backlog at
proposed status. When both return, the harness fires one direction-review
checkpoint whose decisions list carries every question, the PRD approval, the
architecture options, the design directions, and any open defaults. It holds
all work past requirements until answered.

On the response, the PRD and backlog are confirmed with the human's edits, the
selected option and direction are recorded, and both downstream sets start in
one batch. When the response edits the PRD in a way that invalidates an
option or a direction, the invalidated unit is re-routed once against the
confirmed PRD and its choice comes back as a follow-up decision at the next
gate that fires, not as a new sitting of its own.

The reference run spent a separate sitting each on the PRD, the architecture
options, the architecture confirmation, and the design direction. Under
standard those four are one.

## Gates hold only dependent work

An open gate names what it holds in its `holds` field: phase names, story or
artifact ids, or all. Everything outside the list keeps running while the
human is away. `derive-ready-queue.py` sets blocked only for a gate that holds
all, reports the rest in `held`, and the orchestrator routes around them.

| Gate | holds |
|------|-------|
| direction-review, prd-approval | all phases past requirements |
| architecture-options-selection | architecture, development |
| architecture-confirmation | development |
| design-direction-selection | design, and the development of UI stories |
| pr-merge | the stories in the PR, and any unit that edits a file the PR edits |
| security-compliance-flag | the flagged story or artifact |
| scope-change | all |

While a pr-merge gate is open the next file-disjoint batch builds on its own
branch, in its own worktree, from the protected base, so the human merging one PR never idles the
build of the next. Work that runs past an open gate never merges past it, and
never consumes an artifact the gate may change.

The loop exits waiting on a human only when the orchestrator returns an empty
batch while a gate is open. In the reference run there was no agent activity
for about 55 of the run's 70 hours, because every open gate stopped all work.

## Gate batching and auto-merge

The pr-merge gate fires per batch, where a batch is the set of stories the
orchestrator co-scheduled onto one branch, or the whole page on brochure. It
does not fire per story when several stories land in one PR. The reference case
opened five PRs and five gates for six kilobytes of code.

A run may set `auto_merge_on_green: true` in its run brief. Under that flag, on
brochure and small only, a Code Reviewer APPROVE plus a fully green
required-check set merges the PR with `gh pr merge --squash`, and the human
reviews the deployed result instead of each PR. The harness records the merge in
the cycle artifact. The flag defaults to false, is a human decision recorded in
the project CLAUDE.md, and never applies to saas or mobile. Autonomy autopilot
implies it. Under either, a PR that carries a `TODO(DEF-<n>)` placeholder or an
open blocking question is never auto-merged and goes to a human pr-merge gate
that lists them.

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
batch. Outside auto-merge the harness pushes and opens the PR but never merges
it, and it never bypasses protection, because the human merge is the gate. This is the default for every
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

An escalation reaches the human only when resolving it would change a stated
human constraint or the scope of a confirmed artifact. Everything else the
routed specialist rules in-cycle, records in the artifact's decision log and
the PR description, and the run moves on. In the reference case three of four
escalations went to the human: a favicon file count, which story owns a
heading, and TypeScript for a thirty-line script, the last ruled twice.

Under standard and autopilot a deferrable decision is not escalated at all.
The unit takes the recommended option and reports it for the defaults ledger.
An escalation is raised only for a blocking decision, for missing or
contradictory input that no default can cover, or for a conflict with approved
architecture.

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
- `scripts/claim-run.py <run-dir> claim|release|status [<session-id>]` holds
  the single-writer lock on a run with a heartbeat.
- `scripts/review-package.py <base> <head> --out <file>` writes the commit
  list, stat, and diff a reviewer reads, and refuses a range whose head does
  not descend from its base. The diff never enters the main session.
- `scripts/preflight.py [--profile <profile>]` checks once at run open that
  the interpreter, the venv, git identity, gh auth, node, npx, and a headless
  Chromium-family browser actually work, and prints the table the harness
  records in the run brief. A build unit in the reference run lost time
  discovering a broken chromium wrapper on its own.

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
board projection is opt-in per project. Run profiles, the run brief, the
mechanical Check, the fold-in and docs policies, the review bound, the
un-joined dispatch barrier, and batch-level pr-merge with opt-in auto-merge
were added after the brochure reference run. Autonomy levels, the defaults
ledger, the intake question sweep, the direction-review gate, and gates that
hold only dependent work followed from the same run's timing: about 55 idle
hours of 70 and nine gates for one page.
