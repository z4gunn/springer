# Project - Springer Agent Rules

This file is the operative ruleset for the AI agents building this application. It loads every session and OVERRIDES default behavior. This project was instantiated from Springer, an AI software development team built as a library of Claude Code agents and skills. The agents in `.claude/agents/` and the skills in `.claude/skills/` drive the full lifecycle, from idea to production, and you the human enter only at deliberate checkpoints.

## How to start

Delegate to the Orchestrator agent (`spgr-agent-orchestrator`), which sequences the phases and routes artifacts between agents, or invoke a specific agent for a specific phase, for example `spgr-agent-discovery` to start research or `spgr-agent-architect` to produce architecture options. Describe the app you want to build and let the team run.

## Core Design Principles

These constraints shape every agent and are non-negotiable.

1. Architecture first. No development begins until you approve the architecture. The Architect agent proposes at least two distinct options with full tradeoffs. It does not select. You select. Once approved, the architecture is an immutable constraint. A developer agent that cannot satisfy a requirement within it escalates rather than deviating.
2. Minimal human-in-the-loop. The only required gates are architecture approval, design-direction selection, pull-request merge, a vertical security or compliance flag, and a scope change. Work between these gates flows agent to agent.
3. Structured artifact contracts. Every handoff is a typed artifact with enumerated required fields, per-section rationale, explicit confidence signals (confirmed, proposed, needs-human-input), and a versioned schema. The receiving agent validates the artifact before acting on it.
4. Escalation is not failure. An agent that refuses to proceed on incomplete or contradictory input, and returns a precise list of what is missing, is doing its job. Agents do not fill gaps with assumptions.
5. Vertical agents are always active. Cross-cutting concerns (auth, security, compliance, observability, performance, accessibility) are not bound to a single phase. A vertical agent operates as a consultant when tagged for a specific question, as an auditor on a scheduled sweep, and as a gate whose sign-off is required before certain artifacts can be marked confirmed.
6. Design agents receive maximum creative latitude. They receive the problem and the personas, not wireframes, and produce multiple distinct directions. You select one direction. The agent then executes that direction with precision.

## Where things live

This project directory is the build target. Source code is written into the project tree at the repository root, and the file-writing tooling refuses to write outside it.

- `runs/<run-id>/` is the artifact store. Each run holds `artifacts/`, `archive/`, `escalations/`, `checkpoints/`, and `consultations/`. Every typed artifact (PRD, ADRs, ERD, test plan, and so on) lives here.
- Application source code, configuration, tests, and CI live in the project tree, the same place any other repo keeps them.
- `schemas/` holds the JSON Schemas that artifacts validate against.
- `.claude/references/` holds the shared cross-skill references, cited by repo-relative path.

## Generated Code Standards

Any JavaScript-runtime stack this project selects MUST be TypeScript. Plain JavaScript is not permitted for new source. All generated TypeScript follows `.claude/references/typescript-standards.md`, the single source of truth for the tooling baseline (gts), compiler strictness, lint rules, and format rules. An agent that cannot satisfy a requirement in TypeScript within the approved architecture escalates rather than falling back to plain JavaScript. Other languages (for example Python, Go, Swift, Kotlin) keep their stack-default tooling and are unaffected by this rule.

## Git conventions

- Use conventional commit messages, scoped by what changed (for example `feat(api): add subscription endpoint`, `chore(ci): add typecheck stage`).
- One logical change per commit. Lint, format, and the type checker pass before every commit.
- Never commit secrets or `.env`.
