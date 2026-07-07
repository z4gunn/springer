# Springer - Agent Rules

This file is the operative ruleset for AI agents working in this repository. It loads every session and OVERRIDES default behavior. The project overview, motivation, methodology, and the agent and skill catalog written for people are in README.md.

## Overview

Springer is an AI software development team built as a library of Claude Code skills and agents. Each agent models a traditional dev-team role (product manager, architect, developer, QA, DevOps) or a vertical specialty that spans those roles. The team executes the full lifecycle on a greenfield SaaS or mobile application, from idea to production, and the human enters only at deliberate checkpoints.

This repository holds the build: 27 agents and 197 skills, almost all mapped from Phase 1 specs that live in a private vault (see Spec Source below). When adding or changing an artifact that has a spec, map from the spec rather than inventing. spgr-render-doc, spgr-render-design-mockups, and spgr-run-harness are net-new capabilities with no Phase 1 spec, authored directly to these build standards.

## Core Design Principles

These constraints shape every agent and are non-negotiable.

1. Architecture first. No development begins until the human approves the architecture. The Architecture agent proposes at least two distinct options with full tradeoffs and does not select. Once approved, the architecture is an immutable constraint. A developer agent that cannot satisfy a requirement within it escalates rather than deviating.
2. Minimal human-in-the-loop. The only required gates are architecture approval, design-direction selection, PR merge, a vertical security or compliance flag, and a scope change. Work between these gates flows agent to agent.
3. Structured artifact contracts. Every handoff is a typed artifact with enumerated required fields, per-section rationale, explicit confidence signals (confirmed, proposed, needs-human-input), and a versioned schema. The receiving agent validates the artifact before acting on it.
4. Escalation is not failure. An agent that refuses to proceed on incomplete or contradictory input, and returns a precise list of what is missing, is doing its job. Agents do not fill gaps with assumptions.
5. Vertical agents are always active. Cross-cutting concerns (auth, security, compliance, observability, performance, accessibility) are not bound to a single phase. A vertical agent operates as a consultant when tagged, as an auditor on a scheduled sweep, and as a gate whose sign-off is required before certain artifacts can be marked confirmed.
6. Design agents receive maximum creative latitude. They receive the problem and the personas, not wireframes, and produce multiple distinct directions. The human selects one direction, and the agent executes it with precision.

## Repository Layout

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

A repo-level README.md is intentional. The no-README rule in Universal Rules below applies inside a skill or agent directory, not at the repository root.

When Springer runs as a project instance, a copy instantiated for one application through `scripts/new-project.sh`, the repository root is that application. The file-writing tooling writes application source into the project tree and refuses to write outside the repository root, while typed artifacts accumulate in `runs/<run-id>/`. The instance receives the runtime (`.claude/skills`, `.claude/agents`, `.claude/references`, `schemas`) and a tailored `CLAUDE.md` from `templates/project-CLAUDE.md`, not this build ruleset.

Spec source (read-only, private): Phase 1 specs live in a private vault as `skills/spgr-skill-*.md` and `agents/spgr-agent-*.md`, each with a "Phase 2 Build Notes" section that is the build brief for that artifact. The specs are build provenance, are not required to run Springer, and are never edited from this repository. Build scripts read them through the `SPGR_SPEC_DIR` and `SPGR_BUILD_STANDARDS` environment variables, which have no default pointing at any private location.

External skill dependencies (optional, not vendored): `spgr-render-diagram-excalidraw` builds on the third-party `excalidraw-diagram` skill by Cole Medin (https://github.com/coleam00/excalidraw-diagram-skill), expected at `~/.claude/skills/excalidraw-diagram/`, and does not run without it. `spgr-generate-design-directions` and `spgr-create-design-system` can draw candidate styles, palettes, and font pairings from `ui-ux-pro-max-skill` (https://github.com/nextlevelbuilder/ui-ux-pro-max-skill), expected at `~/.claude/skills/ui-ux-pro-max/` (verify the installed directory name), translating every selected value into named design tokens so no raw hex or font name reaches an artifact, and both run fully without it. Every other Springer skill and agent works with neither installed.

## Build Standards

Build from the templates in `templates/`. A hard rule is a shape constraint that a validator can enforce. A guidance rule requires judgment.

### Authoring Voice

All authored prose (skill descriptions, agent system prompts, references, commit messages) follows the Springer technical writing voice. No em-dashes anywhere, use a regular hyphen, a comma, a period, or restructure the sentence. No semicolons, no body-text bold, no italics, no emojis, no marketing adjectives (e.g. robust, powerful, seamless), and no filler verbs (e.g. leverage, utilize, facilitate). A user-level hook blocks any em-dash written into a documentation file.

### Universal Rules

These rules apply to both skills and agents.

Hard:
1. One artifact has one responsibility. An artifact that does two jobs must be split.
2. The name is lowercase-kebab, globally unique, matches the file or directory, and keeps the spec's `spgr-` prefix (e.g. spec `write-prd` becomes skill `spgr-write-prd`).
3. No auxiliary files. A skill or agent must not contain a README, a CHANGELOG, or an install or process document. Ship only what the agent needs to do the job.
4. Detail lives in `references/` for skills, or in the prompt body for agents, and must not be duplicated across both. Agent workflow steps invoke skills by name and do not restate the procedure detail the skill body carries.

Guidance:
5. Assume the reader is a capable model. Add only the Springer-specific contract, schema, or procedure that the reader cannot infer. Cut anything that earns its tokens on general knowledge.
6. Map from the spec's "Phase 2 Build Notes" rather than restating the whole spec. The Overview maps to the description and the body introduction. The input and output contract maps to the body Inputs and Outputs. The methodology rules map to the body procedure. The escalation triggers map to the escalation instructions.

### Skill Rules

Hard:
- Frontmatter is comprised of exactly two keys, `name` and `description`. Nothing else.
- The description carries all triggering information, both what the skill does and when to use it. There is no "when to use" section in the body, because the body is not loaded until the skill triggers.
- The description targets 300 characters with a hard cap of 350. Every description loads into every session, so it states what the skill produces and when to invoke it. The output contract, per-field detail, and verdict conditions live in the body.
- The body is written in the imperative (e.g. "Produce the artifact", not "This skill will produce the artifact") and must be under 500 lines. Content that approaches that limit moves to `references/`.
- References are one level deep from SKILL.md. A reference file longer than 100 lines opens with a table of contents.
- A `scripts/` file is added only when the same code would be rewritten on each run, or when determinism matters. Test every script by running it. An `assets/` file is added only for files used in the output (e.g. schema files, templates, boilerplate).

### Agent Rules

Hard:
- Required frontmatter is `name` and `description`. The `tools` field must be declared and scoped to least privilege. Omitting it inherits every tool.
- The description is framed for when to delegate, not for what the agent is. The word "proactively" is added only when the agent can opt to invoke itself.
- The body is the system prompt and replaces the default. It must contain the workflow steps, the constraints, the escalation triggers, and the output format.
- The body states, directly after the intro, that a skill name resolves to `.claude/skills/<name>/SKILL.md` and is read before the step it governs, because subagents carry no skill catalog.

Guidance:
- Tools follow the role. A review or audit agent is read-only (`Read, Grep, Glob`), with `Bash` added only to run a linter or scanner. A developer agent uses `Read, Edit, Write, Bash, Grep, Glob`.
- The `model` field is omitted (inherit) by default. Use `haiku` for a low-cost read-only research agent, and `opus` for an architecture or judgment-heavy role.
- A subagent cannot spawn a subagent. The Orchestrator is the main agent that delegates, and the sub-roles return summaries. Cross-agent handoffs are encoded as artifact contracts, not as nested agent calls.

### Per-Artifact Checklist

Run this checklist on every artifact before it is committed.
- [ ] Started from a template, not a blank file
- [ ] Name matches the file or directory, lowercase-kebab, `spgr-` prefix, globally unique
- [ ] Skill frontmatter is exactly `name` and `description`. Agent declares `tools` at least privilege
- [ ] Description states what the artifact does and when to use it, within the length cap. Agent description is framed for delegation
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

Each item is a prerequisite for the next.

1. Artifact schemas (`schemas/`), the typed output for every handoff. Everything else validates against them.
2. Orchestrator agent, which routes artifacts, tracks WIP, and manages the escalation queue.
3. PM and Architecture agents. Validate the full architecture checkpoint flow (PM to Architecture to human approval) before any developer agents.
4. Architecture-gate verticals: Auth, Security, and Compliance, wired as consultants and gates before the architecture checkpoint is operational.
5. QA agent, before any developer agents, because test-first is non-negotiable.
6. Developer agents, backend first, then frontend and mobile. Validate the QA to developer to reviewer to PR flow.
7. DevOps agent, once the developer flow works.
8. Design agent, which can run in parallel with the developer agents after architecture approval.
9. Second-wave universal verticals: Performance and Resilience first, then Analytics and Accessibility, then Feature Flag and API Design.
10. Project-specific verticals: Billing and Multi-tenancy for SaaS, App Store for mobile, and i18n when global reach is a stated goal.

## Git Conventions

- Commit directly to `main`. Push after a unit of work is complete. A branch and PR are opt-in. This governs maintaining the Springer repository itself. Applications Springer builds follow the trunk-based pull-request workflow in `.claude/references/git-workflow.md`, where `main` is protected and every change lands through a reviewed PR.
- Use conventional commit messages, scoped by what changed (e.g. `feat(agent): build spgr-agent-architect`, `chore(schemas): add prd schema`).
- Never commit secrets or `.env`.
- The full project roadmap and the methodology research that motivates it live in a private vault and are not required to work in this repository.
