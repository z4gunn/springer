# Springer Harness API Contract

API version: v1. Status: agreed 2026-11-01. A change to this contract is agreed before either side implements it.

## Contents

- Overview
- Scope
- Definitions
- Contract rules
- Transport and authentication
- Conventions
- Reads
- Event streams
- Operations
- Design review surface
- Screen coverage
- Changes made elsewhere
- Decisions
- Conformance

## Overview

This document defines the versioned HTTP and server-sent events (SSE) interface between the Springer harness daemon and its clients. This document covers every read, every write, the event streams, the error model, and the changes the interface requires in the state model.

## Scope

This document covers the interface the TUI uses, which is also the interface the chat line and a later web UI will use. This document does not cover the daemon internals (e.g. scheduler, Check, retrieval), the provider contracts (e.g. coding agent, source host), the TUI layout, or the channel that session hooks use to report events to the daemon. Those hooks are unchanged until step 5 of the branch sequence.

## Definitions

```
Client      - A consumer of this API (e.g. the TUI, a later web UI)
Cursor      - An opaque string naming a position in one run's event ledger
Ledger      - runs/<run_id>/events.jsonl, the append-only event file of one run
Operation   - A typed write request, the only way a client changes state
Projection  - A view rebuilt from the cycle log and the ledger (e.g. run-state)
SSE         - Server-sent events, a one-way HTTP event stream
TUI         - The terminal user interface of the harness
```

Unit, session, gate, cycle, and the risk levels L0 to L3 are defined in `runtime/references/state-model.md`.

## Contract rules

These rules are used to keep the TUI independent of how the work behind the API is done.

1. The daemon is the only implementation of this API. The mock sits at the coding agent provider slot, behind the daemon, and there will be no mock API server. The TUI talks to a real daemon at step 4 and at step 6 alike, so the Claude Code provider replaces the mock without a TUI change.
2. Reads are GET requests and have no side effects. Every write is an operation sent to one endpoint. See Decisions, D1.
3. The chat line is comprised of a model calling the same operations as the TUI, drawn from the published catalog. The chat line cannot do anything a click cannot.
4. A payload that has a schema under `runtime/schemas/` is served in that shape (e.g. `unit-spec-v1`, `hil-checkpoint-v2`), and this contract does not restate it.
5. A client must not read the run store or the daemon state files directly. The API is the only interface in the system between a client and the daemon.

## Transport and authentication

The daemon serves HTTP on the loopback interface, because a coding agent's control surface must not be reachable from the network. Remote access to a daemon on another machine is out of scope for v1, and an SSH tunnel is the supported path.

```
Bind        - 127.0.0.1 only. The port is written to ~/.springer/daemon.json at start.
Base path   - /v1
Format      - JSON, UTF-8. Timestamps are UTC in ISO 8601 form.
Token       - ~/.springer/api-token, mode 0600, created at onboarding.
Auth        - Authorization: Bearer <token> on every request except GET /v1/health.
```

The daemon must reject a request whose Host header is not a loopback name, and a request whose Origin header is present and not the daemon's own origin. These checks are used to stop a web page in the local browser from reaching the API by means of DNS rebinding.

## Conventions

The conventions in this section apply to every endpoint.

### Versioning

A change that adds a field or an endpoint stays in v1. A change that removes or retypes a field moves to `/v2`. A client must ignore fields it does not recognize. `GET /v1/health` returns `api_version` and `harness_version` with no token, so a client can report a mismatch before it authenticates.

### Consistency

Every run-scoped read carries `as_of`, the cursor the response reflects. A client fetches a snapshot, subscribes to the event stream with `after=<as_of>`, and misses nothing between the two. A client should refetch a projection on an event that changes it rather than computing state from events.

### Pagination

A list that can grow takes `cursor` and `limit` (default 100, maximum 1000) and returns `next_cursor`, which is null at the end.

### Errors

Every error response has one shape, so a client renders a failure from the code rather than from the HTTP status.

```json
{"error": {"code": "stale_version", "message": "The brief changed since version 4.", "details": {"current_version": 5}}}
```

| HTTP | Code | Meaning |
|------|------|---------|
| 400 | invalid_args | The args do not match the operation's schema |
| 400 | unknown_operation | The type is not in the catalog |
| 401 | unauthorized | The token is missing or wrong |
| 403 | forbidden_host | The Host or Origin check failed |
| 403 | not_allowed_for_actor | The operation is not open to this actor (e.g. a secret from the chat line) |
| 404 | not_found | The project, run, unit, session, or gate does not exist |
| 409 | stale_version | `base_version` no longer matches the brief |
| 409 | gate_already_answered | Another actor answered first. `details` carries the recorded response |
| 409 | illegal_transition | The unit or run state does not allow this operation |
| 409 | confirmation_invalid | The confirm token is expired, used, or bound to other args |
| 422 | critique_errors | `run.start` found blocking brief errors. `details` carries the critique |
| 423 | run_externally_held | A live non-daemon session holds the run lock. Reads still work |
| 500 | internal | The daemon failed. The audit log and the daemon log carry the detail |

## Reads

Reads are grouped by the resource they return. Paths under a run are abbreviated with the prefix `{run}`, which stands for `/v1/projects/{slug}/runs/{run_id}`.

| Path | Returns |
|------|---------|
| GET /v1/health | `status`, `api_version`, `harness_version` |
| GET /v1/daemon | `state` (running, parked), `parked_until`, `started_at`, `degradations` (e.g. a missing optional tool, as `springer doctor` reports them) |
| GET /v1/usage | One `usage-window-v1` record per provider account |
| GET /v1/operations/catalog | Every operation with its args JSON Schema, confirmation rule, and actor rule |
| GET /v1/audit | The audit log, filterable by `project`, paginated |
| GET /v1/projects | Project summaries |
| GET /v1/projects/{slug} | One project summary plus its registry record |
| GET /v1/projects/{slug}/brief | The brief view |
| GET /v1/projects/{slug}/brief/critique | The critique, computed on request from the file on disk. See below |
| GET /v1/projects/{slug}/provisioning | Checklist items with `item_id`, `secret_name`, `needed_by`, `present`. Never a secret value |
| GET /v1/projects/{slug}/runs | Run summaries, newest first |
| GET {run} | The run view |
| GET {run}/backlog | The backlog view |
| GET {run}/units | Unit summaries, filterable by `state` |
| GET {run}/units/{unit_id} | `spec` (`unit-spec-v1`), `state` (`unit-state-v1`), `risk`, `sessions` (`session-v1` each), `retrieved` |
| GET {run}/units/{unit_id}/diff | The unit's PR diff as `text/x-diff` |
| GET {run}/gates | Gates, filterable by `state` (open, answered) and `digest` |
| GET {run}/gates/{gate_id} | The gate view |
| GET {run}/metrics | `product_checks_per_100_dispatches`, `failure_class_mix`, `dispatches`, `list_price_spend_usd`, `daily_cap_usd` |
| GET /v1/projects/{slug}/design-session | `url`, `expires_at`. See Design review surface |

### Project summary

The project summary is used by the Projects screen to show every project's status without opening it.

```json
{"slug": "acme", "name": "Acme", "path": "/srv/acme", "profile": "saas", "deploy": "self-hosted",
 "runtime_version": "abc1234", "archived": false,
 "active_run": {"run_id": "acme-1", "phase": "development", "open_gates": 1, "in_flight": 2,
                "paused": false, "waiting_on": null, "externally_held": false}}
```

`waiting_on` is null, `usage_window`, `gate`, or `provisioning`. `active_run` is null when the project has no run in progress.

### Brief view

The brief view is used by the Brief screen, and it splits `docs/brief.md` into the machine fields and the sections. `docs/brief.md` stays the source of truth, and the daemon is its only writer while a client is connected.

```json
{"version": 4, "started": false,
 "facts": {"surfaces": ["web"], "backend": "yes", "accounts": "multi-org", "payments": "subscription",
           "scale": "team", "autonomy": "autopilot", "deploy": "self-hosted", "pinned": {"db": "postgres"}},
 "derived": {"profile": "saas", "lane": "build",
             "sentence": "A multi-org product that charges money runs as saas."},
 "sections": [{"name": "Problem", "required": true, "confidence": "confirmed", "body": "..."}],
 "recommendation": {"verdict": "go", "summary": "...", "dismissed": false}}
```

`confidence` takes the values confirmed, proposed, and needs-human-input. `recommendation` is null unless Discovery produced one. The critique returns `errors`, `warnings`, and `info`, each a list of `{"rule": "flow-without-outcome", "section": "Core flows", "message": "..."}`.

### Run view

The run view is the `content` of `run-state-v2` with four additions. `as_of` is the cursor, `paused` and `waiting_on` are as in the project summary, and each `in_flight` row gains `last_tool_call`, which the daemon reads from the session stream.

### Backlog view

The backlog view is used by the Backlog screen for the tree, the board, and the graph, all from one response.

```json
{"as_of": "c-1842", "state": "generated",
 "epics": [{"epic_id": "E-1", "title": "Invoice a client", "critical": true,
   "features": [{"feature_id": "F-3", "title": "Invoice editor", "mvp": true, "deferred": false,
     "stories": [{"story_id": "S-12", "title": "Save a draft", "column": "in_review", "risk": "L1",
                  "wave": 2, "unit_ids": ["U-0412"], "pr": {"number": 7, "url": "..."},
                  "depends_on": ["S-9"]}]}]}],
 "unknowns": [{"unknown_id": "UK-1", "question": "...", "answer": null}]}
```

`state` is `not_generated` with empty lists until the backlog exists. `column` is one of ready, in_progress, in_review, blocked, done. The dependency graph is carried by `depends_on`, and the MVP line by each feature's `mvp` flag, so the view has one source for each fact.

### Gate view

The gate view is the `content` of `hil-checkpoint-v2` plus a `context` object, and it holds what a person needs to answer without leaving the TUI.

```json
{"context": {"task": "...", "findings": [{"vertical": "spgr-agent-auth", "rule": "...", "detail": "..."}],
             "builder_response": "...", "diff_path": "/v1/projects/acme/runs/acme-1/units/U-0412/diff",
             "design_session": false, "age_seconds": 3600}}
```

`design_session` is true when the gate needs a browser (e.g. direction review), and the client then requests a design session.

### Session stream

`GET {run}/units/{unit_id}/sessions/{session_id}/stream` serves the session's captured stream-json as SSE, starting at `after` (default the start of the stream). The stream closes when the session reaches a terminal state, and a replay of a finished session works the same way. The stream is separate from the event ledger, because a session emits far more lines than the run screen needs in its feed.

## Event streams

Two SSE streams are used to tell a client what changed. Each frame's `event` field is the event name and `data` is one JSON object.

### Run stream

`GET {run}/events?after=<cursor>` serves the ledger of one run in order, with each `data` being an `events-v1` line unchanged. The `id` field is the cursor, and a reconnect with `Last-Event-ID` or `after` resumes at the next line.

The cursor is a position in the ledger rather than `seq`, because lines written by the session hooks carry no `seq` and a stream keyed on `seq` would skip them. A client must treat the cursor as opaque. A `heartbeat` frame is sent every 15 seconds. A `resync` frame is sent when the cursor cannot be honored, and the client refetches its snapshot.

### Daemon stream

`GET /v1/events` serves a summary across all projects for the Projects screen and the gate badge, and it has no replay. A client refetches `GET /v1/projects` on connect.

| Event | Data |
|-------|------|
| project_status | One project summary |
| gate_opened | `project`, `run_id`, `gate_id`, `level` |
| gate_answered | `project`, `run_id`, `gate_id` |
| daemon_state | `state`, `parked_until` |
| window_sample | `provider`, `used_fraction`, `resets_at` |
| heartbeat | Empty |

## Operations

An operation is a typed write, and `POST /v1/operations` is the only write endpoint in the system. The daemon applies an operation under the run's single-writer rule, records it, and returns the outcome.

### Request

The request names the operation and carries a client-generated id, so a retry after a dropped connection is not applied twice.

```json
{"op_id": "0f6c1e0a-...", "type": "gate.answer", "project": "acme", "run_id": "acme-1",
 "args": {"gate_id": "G-0007", "option": "approve"}, "confirm_token": null}
```

`project` and `run_id` are omitted on an operation that has no such scope (e.g. `config.set_role_model` takes no `run_id`). A repeated `op_id` returns the recorded outcome and applies nothing. The actor is set by the daemon from the connection, as `tui` for a token holder, `chat` for the chat agent, and `channel:<name>` for a notification reply. A client cannot claim an actor.

### Response

The response status is one of three values. A rejected operation returns an error response instead.

```json
{"op_id": "0f6c1e0a-...", "type": "gate.answer", "status": "applied", "cursor": "c-1843", "result": {}}
```

```
applied             - The change is recorded. cursor names the ledger line for a run-scoped operation.
accepted            - The change is recorded and work continues (e.g. run.start). result names what to watch.
needs_confirmation  - Nothing changed. preview and confirm_token are present.
```

### Confirmation

Confirmation is used to hold a change to scope or configuration until a person has read its consequence, in the same manner for a click and for the chat line. The first request returns `needs_confirmation` with `preview` (`summary` and a `consequences` list) and `confirm_token`. The client shows the preview, and on a yes sends the same request with the token. A token is single use, expires after 5 minutes, and is bound to the type and the args, so a confirmed preview cannot apply to a different change.

An operation sent by the chat actor always requires confirmation when it changes state, whatever the catalog says for a click. The chat line can opt to propose several operations in one reply, and each is confirmed separately.

### Catalog

The catalog is the closed list of writes in v1, and `GET /v1/operations/catalog` publishes it with the args schemas. The Confirm column applies to the `tui` actor. Secrets are the one exception to chat parity, because a value typed into the chat line would reach a model.

| Type | Args | Confirm | Effect |
|------|------|---------|--------|
| project.create | `name`, `path`, `mode` (new, adopt) | Yes | Scaffolds or adopts the repository and registers it |
| project.archive | none | Yes | Hides the project and refuses a new run. Deletes nothing |
| brief.update_section | `section`, `body`, `base_version` | After start | Writes the section and marks it confirmed. After `run.start` it opens a scope-change gate |
| brief.update_facts | `facts`, `base_version` | After start | Writes the frontmatter and recomputes `derived`. After `run.start` it opens a scope-change gate |
| brief.confirm_section | `section`, `base_version` | No | Marks a proposed section confirmed unchanged |
| brief.run_discovery | `sections` (list, or all) | Yes | Dispatches Discovery against the named sections. Returns accepted |
| brief.dismiss_recommendation | none | No | Hides the go or no-go banner |
| run.start | `base_version` | Yes | Commits the brief and opens the run. Fails with critique_errors while an error stands. Returns accepted |
| run.pause | `reason` | No | Stops claiming and dispatching. In-flight sessions finish and Check still runs |
| run.resume | none | No | Clears the pause |
| unit.cancel | `unit_id` | Yes | Kills the live session and moves the unit to cancelled |
| unit.redispatch | `unit_id`, `model_tier` (optional, equal or higher) | Yes | Kills the live session if any and moves the unit to redispatch. No retry is spent |
| gate.answer | `gate_id`, `option`, `decisions`, `free_text`, `rule_change` | With rule_change | Records the response and releases what the gate holds. `decisions` carries one `{decision_id, response}` per item of a one-sitting gate, and `free_text` carries the structure notes. `rule_change` updates the risk rules file |
| digest.mark_viewed | `gate_ids` | No | Closes digest entries |
| backlog.move_mvp_line | `after_feature_id` | Outside scope review | Moves the line |
| backlog.defer_feature | `feature_id` | Outside scope review | Tags the feature deferred. Its tasks stay in the graph |
| backlog.restore_feature | `feature_id` | Outside scope review | Clears the deferred tag |
| backlog.reorder | `story_id`, `position` | No | Reorders within a wave. A move that breaks a dependency returns illegal_transition |
| backlog.add_bug | `title`, `description`, `severity` | No | Adds a bug to the backlog |
| backlog.answer_unknown | `unknown_id`, `answer` | No | Records the answer |
| provisioning.set_secret | `item_id`, `value` | No | Stores the value in the OS keyring. The value is never logged, returned, or recorded. Refused for the chat actor |
| config.set_role_model | `role`, `model` | Yes | Changes the model for a role (e.g. the reviewer) |
| config.set_gate_channels | `level`, `channels` | Yes | Changes where gates of that level notify |

Moves of the MVP line during an open scope review take no confirmation, because `gate.answer` on that gate is the commit. A human answer to a production-release gate is the one click the release takes, and the daemon must never apply one from an actor other than a person.

### Chat

The chat line is exposed as one endpoint, which is a stub until the chat agent is built. `POST /v1/chat` takes `{"session_id": null, "project": "acme", "message": "..."}` and streams SSE frames of `text` and `proposed_operation`, closing with `done`. A `proposed_operation` frame carries an operation request and its preview, and the client confirms it with the flow above. At step 4 the stub answers that the chat agent is not built and proposes nothing.

## Design review surface

Design artifacts are served to a browser, because mockups and comps do not fit in a terminal. A browser cannot send the bearer header on a navigation, so `GET /v1/projects/{slug}/design-session` returns a URL with a one-time code valid for 60 seconds. The first load exchanges the code for an HttpOnly cookie scoped to `/design/{slug}/`, valid for 8 hours. The surface serves the files under the project's `docs/design/`, must refuse any path outside it, and has no write capability. See Decisions, D4.

## Screen coverage

This section is used to check the contract against what the target README promises, with respect to each screen. A row with no endpoint would be a gap in the contract.

| Screen | Feature | Served by |
|--------|---------|-----------|
| Projects | List with status | GET /v1/projects, daemon stream |
| Projects | New, open, archive | project.create, project.archive |
| Brief | Editor, facts panel, derived profile | GET brief, brief.update_section, brief.update_facts |
| Brief | Critique | GET brief/critique |
| Brief | Discovery, proposed sections, go or no-go | brief.run_discovery, brief.confirm_section, brief.dismiss_recommendation, gate.answer |
| Brief | Interview | POST /v1/chat, writing through brief.update_section |
| Brief | Start run | run.start |
| Brief | Provisioning entry | GET provisioning, provisioning.set_secret |
| Backlog | Tree, board, graph, MVP line, risk tags | GET {run}/backlog |
| Backlog | Move line, defer, restore, reorder, add bug, answer unknown | backlog.* |
| Backlog | Open the PR | `pr.url` in the backlog view |
| Run | Phase, in-flight rows with agent, model, elapsed, context, cost, last tool | GET {run}, run stream |
| Run | Live session output | Session stream |
| Run | Gate cards, recommended option first, consequences | GET {run}/gates, GET gate view, gate.answer |
| Run | Risky merge diff | GET units/{unit_id}/diff |
| Run | Feed of routine decisions | GET {run}/gates with `digest=true`, digest.mark_viewed |
| Run | Cancel, re-dispatch, pause | unit.cancel, unit.redispatch, run.pause, run.resume |
| Run | Waiting on usage window, list-price spend | `waiting_on`, GET /v1/usage, GET {run}/metrics |
| Run | Design gate opens the browser | `design_session`, GET design-session |
| All | Chat line | POST /v1/chat, catalog |
| All | Audit of applied operations | GET /v1/audit |

## Changes made elsewhere

The contract could not be served by the state model as first written, and this section lists each change it required. All of them touch files added at step 2 and no file the no-rewrite rule protects.

| File | Change | Reason |
|------|--------|--------|
| `events-v1.json`, state-model Events table | Add `operation_applied` with `op_id`, `type`, `actor`, `args`. A secret value is never in `args` | The ledger has no record of a human intervention, and the projection must rebuild from it. See D2 |
| `run-state-v2.json` | Add `paused`, `waiting_on`, and `last_tool_call` on `in_flight`. Drop the v1 cap of two on the `wip_board` stages | The run view reads the fields and the projection owns them. An L2 hold never blocks the agent, so review can exceed the WIP limit, and the scheduler enforces the limit |
| `hil-checkpoint-v2.json` | Add `checkpoint_type` values. See D5 | Several gates in the design notes have no type |
| state-model Entities table | Add the audit log at `~/.springer/audit.jsonl`, written by the daemon | An operation with no run (e.g. config) has no ledger, and the design notes require an audit log of applied operations |
| state-model Events section | State that the API cursor, not `seq`, orders a stream | Hook lines carry no `seq` |

## Decisions

Each decision below is Decided. Each one names its governing reason and the condition that would reopen it.

| Id | Decision | Governing reason | Revisit when |
|----|----------|------------------|--------------|
| D1 | One `POST /v1/operations` endpoint with a published catalog, not REST verbs per resource | The chat line, the audit log, confirmation, and idempotency then each exist once, and the catalog is the proof of chat parity | A web UI needs HTTP caching or per-route access rules on writes |
| D2 | An intervention is recorded as an `operation_applied` event. The design notes say it writes a cycle record | `pdca-cycle-v1` requires a plan, do, check, and act, and an intervention has none of them. State-model principle 1 allows a cycle record or an event | The retrospective cannot read interventions from the ledger |
| D3 | Pause applies to the run. The design notes place it on the unit row | The unit lifecycle has no paused state, and pausing a live session has no provider primitive. The unit row offers cancel and re-dispatch | A run shows a need to hold one unit while its siblings continue |
| D4 | The design page is read-only at v1, and structure notes and the pick go through `gate.answer` in the TUI | One write path. The design notes place the web UI later, starting with this surface | Written notes without pinning to a mockup prove too imprecise |
| D5 | Add `checkpoint_type` values `discovery-go-no-go`, `structure-confirmation`, `scope-review`, `taste-review`, `production-release`, `provisioning-required`, `routine-decision`. Brief submit is `run.start` and has no gate record | Each is a gate the design notes define. `scope-change` is an edit after start and is a different event from the MVP review. Brief submit has no decision to record beyond the operation | A gate appears that fits none of these |

## Conformance

The contract is enforced by tests rather than by this document alone. Step 3 will define the payloads as Pydantic models in `harness/springer_harness/api/`, generate `harness/openapi.json` from them, and commit it. A test must fail when the served schema differs from the committed file, so a contract change is visible in review. A test suite runs each catalog operation and each read against the real daemon with the mock provider, and a test must fail when a catalog entry has no test. The Screen coverage table is carried into the TUI build at step 4 as its acceptance list.
