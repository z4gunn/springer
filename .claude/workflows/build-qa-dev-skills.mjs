export const meta = {
  name: 'build-qa-dev-skills',
  description: 'Fan out builder subagents to author the QA, development, mobile, and review SPGR skills from their Phase 1 specs',
  phases: [
    { title: 'Testing skills' },
    { title: 'Development skills' },
    { title: 'Mobile skills' },
    { title: 'Review skills' },
  ],
}

const SPEC_DIR = process.env.SPGR_SPEC_DIR ?? 'specs/skills'
const OUT_DIR = '.claude/skills'
const TEMPLATE = 'templates/SKILL.template.md'
const STANDARDS = process.env.SPGR_BUILD_STANDARDS ?? 'specs/BUILD-STANDARDS.md'

const TESTING = [
  'write-test-plan', 'write-acceptance-test', 'write-unit-test', 'write-integration-test',
  'write-e2e-test', 'write-load-test', 'run-tests', 'write-bug-report', 'run-accessibility-audit',
  'run-security-scan', 'run-smoke-test', 'write-uat-report', 'write-contract-test',
  'write-fixture-factory', 'detect-test-flakiness',
]
const DEVELOPMENT = [
  'implement-feature', 'implement-api-endpoint', 'implement-state-management', 'write-component',
  'write-migration', 'write-seed-data', 'format-code', 'lint-code', 'refactor', 'scaffold-project',
  'scaffold-service', 'scaffold-feature', 'scaffold-background-job', 'scaffold-webhook-delivery',
  'scaffold-transactional-email', 'diagnose-error', 'validate-migration-safety', 'git-commit',
  'create-branch', 'create-pr', 'write-dockerfile', 'generate-env-template', 'validate-env-config',
  'search-codebase',
]
const MOBILE = [
  'configure-deep-linking', 'configure-push-notifications', 'write-platform-permissions',
  'write-mobile-build-pipeline',
]
const REVIEW = [
  'review-pr', 'check-architecture-compliance', 'check-xp-compliance', 'check-style-compliance',
  'generate-docstrings', 'audit-doc-coverage',
]

const REPORT_SCHEMA = {
  type: 'object',
  required: ['skill_name', 'file_path', 'frontmatter_ok', 'voice_ok', 'under_500_lines', 'maps_escalation', 'notes'],
  additionalProperties: false,
  properties: {
    skill_name: { type: 'string' },
    file_path: { type: 'string' },
    frontmatter_ok: { type: 'boolean', description: 'frontmatter is exactly name and description' },
    voice_ok: { type: 'boolean', description: 'no em-dash, semicolon, body bold/italic, emoji, or banned filler (leverage/utilize/facilitate/robust/powerful/seamless)' },
    under_500_lines: { type: 'boolean' },
    maps_escalation: { type: 'boolean', description: 'spec escalation triggers and methodology rules are reflected in the body' },
    notes: { type: 'string', description: 'one line on the output type (envelope artifact vs source code) and any schema deferral' },
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
- Map the spec's Inputs/Outputs, Implementation Notes, methodology rules, and any escalation triggers into the body. The Procedure must include the validation or escalation step.
- AUTHORING VOICE (a hook blocks em-dashes in markdown, so do not write them): no em-dashes (use a comma, period, or regular hyphen), no semicolons, no body-text bold or italics, no emojis, no marketing adjectives (robust, powerful, seamless), no filler verbs (leverage, utilize, facilitate). Do not write the word "leverage" in any form.
- No README, CHANGELOG, or process files. Only the single SKILL.md. Keep everything in SKILL.md; add references/ only if truly needed (one level deep, TOC if over 100 lines).

SPRINGER CONTRACT CONTEXT:
- This skill is called by the QA, developer, or code-reviewer agents. The artifact-plumbing skills already exist and must be referenced by name where the spec implies them: spgr-read-file, spgr-write-file, spgr-read-artifact, spgr-write-artifact, spgr-validate-artifact, spgr-version-artifact, spgr-log-decision, spgr-escalate, spgr-notify-human, spgr-tag-vertical-agent. Other already-built skills you may reference by name include spgr-write-acceptance-criteria and spgr-run-tests.
- The schema registry is at schemas/ with one JSON Schema per artifact type. Reference the registry through spgr-validate-artifact rather than inlining field lists.
- TWO KINDS OF OUTPUT. (1) Some skills produce an ENVELOPE ARTIFACT with a registered schema: test-plan, bug-report, uat-report, code-review, pull-request (plus prd, nfr, user-story, acceptance-criteria, architecture-options, adr, architecture-decision, erd, tech-stack-decision, data-dictionary, system-diagram, infrastructure-diagram, escalation, hil-checkpoint, consultation). For these, write via spgr-write-artifact with inline spgr-validate-artifact. (2) Most development and testing skills produce SOURCE CODE (test files, components, migrations, scaffolds, config). For these, write files via spgr-write-file, and say in one Notes line that the output is source code verified by spgr-run-tests and CI rather than by an envelope schema. If a skill produces an artifact type not in the registered list above (for example a smoke-test result, a flakiness report, a doc-coverage report, or an OpenAPI spec), note that it is written via spgr-write-artifact with its registered schema added in a later increment.
- XP discipline is central to this increment: test-first (failing test before implementation), YAGNI (build only what the acceptance criteria specify), one logical change per commit, lint and format clean before commit. Reflect the spec's specific rules, do not generically restate XP.

After writing, return the structured report. Set the booleans to true only if you verified each by re-reading your file.`
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

phase('Testing skills')
const testing = await buildBatch(TESTING, 'Testing skills')
phase('Development skills')
const dev = await buildBatch(DEVELOPMENT, 'Development skills')
phase('Mobile skills')
const mobile = await buildBatch(MOBILE, 'Mobile skills')
phase('Review skills')
const review = await buildBatch(REVIEW, 'Review skills')

const all = [...testing, ...dev, ...mobile, ...review].filter(Boolean)
const total = TESTING.length + DEVELOPMENT.length + MOBILE.length + REVIEW.length
const failed = all.filter((r) => !(r.frontmatter_ok && r.voice_ok && r.under_500_lines && r.maps_escalation))
log(`built ${all.length}/${total} skills, ${failed.length} self-reported issues`)
return { built: all.length, total, failed, reports: all }
