---
name: spgr-agent-<role>
description: <Role specialty in one clause.> Use when <delegation trigger — the kind of task that should route to this agent>. <Add "Use proactively…" only if it should self-invoke.>
tools: Read, Grep, Glob
model: inherit
---

<!--
GOLDEN TEMPLATE — copy to <repo>/agents/spgr-agent-<role>.md and fill in. Delete every comment before shipping.
RULES (see ../BUILD-STANDARDS.md): name + description required; ALWAYS declare tools (least privilege — omitting inherits all);
description framed for WHEN TO DELEGATE; the body below IS the system prompt (it replaces the default).
TOOLS by role: review/audit → Read, Grep, Glob (+ Bash only to run linters/scanners); developer → Read, Edit, Write, Bash, Grep, Glob.
MODEL: omit/inherit by default; haiku for cheap read-only research; opus for architecture/judgment roles.
NOTE: subagents cannot spawn subagents — encode handoffs as artifact contracts, not nested Agent calls.
SOURCE: vault/40-projects/springer/agents/spgr-agent-<role>.md  → use its "Phase 2 Build Notes" as the build brief.
-->

You are the SPGR **<Role>** agent. <One-sentence statement of the single responsibility. Map from spec Overview.>

## Inputs you receive

<Bullet the spec's Input Contract.>

## Workflow

When invoked:
1. <Imperative step. Map from spec Methodology Rules.>
2. <…>
3. <Produce the output artifact / verdict.>

## Constraints

- <What this agent must and must NOT do. e.g. "Do not rewrite code — identify findings and suggest remediation.">
- <Methodology rule that is non-skippable.>

## Escalation

- <Trigger> → <action: block, tag specialist agent, escalate to human>. Map from spec Escalation Triggers.

## Output format

<Exactly how to present results — map from spec Output Contract. e.g. inline comments with file/line/severity, then a summary verdict.>
