export const meta = {
  name: 'build-authoring-skills',
  description: 'Fan out builder subagents to author the 23 PM, architect, and gate-vertical SPGR skills from their Phase 1 specs',
  phases: [
    { title: 'PM skills' },
    { title: 'Architect skills' },
    { title: 'Gate-vertical skills' },
  ],
}

const SPEC_DIR = process.env.SPGR_SPEC_DIR ?? 'specs/skills'
const OUT_DIR = '.claude/skills'
const TEMPLATE = 'templates/SKILL.template.md'
const STANDARDS = process.env.SPGR_BUILD_STANDARDS ?? 'specs/BUILD-STANDARDS.md'

const PM = [
  'write-prd', 'write-nfr', 'write-user-story', 'write-acceptance-criteria',
  'prioritize-backlog', 'scope-mvp', 'write-definition-of-done',
]
const ARCHITECT = [
  'generate-architecture-options', 'write-adr', 'generate-erd', 'write-api-spec',
  'generate-system-diagram', 'write-tech-stack-decision', 'write-infrastructure-diagram',
  'write-data-dictionary',
]
const VERTICAL = [
  'design-auth-model', 'write-auth-flow', 'write-rbac-policy',
  'write-threat-model', 'write-security-findings',
  'assess-compliance-scope', 'classify-data', 'write-retention-policy',
]

const REPORT_SCHEMA = {
  type: 'object',
  required: ['skill_name', 'file_path', 'frontmatter_ok', 'voice_ok', 'under_500_lines', 'maps_escalation', 'notes'],
  additionalProperties: false,
  properties: {
    skill_name: { type: 'string' },
    file_path: { type: 'string' },
    frontmatter_ok: { type: 'boolean', description: 'frontmatter is exactly name and description' },
    voice_ok: { type: 'boolean', description: 'no em-dash, semicolon, body bold/italic, emoji, or banned filler' },
    under_500_lines: { type: 'boolean' },
    maps_escalation: { type: 'boolean', description: 'spec escalation triggers and methodology rules are reflected in the body' },
    notes: { type: 'string', description: 'one line on the schema type produced and any deferral' },
  },
}

function prompt(name) {
  return `Build one SPGR skill from its Phase 1 spec. This is a file-authoring task. Produce exactly one file.

SPEC (source of truth, read it fully): ${SPEC_DIR}/spgr-skill-${name}.md
Use its "Phase 2 Build Notes" section as the build brief.

GOLDEN TEMPLATE (copy this shape, fill it in, delete all template comments): ${TEMPLATE}
BUILD STANDARDS (authoritative, read the Skills section): ${STANDARDS}

WRITE THE FILE TO: ${OUT_DIR}/spgr-${name}/SKILL.md

HARD RULES:
- Frontmatter is EXACTLY two keys: name and description. name must be "spgr-${name}". The description carries both what the skill produces and when to use it (there is no "when to use" section in the body).
- Body is imperative, single-responsibility, and under 500 lines. Use the template sections: # ${name}, ## Purpose, ## Inputs, ## Outputs, ## Procedure, ## Notes.
- Map the spec's Inputs/Outputs, Implementation Notes, methodology rules, and any escalation triggers into the body. Procedure steps must include the validation or escalation step.
- AUTHORING VOICE (a hook blocks em-dashes in markdown, so do not write them): no em-dashes (use a comma, period, or regular hyphen), no semicolons, no body-text bold or italics, no emojis, no marketing adjectives (robust, powerful, seamless), no filler verbs (leverage, utilize, facilitate).
- No README, CHANGELOG, or process files. Only the single SKILL.md. Push overflow detail to references/ only if truly needed (one level deep, TOC if over 100 lines); prefer to keep everything in SKILL.md for these skills.

SPRINGER CONTRACT CONTEXT:
- This skill is called by agents. Artifact production goes through the plumbing skills already built: spgr-write-artifact, spgr-read-artifact, spgr-validate-artifact, spgr-version-artifact, spgr-log-decision, spgr-escalate, spgr-notify-human, spgr-tag-vertical-agent. Reference these by name in the Procedure where the spec implies them, rather than re-describing artifact mechanics.
- The schema registry is at schemas/ with one JSON Schema per artifact type. Reference the registry through spgr-validate-artifact rather than inlining field lists. Registered types include: prd, nfr, user-story, acceptance-criteria, architecture-options, adr, architecture-decision, erd, tech-stack-decision, data-dictionary, system-diagram, infrastructure-diagram, escalation, hil-checkpoint, consultation. If this skill's output type is NOT in that list (for example a prioritized backlog, an MVP scope, a definition of done, an OpenAPI api-spec, or a vertical artifact like auth-model or threat-model), say in one Notes line that the artifact is written via spgr-write-artifact and its registered schema is added in a later build increment. The api-spec is OpenAPI 3.1 YAML validated by OpenAPI tooling, not by an envelope schema.

After writing, return the structured report. Set frontmatter_ok, voice_ok, under_500_lines, and maps_escalation to true only if you verified each by re-reading your file.`
}

async function buildBatch(names, phase) {
  return parallel(names.map((name) => () =>
    agent(prompt(name), {
      label: `build:spgr-${name}`,
      phase,
      schema: REPORT_SCHEMA,
      agentType: 'general-purpose',
    })
  ))
}

phase('PM skills')
const pm = await buildBatch(PM, 'PM skills')
phase('Architect skills')
const arch = await buildBatch(ARCHITECT, 'Architect skills')
phase('Gate-vertical skills')
const vert = await buildBatch(VERTICAL, 'Gate-vertical skills')

const all = [...pm, ...arch, ...vert].filter(Boolean)
const failed = all.filter((r) => !(r.frontmatter_ok && r.voice_ok && r.under_500_lines && r.maps_escalation))
log(`built ${all.length}/23 skills, ${failed.length} self-reported issues`)
return { built: all.length, total: 23, failed, reports: all }
