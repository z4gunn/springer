---
name: spgr-<verb-noun>
description: <What the skill produces, in one clause.> Use when <concrete trigger scenario, the situation or request that should invoke this skill>. <Optional second trigger.>
---

<!--
GOLDEN TEMPLATE. Copy to .claude/skills/spgr-<verb-noun>/SKILL.md and fill in. Delete every comment before shipping.
RULES (see ../CLAUDE.md Build Standards): frontmatter is EXACTLY name + description. Body imperative and <500 lines.
All "when to use" lives in description, never here. Push detail to references/. No README/CHANGELOG.
SOURCE: vault/40-projects/archive/springer/skills/spgr-skill-<name>.md  → use its "Phase 2 Build Notes" as the build brief.
-->

# <verb-noun>

## Purpose

<One short paragraph: the SPGR-specific job this skill does and why the contract matters. Assume general competence. Only add what's non-obvious. Map from spec Overview/Purpose.>

## Inputs

| Field | Description |
|-------|-------------|
| `<field>` | <from spec Primary Input> |

## Outputs

| Artifact | Description |
|----------|-------------|
| `<artifact>` | <from spec Primary Output> |

## Procedure

1. <Imperative step. Map from spec Implementation Notes / Phase 2 Build Notes.>
2. <…>
3. <Validation / escalation step, what to do on failure.>

## Notes

- <SPGR contract rule, schema reference, or constraint. Reference the schema registry instead of inlining field lists.>

<!--
OPTIONAL bundled resources (delete the headers you don't use):
- scripts/   add when the same code would be rewritten each run or determinism matters. Test by running it.
- references/ add for detail that would bloat this file. Keep one level deep. TOC any file >100 lines.
- assets/    add only for files used IN the output (schema files, templates, boilerplate).
Reference each from the body and say WHEN to read it, e.g.:
  For the full artifact schema, see [references/schema.md](references/schema.md).
-->
