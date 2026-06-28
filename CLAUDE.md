# Springer - Agent Rules

This file is the operative ruleset for AI agents working in this repository. It loads every session and OVERRIDES default behavior. For the project overview, motivation, methodology, and the agent and skill catalog written for people, see README.md. This file is the rules, conventions, and procedures an agent needs to build or change an artifact here.

## Overview

Springer is an AI software development team, comprised of a library of Claude Code skills and agents, where each agent models a traditional dev-team role (e.g. product manager, architect, developer, QA, DevOps) and the vertical specialties that span those roles. The team executes the full software lifecycle on any greenfield SaaS or mobile application, from idea to production, and the human enters only at deliberate checkpoints.

This repository holds the build: 27 agents and 197 skills, almost all translated from a Phase 1 spec into one working Claude Code artifact. The Phase 1 specs are the source of truth and live in a private vault (see Spec Source below). When adding or changing an artifact that has a spec, map from its spec rather than inventing. A small number of skills (spgr-render-doc, spgr-render-design-mockups, and spgr-run-harness) are net-new capabilities authored directly to these build standards with no Phase 1 spec. The motivation and methodology behind these rules are in README.md and are not restated here.

## Core Design Principles

This section lists the constraints that shape every agent. These are non-negotiable.

1. Architecture first. No development begins until the human approves the architecture. The Architecture agent proposes at least two distinct options with full tradeoffs. It does not select. The human selects. Once approved, the architecture is an immutable constraint. A developer agent that cannot satisfy a requirement within it escalates rather than deviating.
2. Minimal human-in-the-loop. The only required gates are architecture approval, design-direction selection, PR merge, a vertical security or compliance flag, and a scope change. Work between these gates flows agent to agent.
3. Structured artifact contracts. Every handoff is a typed artifact with enumerated required fields, per-section rationale, explicit confidence signals (i.e. confirmed, proposed, needs-human-input), and a versioned schema. The receiving agent validates the artifact before acting on it.
4. Escalation is not failure. An agent that refuses to proceed on incomplete or contradictory input, and returns a precise list of what is missing, is doing its job. Agents do not fill gaps with assumptions.
5. Vertical agents are always active. Cross-cutting concerns (e.g. auth, security, compliance, observability, performance, accessibility) are not bound to a single phase. A vertical agent operates as a consultant when tagged for a specific question, as an auditor on a scheduled sweep, and as a gate whose sign-off is required before certain artifacts can be marked confirmed.
6. Design agents receive maximum creative latitude. They receive the problem and the personas, not wireframes, and produce multiple distinct directions. The human selects one direction. The agent then executes that direction with precision.

## Repository Layout

This section describes where each kind of file lives.

```
springer/
  README.md              project overview for people (overview, motivation, methodology, agent and skill catalog)
  CLAUDE.md              this file, the operative ruleset for AI, loaded every session
  .claude/
    skills/<name>/SKILL.md   built skills, auto-loaded in this repo
    agents/<name>.md         built agents, auto-loaded in this repo
    references/<name>.md     shared cross-skill references (e.g. diagram-standards), cited by repo-relative path
  templates/             golden starters, build from these and not from a blank file
    SKILL.template.md
    agent.template.md
  schemas/               artifact JSON Schemas, built first (see Build Order)
  runs/                  the run store where a project's artifacts accumulate
```

A repo-level README.md is intentional and is not an auxiliary file in the no-README sense. The no-README rule in Universal Rules below applies inside a skill or agent directory, not at the repository root.

When Springer runs as a project instance, a copy instantiated for one application through `scripts/new-project.sh` (see the README Quickstart), the repository root is that application. The file-writing tooling writes application source code into the project tree and refuses to write outside the repository root, while typed artifacts accumulate in `runs/<run-id>/`. The downstream project receives the runtime (`.claude/skills`, `.claude/agents`, `.claude/references`, `schemas`) and a tailored `CLAUDE.md` from `templates/project-CLAUDE.md`, not this build ruleset.

Spec source (read-only, private): Phase 1 specs live in a private vault, as `skills/spgr-skill-*.md` and `agents/spgr-agent-*.md`, each with a "Phase 2 Build Notes" section that is the build brief for that artifact. The specs are build provenance and are not required to run Springer or to use any built agent or skill. They are not edited from this repository. The one-time build scripts in `.claude/workflows/` read them through the `SPGR_SPEC_DIR` and `SPGR_BUILD_STANDARDS` environment variables, which have no default pointing at any private location.

External skill dependency (optional): The `spgr-render-diagram-excalidraw` skill builds on the third-party `excalidraw-diagram` skill by Cole Medin (https://github.com/coleam00/excalidraw-diagram-skill), expected at `~/.claude/skills/excalidraw-diagram/`. It reuses that skill's color palette, element templates, and render methodology by path. The skill is not vendored here and must be installed separately for render-diagram-excalidraw to run. Every other Springer skill and agent works without it.

External skill dependency (optional): The `spgr-generate-design-directions` and `spgr-create-design-system` skills can draw on the third-party `ui-ux-pro-max-skill` (https://github.com/nextlevelbuilder/ui-ux-pro-max-skill), a catalog of UI styles, color palettes, and font pairings, expected at `~/.claude/skills/ui-ux-pro-max/`. Verify the exact installed directory name on install. The two skills consume the catalog by path as an optional source of candidate styles, palettes, and pairings, then translate every selected value into named design tokens, so no raw hex or font name reaches an artifact. The catalog is not vendored here and must be installed separately. Both skills run fully without it.

## Build Standards

This section defines how to build each skill and agent. Build from the templates in `templates/`. The rules are split by degree of freedom. A hard rule is a shape constraint that a validator can enforce. A guidance rule requires judgment.

### Authoring Voice

All authored prose (skill descriptions, agent system prompts, references, commit messages) follows the Springer technical writing voice. No em-dashes anywhere. Use a regular hyphen, a comma, a period, or restructure the sentence. No semicolons, no body-text bold, no italics, no emojis, no marketing adjectives (e.g. robust, powerful, seamless), and no filler verbs (e.g. leverage, utilize, facilitate). A user-level hook blocks any em-dash written into a documentation file.

### Universal Rules

These rules apply to both skills and agents.

Hard:
1. One artifact has one responsibility. An artifact that does two jobs must be split.
2. The name is lowercase-kebab, globally unique, matches the file or directory, and keeps the spec's `spgr-` prefix (e.g. spec `write-prd` becomes skill `spgr-write-prd`, and spec `spgr-agent-architect` stays `spgr-agent-architect`).
3. No auxiliary files. A skill or agent must not contain a README, a CHANGELOG, or an install or process document. Ship only what the agent needs to do the job.
4. Detail lives in `references/` for skills, or in the prompt body for agents, and must not be duplicated across both.

Guidance:
5. Assume the reader is a capable model. Add only the Springer-specific contract, schema, or procedure that the reader cannot infer. Cut anything that earns its tokens on general knowledge.
6. Map from the spec's "Phase 2 Build Notes" rather than restating the whole spec. The Overview maps to the description and the body introduction. The input and output contract maps to the body Inputs and Outputs. The methodology rules map to the body procedure. The escalation triggers map to the escalation instructions.

### Skill Rules

Hard:
- Frontmatter is comprised of exactly two keys, `name` and `description`. Nothing else.
- The description carries all triggering information, both what the skill does and when to use it. There is no "when to use" section in the body, because the body is not loaded until the skill triggers.
- The body is written in the imperative (e.g. "Produce the artifact", not "This skill will produce the artifact") and must be under 500 lines. Content that approaches that limit moves to `references/`.
- References are one level deep from SKILL.md. A reference file longer than 100 lines opens with a table of contents.
- A `scripts/` file is added only when the same code would be rewritten on each run, or when determinism matters. Test every script by running it. An `assets/` file is added only for files used in the output (e.g. schema files, templates, boilerplate).

### Agent Rules

Hard:
- Required frontmatter is `name` and `description`. The `tools` field must be declared and scoped to least privilege. Omitting it inherits every tool.
- The description is framed for when to delegate, not for what the agent is. The word "proactively" is added only when the agent can opt to invoke itself.
- The body is the system prompt and replaces the default. It must contain the workflow steps, the constraints, the escalation triggers, and the output format.

Guidance:
- Tools follow the role. A review or audit agent is read-only (`Read, Grep, Glob`), with `Bash` added only to run a linter or scanner. A developer agent uses `Read, Edit, Write, Bash, Grep, Glob`.
- The `model` field is omitted (inherit) by default. Use `haiku` for a low-cost read-only research agent, and `opus` for an architecture or judgment-heavy role.
- A subagent cannot spawn a subagent. The Orchestrator is the main agent that delegates, and the sub-roles return summaries. Cross-agent handoffs are encoded as artifact contracts, not as nested agent calls.

### Per-Artifact Checklist

Run this checklist on every artifact before it is committed.
- [ ] Started from a template, not a blank file
- [ ] Name matches the file or directory, lowercase-kebab, `spgr-` prefix, globally unique
- [ ] Skill frontmatter is exactly `name` and `description`. Agent declares `tools` at least privilege
- [ ] Description states what the artifact does and when to use it. Agent description is framed for delegation
- [ ] Body is imperative and single-responsibility. Skill body is under 500 lines
- [ ] Detail is in `references/`, with no duplication, references one level deep
- [ ] No README, CHANGELOG, or process files
- [ ] The spec's contracts, methodology rules, and escalation triggers are all mapped
- [ ] No em-dashes, semicolons, body-text bold, italics, or banned filler words
- [ ] Scripts, if any, are tested by running them

### Generated Code Standards

The rules above govern the artifacts in this repository. This subsection governs the code those artifacts generate for a downstream project.

Hard:
- Any JavaScript-runtime stack a project selects MUST be TypeScript. Plain JavaScript is not permitted for new source. All generated TypeScript follows `.claude/references/typescript-standards.md`, the single source of truth for the tooling baseline (gts), compiler strictness, lint rules, and format rules. An agent that cannot satisfy a requirement in TypeScript within the approved architecture escalates rather than falling back to plain JavaScript. Other languages (e.g. Python, Go, Swift, Kotlin) keep their stack-default tooling and are unaffected by this rule.

## Build Order

This section gives the order of work. Each item is a prerequisite for the next.

1. Artifact schemas (`schemas/`). These define the typed output for every handoff. Build them before any agent prompts, because everything else validates against them.
2. Orchestrator agent. This agent routes artifacts, tracks WIP, and manages the escalation queue.
3. PM and Architecture agents. These sit at the top of the funnel. Validate the full architecture checkpoint flow (PM to Architecture to human approval to approved architecture) before any developer agents.
4. Architecture-gate verticals: Auth, Security, and Compliance. Wire these as consultants and gates before the architecture checkpoint is operational.
5. QA agent. Build this before any developer agents, because test-first is non-negotiable.
6. Developer agents. Backend first, then frontend and mobile. Validate the QA to developer to reviewer to PR flow.
7. DevOps agent. Wire in CI/CD and deployment once the developer flow works.
8. Design agent. This can run in parallel with the developer agents after architecture approval.
9. Second-wave universal verticals. Performance and Resilience first, then Analytics and accessibility, then Feature Flag and API Design.
10. Project-specific verticals. Billing and Multi-tenancy for SaaS, App Store for mobile, and i18n when global reach is a stated goal.

## Git Conventions

This section states the commit and branch rules.

- Commit directly to `main`. Push after a unit of work is complete. A branch and PR are opt-in. This rule governs maintaining the Springer repository itself. Applications Springer builds follow the trunk-based pull-request workflow in `.claude/references/git-workflow.md`, where `main` is protected and every change lands through a reviewed PR.
- Use conventional commit messages, scoped by what changed (e.g. `feat(agent): build spgr-agent-architect`, `feat(skill): build spgr-write-prd`, `chore(schemas): add prd schema`).
- Never commit secrets or `.env`.
- The full project roadmap and the methodology research that motivates it live in a private vault and are not required to work in this repository.
