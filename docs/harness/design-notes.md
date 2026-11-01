# Springer Harness and Design-to-Build Flow: Design Notes

Date: 2026-11-01
Author: z4gunn, with Claude
Status: design notes for ingestion into the Springer build, revision 7

## Purpose

This document records the design of an opinionated, near-autonomous software development workflow for a web SaaS or React Native product, from a written brief to a released MVP, and the design of a standalone Springer harness that drives that workflow with the human working almost entirely in a TUI. It covers the canonical workflow and its human gates, the design-to-build stages and their artifacts, the stack and deployment profiles, the conventions and backlog rules, the risk and merge policy, the agentic principles the whole thing rests on, the harness product model and architecture, retrieval, a pragmatic review of gaps and gotchas, a gap analysis against the current Springer repository, and a phased build plan.

## Decisions

| Topic | Decision |
|-------|----------|
| Workflow | One opinionated path: brief, requirements, design directions with architecture options in one sitting, structure pass, architecture locked, conventions, design system as code, optional high-fidelity variants, screen specs, backlog and MVP cut, walking skeleton, features, release, retrospective |
| Human gates | Five: brief submit, direction review (with structure notes), scope review, L2 merge holds, production release. Optional: go or no-go when starting from Discovery, taste review when variants are on |
| Entry points | Two. Write the brief directly, or write only an Idea and let Discovery draft the brief as proposed sections for the human to confirm |
| Human interface | TUI first (Python, Textual), web UI later. The daemon serves design artifacts on localhost so the TUI can open a browser for mockup and comp review |
| Brief | One file, docs/brief.md, YAML frontmatter plus prose sections. The human-authored source of truth that run-brief.json projects from. Versioned, and an edit after Start run is a scope-change gate |
| Profile | Never shown as a choice. Derived from product facts in the brief (surfaces, backend, accounts, payments, scale) and recorded read-only. The five internal profiles and everything downstream that reads them are unchanged |
| Autonomy | The one run setting the user picks explicitly, named by what they experience: ask at every step, one review sitting then run, run and stop only for risk |
| CLI surface | Two commands a user must know: springer onboard and springer. Everything else is in the TUI or the chat line |
| Harness | Springer-specific daemon, Python, Agent SDK, one daemon serving many projects, SDK sessions as subprocesses in a worktree |
| Coding agent providers | Provider contract designed now. Claude Code is the only builder provider at v1. Other agents join as reviewers through an adapter, builder parity is a later milestone |
| Bring your own | Source host, backlog projection, notification channels, staging targets, design tools, memory backend, all behind small provider contracts |
| Assumptions | Reversible decisions are taken by default and logged (L1). Irreversible decisions escalate before start (L3). Agents never stop mid-task to ask |
| Merge policy | L0 and L1 auto-merge on green. L2 holds the merge only. L3 blocks before start. The harness is the only merger |
| PR size | Small. One task, one PR, stacked branches for dependent work |
| Target surfaces | Web only, mobile only (Expo), or both |
| Stack | TypeScript monorepo, Next.js for web, Expo and Expo Router for mobile, shared packages/ui |
| Deployment profiles | Cloud (Vercel, Supabase) or self-hosted (one VPS, Docker Compose, Coolify or Dokploy). No Kubernetes |
| CI | Local, on the orchestrator machine, receipts as the evidence. GitHub free tier as remote, no Actions |
| Staging | Local Linux farm, Compose per branch, a Mac for iOS simulators |
| Cost and auth | v1 runs on Claude Code subscription session auth, not an API key. The daemon budgets against the plan's usage windows, sleeps through a limit to the reset, and shows window usage and list-price equivalent spend in the TUI. An API-key path with a dollar cap is kept as a switch for later |
| Build order | The orchestrator state model is designed first, because it is the one thing expensive to change later. Done, see springer-state-model.md. Then Phase 0, the harness walking skeleton. Task templates and the risk rules file are written the day they are needed |
| State model | Approved as written in springer-state-model.md: the unit as a first-class entity, sessions tracked separately, gates with level and holds, the usage window as daemon state, mechanical crash recovery, and overlapping cycles with disjointness computed from declared paths |
| Branch | A new branch of the Springer repository. Greenfield for the harness package, the runtime brought over as a unit pruned by profile, the repository restructured into harness/ and runtime/. See Branch strategy |
| Backlog default | Files in the repository plus the TUI board. A tracker is an optional one-way projection |
| Design system | Per product, tokens emitted as code into packages/ui, extracted from real wireframe needs |
| Prototype carry-forward | Tokens, primitives, patterns, and Zod contracts carry forward. Screen composites are specified and rebuilt. The prototype directory is deleted |
| RAG | Harness-owned FTS5 index over structured records. Embeddings only if misses are observed |
| Compliance | One vertical agent per framework |

## The opinionated workflow

This is the canonical path. Every other section serves it. A human gate is marked (gate).

There are two entry points. A user who knows what they want starts at step 1 and writes the brief. A user who has an idea but does not know the users, the market, or the flows starts at step 0, and Discovery drafts the brief for them to confirm.

0. Discovery (optional entry point, gate: go or no-go). The user writes only the Idea section of the brief: a paragraph on the idea and who it might be for. The Discovery agent runs market research, competitive analysis, user-feedback mining (forums, app store reviews, review platforms), persona and ICP construction, market sizing, and a go or no-go recommendation. Its output is written into the brief's Problem, Users, Core flows (as candidates), Constraints, and Inputs sections, each marked proposed, with the research artifacts under runs/ and a readable docs/discovery.md. The human reads the recommendation, confirms or edits each proposed section, and either continues to step 1 or stops. A no-go closes the run with the research kept.

1. Brief (gate: submit). The human writes the problem, users, core flows, non-goals, and the rest of docs/brief.md in the TUI brief editor, with the chat line in interview mode asking the questions a product manager would and writing the answers into the sections. The side panel collects the product facts (surfaces, backend, accounts, payments, scale), deploy, pinned decisions, and autonomy, fills defaults for anything blank, and shows the derived profile as a sentence. Check brief runs the critique inline. Start run commits. The brief is specified in full under The brief below.
2. Discovery as a step (optional). When the user started at step 1 but a brief section is thin, the chat line offers to run Discovery against it rather than the whole product, for example mining reviews of the named competitors to firm up a persona. On brochure and small this runs only when asked.
3. Requirements. PRD, story backlog within the profile caps, acceptance criteria, NFRs, risk register, definition of done. The developer who will build first reads the draft cold and sorts the intake questions so only the ones that need the human reach the gate.
4. Design directions and architecture options, one sitting (gate: direction review). Three or more structurally distinct directions rendered as low-fidelity HTML mockups plus one hero comp each, side by side with the architecture options for whatever the brief did not pin. The human answers intake questions, picks an architecture option per open decision, picks a direction, and writes structure notes on its mockups.
5. Structure pass. The design agent applies the structure notes, re-renders, and pauses once more only if notes were given. Structure is frozen. No IA, wireframes, or tokens before this point.
6. Architecture locked. ADRs for the gate-list decisions are immutable. The provisioning checklist (accounts, keys, domains, store credentials the human must supply) is emitted here.
7. Conventions. Generated once from the stack profile and reviewed in the next gate batch.
8. Design system as code. IA, wireframes, tokens emitted into packages/ui/tokens, comps rendered from those files through Playwright (react-native-web on mobile) and iterated against the design-quality critique until they pass. Tokens lock only then.
9. High-fidelity variants (optional, gate: taste review). Two or three token treatments of the key screens, each past the detector, compared side by side. The human picks and writes a delta.
10. Screen specs, state tables, interaction and accessibility specs. Screen coverage check against every story.
11. Backlog and MVP cut (gate: scope review). Epics from flows, features from screen clusters, tasks from a fixed type vocabulary, a dependency graph, a critic pass, and a proposed MVP line. The human moves the line and answers the unknowns list.
12. Walking skeleton. The primary flow end to end, thin, deployed to staging, product check passing, in one PR. Nothing else builds until it lands. Blocked until the provisioning checklist is satisfied.
13. Features. One feature at a time to done, polish ceremony for everything that does not touch a gate-list surface. L0 and L1 merge on their own, L2 holds for the human (gate: merge holds), digests summarize the rest.
14. Release (gate: production). Promotion from staging, EAS submit for mobile.
15. Retrospective. Learnings proposed, unexercised rules listed, human promotes rule changes.

Under autopilot the human touches the keyboard at the brief (or the idea plus the go or no-go), the direction review, the scope review, occasional L2 holds, and the release. Everything else is observation.

## The brief

The brief is the human's main work product and the input to everything else. One file, docs/brief.md, with YAML frontmatter for the machine fields and prose sections for the product. The existing run-brief.json stays a derived projection and gains the new fields. Validated by schemas/brief-v1.json.

### Frontmatter

```yaml
---
brief_version: 1
name: acme
surfaces: [web, mobile]      # web | mobile | api | cli, one or more
backend: yes                 # none | yes
accounts: multi-org          # none | single-org | multi-org
payments: subscription       # none | one-time | subscription
scale: team                  # personal | team | public
autonomy: autopilot          # supervised | standard | autopilot (shown by what the user experiences)
deploy: self-hosted          # cloud | self-hosted
staging: staging-1           # a host registered in the harness
reach: regional              # regional | global (global tags the i18n vertical)
frameworks: [gdpr]           # compliance verticals to dispatch
variants: 3                  # 0 | 2 | 3
reference: null              # a POC or earlier version treated as the spec
pinned:                      # architecture decisions taken as given
  db: postgres
  auth: better-auth
  api: hono
budget:
  daily_cap_usd: 40
profile: saas                # derived, read-only, written by the harness
lane: build                  # derived from one question, written by the harness
---
```

### Profile derivation

The five internal profiles (brochure, small, saas, mobile, api) stay as they are, because everything downstream reads them. The user never picks one. The harness derives it from product facts, in the existing precedence, and shows the result as a sentence the user can correct by fixing the fact that produced it.

| Facts | Profile |
|-------|---------|
| surfaces includes mobile | mobile |
| payments is not none, or accounts is multi-org | saas |
| surfaces is api or cli only | api |
| web with backend | small |
| web with no backend | brochure |

scale replaces the mobile-only size field. scale personal gives the small ceremony on any profile. lane is derived from one question the harness already asks, whether the product runs somewhere a user can reach it.

### Pinned decision ids

A closed list the Architect matches against: hosting, db, orm, auth, api, jobs, realtime, billing, email, storage, analytics, errors, tenancy. An unknown key fails validation. A value is a known option, or the word options to force an options-mode decision where the deploy profile would otherwise default.

### Body sections

| Section | Required | Becomes |
|---------|----------|---------|
| Idea | Only when starting from Discovery | The Discovery agent's input. A paragraph on the idea and who it might be for |
| Problem | Yes, one paragraph | PRD problem statement |
| Users | Yes, one to four | Personas, ICP seed |
| Core flows | Yes, one or more | One epic each. Each flow has a name, who, trigger, steps, outcome, and a critical flag |
| Non-goals | Yes, may say none yet, the critique pushes | Scope guard in the PRD and the critic pass |
| Success criteria | Recommended | MVP cut inputs, product checks |
| Constraints | Optional | Architect inputs: integrations, legal, budget, timeline, existing systems |
| Design preferences | Optional | Direction stage: tone words, references, anti-references, brand assets |
| Inputs and references | Optional | docs/inputs ingestion, competitor links |
| Glossary | Optional | Domain terms carried into every agent brief |
| Open questions | Optional | Seeded into the intake sweep |

Core flows are the load-bearing section. A flow with a trigger, steps, and an outcome is an epic with its E2E test implied. The critical flag drives the walking skeleton (the simplest critical flow) and the MVP cut proposal.

### Two ways to fill the brief

From the head: the human knows the users and the flows. The interview below extracts them and writes them into the sections.

From the market: the human has an idea and not much else. They write the Idea section, the TUI offers Run discovery, and the Discovery agent fills Problem, Users, Core flows, Constraints, and Inputs as proposed sections with the research behind each. The human confirms or edits each one. Every section a human has edited is marked confirmed, every section still carrying the agent's draft stays proposed, and Start run requires the required sections to be confirmed. The go or no-go recommendation is shown at the top of the brief until the human dismisses it.

The two can mix. A human who wrote the flows but has no persona can run Discovery for Users only. The chat line offers this whenever a section is empty or thin.

### Interview question set

The chat line's interview mode asks these in order, each unlocking the next, each writing into one section, each with a recommended default when skipped. The first question decides the entry point.

0. Do you know who this is for and what they will do with it, or do you want me to research that first? Yes continues to question 1. No takes the Idea section and runs Discovery, then resumes at question 1 with the sections prefilled.
1. What does the person do today without this product, and what goes wrong? Problem.
2. Who are they? The one or two people you picture. Users.
3. Walk me through the one thing they would do first, then the next. Core flows, with follow-ups on trigger, how they know it worked, and the failure case.
4. Which of those would you be embarrassed to ship badly? Critical flags.
5. What are you deliberately not building in the first version? Non-goals.
6. How will you know the MVP worked? Success criteria.
7. Does it have a backend, does it have accounts for one or many organizations, does it charge money, is it for you, a team, or the public? The product facts.
8. Where will it run, and do you have opinions on the stack? Deploy and pinned.
9. Any data rules, regions, or compliance you already know apply? Frameworks and reach.
10. Two products whose look you like and one you do not. Design preferences.
11. Anything you already have: specs, designs, a prototype, a brand? Inputs and reference.

### Critique rules (Check brief)

Errors block Start run. Warnings show inline. The existing buildability check runs as part of this.

- Error: a flow without an outcome, a user referenced in a flow but absent from Users, no critical flow, an unknown pinned key, a staging host not registered in the harness, a surface that contradicts a flow (a mobile-only flow with no mobile surface).
- Warning: non-goals empty, no success criteria, a pinned value that conflicts with the deploy profile (Supabase on self-hosted), variants set when the derived profile is brochure, a glossary term used inconsistently, a flow with more than about twelve steps.
- Info: an input mentioned in prose but not present under docs/inputs, which becomes an intake question rather than an error.

### Derivation

brief.md projects into run-brief.json (frontmatter into flags plus surfaces, deploy, pinned, frameworks, and the derived profile and lane), into the PM inputs (the body as the problem statement, confirmed on brochure, discovery seed otherwise), into the Architect (pinned as team_constraints, which already exists as an input), into Design (preferences and references), and into the backlog (flows as epics ordered by the critical flag).

Kept out of the brief: provider choices (coding agent, channels), which are harness configuration, and anything the harness can derive.

## Lifecycle methodology

From agile and Scrum: small verifiable units, acceptance criteria as the contract, dependency ordering, the epic to feature to task hierarchy. Not sprints, points, standups, or retro ceremonies. The user-story form is replaced by a task spec with preconditions, inputs and outputs, edge cases, and an executable check.

From XP: test-first, builder plus separate critic in place of pairing, continuous integration with small commits, scheduled refactoring, collective ownership.

From Kanban: pull scheduling from a dependency graph, WIP limits per package, explicit stages with exit gates.

From waterfall: big up-front definition. Its weakness with humans was long build phases and expensive rework. With agents the build is short and rework is cheap, so detailed definition before autonomous execution is the right trade.

What agents need that no methodology supplies: architectural invariants written down and enforced mechanically, and explicit verification gates.

## Phase A: brief to repo foundation

| Stage | Who | Output artifact |
|-------|-----|-----------------|
| Discovery (optional entry) | Discovery agent from the Idea section, human confirms | Proposed brief sections, docs/discovery.md, research artifacts under runs/, go or no-go |
| Brief | Human, with the interview chat | docs/brief.md, docs/inputs/ |
| Requirements | PM agent | PRD, backlog, criteria, NFRs, DoD under runs/ |
| Design directions | Design agent, human picks | docs/design/<direction>/ mockups, docs/design/directions.md |
| Structure pass | Design agent applies notes, human confirms | docs/design/screens.md (screen inventory, flow graph) |
| Architecture | Architect per decision mode, human approves | docs/adr/, stack-profile.md, provisioning checklist |
| Conventions | Generated, reviewed once | packages/config, packages/conventions |
| Design system | Design agent | packages/ui (tokens as code, primitives, patterns), DESIGN.md |
| Variants (optional) | Design agent renders, human picks | docs/design/selection.md |
| Screen specs | Design agent | docs/spec/screens/, docs/spec/states.md |
| Seed data | Generated from packages/types | packages/db/seeds |

### Structure before style

Structure is what is on each screen and how screens connect. Style is how it looks. Reviewing both in one round never converges, because a structural note invalidates the restyle. Structural feedback happens on grayscale mockups. When there are no structural notes, structure is frozen and only then are tokens applied. Style feedback is cheap after that because the layout is not moving.

### Design-aid tools and where each applies

| Stage | Tool | Role |
|-------|------|------|
| Direction | ui-ux-pro-max, Lazyweb MCP | Pick from rendered styles, palettes, and real reference screenshots |
| Context | impeccable init, Anthropic frontend-design | PRODUCT.md and DESIGN.md seed, a typeface and style chosen before code |
| Mockups | impeccable shape, Claude Design (optional) | Plan UX before code, compare structural options |
| Structure pass | impeccable critique | Hierarchy, clarity, navigation, as a written delta before the human sees the mockups |
| Design system | impeccable extract, theme-factory | Tokens and components from what the mockups needed |
| High fidelity | Taste skill, impeccable polish | Premium defaults and the final pass, after structure is frozen |
| Anti-slop gate | impeccable audit, Playwright | Deterministic detector rules plus screenshot diff, before the human sees the work |
| Figma MCP | Optional | Bidirectional with Code Connect. Reintroduces a translation step, so only when a canvas artifact is required |

The design-aid tools pull toward "looks good" and the anti-slop tools toward "looks distinctive". The detector can pass a clean but bland design. The taste gate is where "is this ours" is decided.

These tools are web-first. For React Native a thin project skill encodes NativeWind conventions, safe area, keyboard, and gesture patterns, and the aesthetic tools run against a react-native-web render.

### Variants

At direction: three directions, one representative screen each. At high fidelity: two or three token treatments of the same frozen structure, varying density, type scale, color weight, and component style, never layout. Each variant is a separate agent run with an explicit instruction to differ along named axes, because identical inputs converge. Each passes the detector before display. The review output is a pick plus a delta, and a cross-variant pick is a token edit. Variants render only the two or three highest-leverage screens. Off by default on brochure and small.

### Carry-forward boundary

| Layer | Carries forward |
|-------|-----------------|
| Tokens, Tailwind or NativeWind config | Yes, verbatim |
| Primitives in packages/ui | Yes, versioned |
| Pattern docs, DESIGN.md | Yes |
| Zod schemas used by fake data | Yes, into packages/types |
| Screen composites | No, specified and rebuilt |
| Navigation | As the flow graph, rebuilt in Expo Router |
| Fake data and prototype state | No, replaced by generated seeds |

Deleting the prototype directory is a deliberate step. If it stays, agents reference it.

## Stack, deployment profiles, and architecture intake

### Stack

TypeScript end to end with schema-driven types: Drizzle schema to DB types to Zod validators to API types to form types. Web: Next.js App Router. Mobile: Expo, Expo Router, EAS, New Architecture. Shared: TanStack Query, Zustand, React Hook Form and Zod, NativeWind. UI: shadcn/ui on web, NativeWind with a shadcn-style port or Tamagui on mobile.

Server Components do not exist on React Native. The sharing boundary is components yes, data fetching through TanStack Query hooks against a Hono or tRPC API yes, RSC-specific patterns no. A product with both surfaces has a Hono or tRPC API regardless.

### Monorepo layout

```
apps/
  web/            routes only, thin
  mobile/         routes only, thin
  prototype/      disposable, deleted after spec extraction
packages/
  ui/             tokens, primitives, patterns
  features/       <feature>/{api,components,hooks,model,index.ts}
  api/            Hono routes grouped by feature
  db/             Drizzle schema, migrations, seeds
  types/          Zod schemas, shared inferred types
  config/         lint, tsconfig, tailwind presets
  conventions/    CLAUDE.md fragments, generators, example files
```

### Deployment profiles

| | Cloud | Self-hosted |
|---|---|---|
| Host | Vercel (web), EAS (mobile) | Coolify or Dokploy on one VPS, EAS (mobile) |
| Backend default | Supabase | Hono, Drizzle, Postgres |
| Auth default | Supabase Auth or Better Auth | Better Auth |
| Jobs | Inngest or Trigger.dev | BullMQ in process with Redis |
| Web mutations | Server Actions, plus Hono for mobile | Hono for everything |
| Deploy artifact | git push | Docker image via git push |

Self-hosted constraints: plain Node server or Docker image output, no serverless assumptions, pg_dump backups to S3-compatible storage on a cron. Supabase self-hosted is heavy, so the self-hosted profile defaults to the self-assembled backend.

### Architecture intake

Architecture is a fixed list of decisions, each in one mode: dictated (pinned in the brief), default (from the deployment profile, the human can veto), or options (two or three with fit against the spec, operational cost, lock-in, and what each forecloses). Intake order: surfaces, hosting, backend style, API shape. The rest fall out. Options-mode decisions are ADRs. The gate-list ADRs (data model and tenancy, auth, billing, vendor, anything irreversible) are immutable once approved.

Because the architecture option is chosen in the same sitting as the design direction, the stack is known before the design system is emitted as code.

### Provisioning checklist

Agents cannot create third-party accounts. At architecture lock the harness emits the list of human-provisioned inputs: payment provider keys, OAuth app registrations, Apple and Google developer accounts, domains and DNS, email-sending domain verification, analytics and error-tracking projects. Each item has a secret name and a place to enter it in the TUI. The walking skeleton deploy is blocked until the items it needs are present, under the same rule as content sources.

## Conventions package

Enforce, do not describe. Three tiers.

Tier 1, machine-enforced: strict lint and format config (import order, no default exports, naming, no any, exhaustive switches), tsc strict with noUncheckedIndexedAccess, dependency boundaries, dead-code detection, conventional commits, co-located tests by rule. Springer's typescript-standards (gts baseline) is the home for this.

Tier 2, template-enforced: generators for the repeating units (screen, component, API route, table plus migration, background job), each emitting code, test, preview, types, and barrel entry. One canonical example per unit type kept green.

Tier 3, prose, short: a folder map, the error handling contract, data flow rules, state placement order, and what not to do. Layered per directory under the CLAUDE.md size rules.

Testing: Vitest co-located, required for model and api. React Native Testing Library for anything with state. Playwright (web) and Maestro (mobile) per user flow from the flow graph. Acceptance criteria map one to one to named tests.

Observability in templates: structured logging with a request id, route-level error boundaries.

Builders receive the task spec, the feature README, the conventions fragment for their package, the nearest existing implementation of the same unit type, and the relevant generator. Not the docs tree.

## Backlog, MVP cut, risk, and merge

### Backlog generation

Derive, do not author. Every task is traceable to a spec artifact.

1. Foundation pass from a template keyed on the stack profile.
2. One epic per user flow.
3. One feature per screen cluster plus cross-cutting concerns.
4. Tasks from a fixed type vocabulary (db-table, api-route, screen, component, job, e2e-flow, integration), each type with a template for its criteria shape and required tests.
5. A dependency graph, cycles flagged.
6. A critic pass by an agent that did not see the decomposition.
7. Human scope review at epic and feature level, and the MVP line.
8. Human spot check of five to ten tasks. A bad sample fixes the template, not the tasks.
9. Topological waves with a WIP limit per package.

The MVP line is proposed from core flows, graph centrality, and cost per feature. Deferred features keep their tasks, tagged deferred, so the graph stays whole. The unknowns list is resolved before wave one. The backlog lives as files in the repo. A tracker is a one-way projection.

### Risk levels

| Level | Meaning | Behavior |
|-------|---------|----------|
| L0 routine | No trigger | Auto-merge on green |
| L1 notable | Minor trigger or a recorded default | Auto-merge on green, digest entry |
| L2 high | Auth, sessions, permissions, tenancy, destructive migration, new dependency or egress, payments, PII, secrets, uploads, conventions or CI changes, an open Critical or High finding | Merge holds for the human, only dependents wait |
| L3 blocked | An unresolved irreversible decision or a missing provisioned input | Does not start until resolved |

Rules are static data, auditable, editable from the L2 queue. Verticals raise a level, never lower it. Bias toward over-tagging early.

### Vertical review

Dispatched by diff, at most two per PR, each with a rubric derived from the stack profile and the declared frameworks. Verdicts are pass, pass-with-notes (L1), or flag (L2) and must cite the rule. "This seems risky" is not a valid output. A periodic whole-repo audit covers cross-PR issues.

On an L2 hold the human sees the task, the finding, the diff, and the builder's response, and can approve, approve with a rule change that updates the policy file, or send back. Rule changes are how autonomy grows without lowering the bar.

## Agentic principles

1. Human effort front-loads into the brief and back-loads into review. A mid-task question is a brief or spec gap, fixed at intake.
2. Name the outcome and the proof, not the steps. Goal, files in scope, executable check.
3. Never let the builder grade itself. A separate skeptical evaluator is tractable, a self-critical generator is not.
4. Make subjective quality gradable with a written rubric.
5. State lives in files, not transcripts. Completion is a property of the artifact.
6. Context is a budget. Short layered instruction files, each task handed only its slice.
7. Grow rules from observed failures. A repeated mistake adds a check, not a paragraph.
8. Separate exploration from execution. A plan file before the build.
9. Isolate parallel agents in worktrees with WIP limits.
10. Simplify the harness by subtraction. Remove a gate and see if quality drops.
11. Verify adversarially. A red-team pass against staging after each wave.
12. Keep the design gates human. Judgment work gets churned by a loop, not improved.

### Why agents stop, and the fix for each

| Cause | Fix |
|-------|-----|
| Spec ambiguity | Unknowns resolved before wave one. A reversible default is taken, logged, tagged L1, and the work continues. An irreversible gap is L3 and never reaches a builder. A question-shaped stop is a classified failure the harness re-dispatches with the default-and-continue instruction |
| Permission prompts | Per-task-type allowlist, worktree isolation |
| Waiting on a merge | The builder ends at "PR open, checks green, risk tag set" and pulls the next task. Dependent work stacks on the open PR. The scheduler prefers merged dependencies, then open-PR dependencies |
| Context depletion | Session equals task, budget per task type, handoff file at a context threshold, fresh session resumes from disk, heavy reads delegated to subagents |

An L2 hold never blocks the agent, only the merge.

## The harness

### Product model

The user knows two commands.

```
springer onboard     once
springer             opens the TUI
```

springer onboard is one guided flow: coding agent provider and auth, source host, backlog projection, notification channels, staging hosts and optional tools, then the daemon is installed and started. springer configure <area> changes one section later. springer doctor validates and repairs.

The TUI has four screens and a chat line.

Projects: a list with status. New, open, archive.

Backlog: the epic, feature, story tree and the WIP board, the dependency graph, the MVP line, and the risk tag per item, editable through typed operations. The out-of-the-box backlog view when no tracker is configured. See Backlog out of the box.

Brief: where the human spends their time. A structured editor for goals, personas, core flows, non-goals, constraints, and attachments. A side panel for profile, deploy, surfaces, and pinned decisions with defaults. The chat line in interview mode asks what a product manager would ask and fills the brief from the answers. Check brief runs the buildability critique inline. Start run is the only commit.

Run: phase, dependency graph, in-flight units with context percent and cost, open gates as cards with the recommended option first and the consequences stated, the L1 digest as a feed, interventions (cancel and re-dispatch at a higher tier on the unit row, pause on the run). A design gate opens the browser on the daemon's localhost page for the mockups and comps, because a terminal cannot show them.

The chat line on every screen is an agent over typed operations on the daemon API, with a confirm step for anything that changes config or scope and an audit log. It cannot do anything a click cannot.

Gate notifications go to channels with numbered options. Replying with a number answers the gate. Anything that needs a diff or a mockup links to the TUI or the localhost page.

### Provider contracts

| Slot | v1 implementation | Later | Contract |
|------|-------------------|-------|----------|
| Coding agent | Claude Code (Agent SDK), plus a mock provider for tests | Codex, Gemini CLI, OpenCode as reviewers through an adapter, builder parity later | spawn(role, brief, allowlist, mcp) returns an event stream, result, cost, usage |
| Source host | GitHub | GitLab, Forgejo | create repo, open PR, post status, merge, retarget stacked branches |
| Backlog | Files in the repo plus the TUI board (the default, not a fallback) | Linear, GitHub Projects, Jira as one-way projections | project stories and states one way |
| Channel | Desktop notification, Slack | Telegram, Discord, email, iMessage | notify(event, payload), answer a gate by reply |
| Staging | Compose over SSH | Vercel preview, Coolify API | deploy(branch) returns a URL, teardown |
| Design tools | Playwright, impeccable, ui-ux-pro-max detected | Claude Design, Figma MCP | wired into the design skills when present |
| Memory | FTS5 | Embeddings | index(records), query(scope) |

Springer's agents and skills do not change per provider. The harness translates. Where a provider lacks something a role needs, the harness degrades and reports it in doctor.

### Architecture

A harness process spawns Agent SDK sessions per unit. Loop logic is code. The model does the judgment steps only. Everything deterministic (tick, rehydrate, barrier, receipts, risk scoring, retries, gate state) moves from skill prose into the service. pdca-harness.md becomes the spec for the rewrite. The agents, skills, schemas, references, and hooks survive unchanged.

The harness owns the run state machine, the scheduler, the dispatcher, check, gates, retrieval, and observability. SDK sessions own every agent and skill. The orchestrator agent shrinks to its judgment core: given the readiness snapshot, name the next units and the gap each closes.

One installed package and one daemon on an always-on box, with a project registry under ~/.springer. The runtime stays per project. SDK sessions run inside the project worktree so they load that project's runtime, CLAUDE.md, and hooks. The run store stays per project under runs/. The harness SQLite is a rebuildable index over every registered project's cycle log, the same relationship run-state.json has to the log today.

Scaffolding impact: project creation gains a register step and the manifest records the minimum harness version. Runtime updates stay as they are. Harness updates are a package upgrade with a compat check at run open. The spgr-run-harness skill becomes a shim calling the daemon. run-unattended.py is retired. Docs rendering, the tracker projection, and the dashboard move to harness features.

Registry: projects (path, profile, deploy, staging host, runtime version), worktrees under ~/.springer/worktrees/<project>/<unit> with a shared pnpm store, secrets in the OS keyring per project (builders get .env.test only), staging mapping (project to host to Compose project name).

Daemon security: localhost bind, token auth, typed operations only from the chat agent, audit log of applied operations.

### Agent SDK usage

CLI tier flags: --output-format json or stream-json, --allowedTools and --permission-mode acceptEdits per task type, --append-system-prompt for the role, --resume for multi-step work, --bare so the harness passes exactly the context it assembled, --json-schema for typed verdicts, --mcp-config per role. SDK tier: structured outputs, tool approval callbacks (the risk classifier inspects each tool call, records L2 or L3 triggers, never pauses the agent), usage per session for the handoff threshold, cost per session for budgets. Slash commands are interactive only, so in print mode the task is described or the skill file is loaded directly.

### Monitoring

Per run: phase, open gates with age, WIP board, graph colored by merged, open, or blocked. Per unit: agent, model, elapsed, context percent, last tool call, cost. Stream-json from each session piped to the run screen. Failure-class mix and the one figure, product checks per 100 dispatches. Spend against the daily cap. Interventions are API calls that write operation_applied events.

### Package layout

```
springer-harness/
  springer_harness/
    state/        cycle log reader, projection, SQLite index
    scheduler/    ready queue, barrier, WIP, worktrees
    dispatch/     contract builder, tier selection, provider runner
    providers/    coding agent, source host, backlog, channel, staging, memory
    check/        schema validate, receipts, classify-failure, review package, pr-risk
    gates/        queue, merge, notifiers
    retrieval/    FTS5 index, corpus builders, brief assembly
    api/          FastAPI, runs, units, gates, events (SSE), interventions, static docs/design
    tui/          Textual app: projects, brief, backlog, run, chat line
    chat/         typed-operation agent over the API
  cli: springer onboard | springer | configure | doctor
```

### Migration path

1. Extract every harness script into an importable library with no session assumptions.
2. Build the mock coding-agent provider and the harness test suite against it.
3. Service tick loop calling those libraries, Claude Code provider, file backlog, desktop and Slack channels, Compose staging.
4. Hooks POST events to the service. TUI run screen reads the service.
5. spgr-notify-human posts to the gate queue. Channels become notifiers.
6. First full run under the service on a small profile project.
7. Delete the in-session loop prose from pdca-harness.md, keep the policy parts. Keep the skill as a shim.

Risks: loss of "open the repo and go" (mitigated by the shim), two sources of truth during migration (the cycle log stays the only durable state), prose-to-code behavior drift (evals catch some, the first real run catches the rest).

### Local CI, staging, and cost

GitHub free tier for PRs and branches through the gh API. Private repositories on the free tier have no branch protection, so the harness is the sole enforcer of merge policy and a direct push to main is logged, not prevented. The harness posts check results as commit statuses. Receipts are the CI signal. Staging is Compose per branch on local Linux boxes with DB per branch from a template database, names resolvable on the LAN. Android emulators run on the Linux boxes for Maestro. iOS simulators need macOS, so a Mac joins the farm or iOS E2E runs on the workstation on demand. A dedicated always-on machine hosts the daemon.

Auth and budget at v1: the Claude Code provider uses the subscription session the CLI is logged into on the daemon machine, not an API key. The Agent SDK drives the CLI, so this is the same auth path run-unattended.py uses today. Consequences the scheduler must handle: the budget is a usage window, not dollars, so the scheduler tracks consumption per window from the provider's usage signal, slows dispatch as a window fills, and sleeps through a limit to the reset the way run-unattended.py already does. Parallel sessions draw from one window, so the WIP limit is also a usage-window decision. Per-session cost is still computed at list price for the TUI and the retrospective, as information rather than a cap. Cheaper tiers for mechanical roles, the strong model for builders and the security and compliance reviewers, which also stretches the window. The API-key path, with a real daily dollar cap, stays implemented behind a provider setting so a project can switch when predictability matters more than price.

## RAG

RAG is for context too big to hand over whole. The task spec, the ADRs for the feature, and the acceptance tests are always handed over whole. If a builder has to retrieve what it is supposed to build, the spec is incomplete.

The harness owns the index, built from runs/ on merge and gate events. Three corpora of structured records: artifacts (PRD sections, ADRs with an affects field, screen specs, design system), findings and rulings per vertical (review findings, verdicts, defaults-ledger lines, escalation outcomes, receipts), and learnings under the existing pin and promote rules.

Builders get artifact hits (ADRs by path, nearest implementation of the same unit type). Reviewers get findings for their vertical scoped to the diff. The orchestrator gets learnings. Nobody gets everything.

Structured fields plus BM25 through SQLite FTS5. Embeddings only if misses are observed. Cross-project is a query flag. Cross-project learnings are cited only when user-stated, cross-project findings are advisory with the source project named. Every dispatch records what was retrieved, so a wrong assumption is first checked against the retrieved set.

## Pragmatic review: gaps, gotchas, improvements

1. Bring-your-own coding agent is constrained by the runtime format. Springer's agents, skills, hooks, and allowlists are Claude Code artifacts. Other agents join first as reviewers through an adapter. The provider contract is designed now, one implementation ships.
2. Two assumption philosophies reconciled. Reversible decisions default and log (L1), irreversible decisions escalate before start (L3). No builder stops to ask.
3. A terminal cannot show a mockup. The daemon serves docs/design on localhost from day one and the TUI opens the browser for design gates.
4. No branch protection on private free-tier repos. The harness is the only merger, and that is enforced in the harness, not on GitHub.
5. iOS needs a Mac. Plan the farm accordingly.
6. Human-provisioned inputs block the skeleton. The provisioning checklist is a first-class artifact emitted at architecture lock.
7. Cost model. Subscription session auth at v1 means the budget is a usage window. The scheduler must read the window, slow down as it fills, and sleep to the reset. Spend is shown at list price as information. An API key with a dollar cap is a later switch, not the default.
8. A mock provider is a prerequisite for building and testing the harness without tokens.
9. The brief is the bottleneck. The chat line's interview mode is the highest-leverage TUI feature.
10. Seed and fixture data generated from packages/types, used by prototype, staging, and E2E.
11. Worktrees in a pnpm monorepo are heavy. Shared store, WIP of two or three, worktree reuse per unit type.
12. Model drift. Re-run the eval suite when a provider's model version changes, pin the result in the run brief.
13. Daemon security posture: localhost, token, keyring, typed operations, audit log.
14. The structure pass and tokens-as-code are placed relative to Springer's one-sitting direction review so they do not fight it: direction and architecture in one sitting, structure notes applied, then tokens.

## Springer gap analysis

Springer already covers most of the workflow, in several places more rigorously than the session's first draft.

Ahead: receipts and the review package, failure classification before retry, profiles and lanes, behavioral evals of agents, the rule budget and the single outcome figure.

Pushed on by this design: a structure pass before IA, the design system emitted as code from the real framework, deployment profile and pinned decisions as first-class brief fields, local-receipts CI, the provisioning checklist, seed data, a retrievable findings corpus, and the harness daemon with the TUI.

## Branch strategy

The work happens on a new branch of the Springer repository, greenfield for the harness and pruned-by-profile for the runtime. The current harness keeps working on main until the new one has completed a real run.

Greenfield applies to the harness only. It is new code with no predecessor worth keeping except the scripts, which are extracted as a library. The runtime (agents, skills, schemas, references, hooks) is the proven part of Springer and is brought over as a unit, not cherry-picked skill by skill. The reachability validator and the catalog budget make one-at-a-time cherry-picking a fight: every skill must be named by an agent, a reference, or a reachable skill. Instead, bring the horizontal agents and the harness-touching skills for the first target profile (small) together, run the validator, and add vertical agents by profile as runs need them. Modify on the way over where the design requires it: spgr-run-harness becomes a shim, spgr-notify-human posts to the daemon, the design agent gains the structure pass, spgr-create-design-system emits code.

The branch restructures the repository into two packages with different distribution shapes, the daemon that installs once and the runtime that is copied into every project.

```
springer/
  harness/            new Python package, springer-harness: daemon, API, TUI, providers
  runtime/            moved: agents, skills, references, hooks, schemas
  templates/          kept: project CLAUDE.md, settings, SKILL and agent templates
  scripts/            kept: validate-repo.py, update-project.py, eval-skills.py, paths adjusted
  evals/ tests/       kept, covering both packages
```

When the branch merges, main is the new shape. The monorepo keeps the validator and the evals covering both packages, which is why it is preferred over a separate harness repository.

Sequence on the branch:

1. Skeleton: harness package layout, runtime move, validator paths updated, CI green on the move alone.
2. State model session, written into runtime references and schemas.
3. Mock provider, API, tick loop against a canned run, tests.
4. TUI: projects, brief editor, backlog board, run screen, chat line stub.
5. Horizontal agents and harness-touching skills for small, modified as listed. Validator green.
6. Claude Code provider on session auth. First real run on a small-profile project.
7. Verticals by profile, then the Phase 1 workflow changes.

Steps 3 and 4 will tempt the TUI to be designed around the mock. The API contract is what both sides agree on, so the real provider slots in at step 6 without touching the TUI.

## Backlog out of the box

With no tracker configured, the backlog is files in the repository plus a board in the TUI, and that is the default rather than a fallback. The run store under runs/ is already the source of truth for stories and their states, and a tracker is only ever a one-way projection of it.

The TUI Backlog screen renders the epic, feature, story hierarchy as a tree and as a board with the WIP columns (ready, in progress, in review, blocked, done), the dependency graph, the MVP line, and the risk tag per item. It is editable where the human is allowed to act: move the MVP line, defer or restore a feature, reorder within a wave, add a bug, answer an unknown, open the PR for an item. Every edit is a typed operation recorded as an operation_applied event, so the board never diverges from the log.

For reading outside the TUI, the harness renders docs/backlog.md at gates (under the existing docs rendering policy) with the same tree, status, and MVP line, so the backlog is reviewable in git and in a pull request.

A tracker (Linear, GitHub Projects, Jira) is an optional projection configured in onboarding. GitHub Projects is available on the free tier and is the cheapest choice when a shared view is wanted, but it adds nothing for a single operator that the TUI board does not already show.

## Build plan

Each change respects the rule budget, ships with a check or eval, and is measured by product checks per 100 dispatches.

Before Phase 0, the state model: done. springer-state-model.md is the reference the build implements, placed at runtime/references/state-model.md with the seven schemas it names under runtime/schemas/. The one rule change it makes to pdca-harness.md, overlapping cycles in place of the batch barrier, is approved and displaces the barrier paragraph.

Phase 0, harness walking skeleton (weeks):

1. Extract harness scripts into a library. Mock coding-agent provider. Test suite.
2. Daemon tick loop, Claude Code provider on subscription session auth with usage-window budgeting, file backlog, GitHub source host, desktop and Slack channels, Compose staging over SSH, localhost static serving of docs/design.
3. TUI: projects, brief editor with the side panel, backlog board, run screen with gates and interventions. Chat line with typed operations.
4. springer onboard and springer doctor.
5. First full run on a small-profile project. Then retire run-unattended.py and shrink pdca-harness.md.

Phase 1, workflow (days, can overlap with phase 0):

6. Brief v1: schemas/brief-v1.json, the product-fact fields with profile derivation, deploy, pinned, frameworks, reach, variants, and the critique rules. run-brief-v1.json gains the new fields. Deploy-profiles reference. Architect treats pinned as given.
7. Structure pass after direction selection with an automated critique first. Displaces the optional prototype step.
8. Provisioning checklist at architecture lock, gating the skeleton.
9. Nearest-implementation and ADR-by-path retrieval in the builder brief.

Phase 2, design as code (weeks):

10. Tokens emitted into packages/ui/tokens, comps rendered from those files, react-native-web on mobile.
11. Seed data skill from packages/types.
12. Local-receipts CI platform, commit statuses through gh, staging target in the brief.
13. High-fidelity variants, opt-in.

Phase 3, memory and providers (ongoing):

14. Per-vertical findings corpus in the harness index, advisory to reviewers.
15. Brief interview mode in the chat line.
16. Additional providers by demand: Linear, Telegram, Vercel preview, reviewer adapters for other coding agents.
17. Web UI when the API is stable, starting with the design review surface.
18. One eval per change.

Deliberately not done: a generic orchestrator, full RAG for builders, a new wireframe phase, builder parity for non-Claude agents in v1, Kubernetes.

## Open items

- Usage-window budgeting: which provider signal exposes window consumption, how the scheduler maps it to a dispatch rate, and the TUI display.
- Brief editor behavior in the TUI: section navigation, inline critique display, and how interview answers are merged into sections the human already edited.
- Task spec template per type with the executable check and allowlist.
- Risk rules as a versioned data file.
- Merge mechanics: stacked retargeting, L0 collisions, rebase policy.
- Staging farm spec: box roles, Compose naming, teardown, smoke coverage, emulator setup, the Mac for iOS.
- Pipeline observability: log locations, cost per task, failure taxonomy, backoff on rate limits.
- Compliance corpora per framework.
- Release and production deploy: promotion criteria, EAS submit, rollback.
- Harness pruning cadence.

## Sources consulted

- Harness design for long-running application development, Anthropic Engineering
- Claude Code best practices, and Run Claude Code programmatically, Claude Code docs
- Agentic engineering, Karpathy, Sequoia Ascent 2026
- OpenClaw onboarding, CLI, and setup-agent documentation
- pbakaus/impeccable and impeccable.style
- Design skills for Claude Code and Cursor reviewed, superdesign.dev
- The best SaaS stack in 2026, MakerKit
- React Native in 2026 stack choices, and React Native monorepo 2026
- Backend as a service in 2026, Cotera
- Claude Design launch coverage and Figma MCP integration notes
