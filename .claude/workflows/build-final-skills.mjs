export const meta = {
  name: 'build-final-skills',
  description: 'Fan out builder subagents to author the final 42 SPGR skills (discovery/research, design, devops, and deferred security/compliance/architect/PM skills)',
  phases: [
    { title: 'Discovery and research' },
    { title: 'Design' },
    { title: 'DevOps' },
    { title: 'Deferred security, compliance, and misc' },
  ],
}

const SPEC_DIR = process.env.SPGR_SPEC_DIR ?? 'specs/skills'
const OUT_DIR = '.claude/skills'
const TEMPLATE = 'templates/SKILL.template.md'
const STANDARDS = process.env.SPGR_BUILD_STANDARDS ?? 'specs/BUILD-STANDARDS.md'

const DISCOVERY = [
  'search-web', 'competitive-analysis', 'build-icp', 'build-persona', 'market-sizing',
  'mine-ugc-forums', 'mine-app-store-reviews', 'mine-social-media', 'mine-review-platforms',
  'synthesize-painpoints', 'go-no-go',
]
const DESIGN = [
  'generate-design-directions', 'write-ia', 'create-wireframes', 'create-design-system',
  'create-screen-specs', 'write-interaction-spec', 'create-prototype',
]
const DEVOPS = [
  'write-ci-pipeline', 'write-cd-pipeline', 'write-iac', 'write-deployment-runbook', 'write-rollback-plan',
  'provision-environment', 'run-deployment', 'bump-version', 'create-release-tag', 'publish-package',
  'write-release-checklist', 'validate-release-readiness', 'scaffold-local-dev-env', 'resolve-merge-conflict',
  'generate-sbom', 'run-dast', 'run-dependency-audit',
]
const DEFERRED = [
  'audit-auth-implementation', 'check-license-compliance', 'run-sast', 'detect-schema-drift',
  'write-audit-trail-spec', 'write-risk-register', 'run-compliance-audit',
]

const REPORT_SCHEMA = {
  type: 'object',
  required: ['skill_name', 'file_path', 'frontmatter_ok', 'voice_ok', 'under_500_lines', 'maps_escalation', 'notes'],
  additionalProperties: false,
  properties: {
    skill_name: { type: 'string' },
    file_path: { type: 'string' },
    frontmatter_ok: { type: 'boolean' },
    voice_ok: { type: 'boolean', description: 'no em-dash, semicolon, body bold/italic, emoji, or banned filler (leverage/utilize/facilitate/robust/powerful/seamless, in any form including hyphenated like high-leverage)' },
    under_500_lines: { type: 'boolean' },
    maps_escalation: { type: 'boolean' },
    notes: { type: 'string', description: 'one line on output type (envelope artifact, report, or source/config) and validation mode' },
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
- Frontmatter is EXACTLY two keys: name and description. name must be "spgr-${name}". The description carries both what the skill produces and when to use it (no "when to use" section in the body).
- Body is imperative, single-responsibility, under 500 lines. Sections: # ${name}, ## Purpose, ## Inputs, ## Outputs, ## Procedure, ## Notes.
- Map the spec's Inputs/Outputs, Implementation Notes, methodology rules, and escalation triggers. The Procedure must include the validation or escalation step.
- AUTHORING VOICE (a hook blocks em-dashes in markdown): no em-dashes (use a comma, period, or regular hyphen), no semicolons, no body-text bold or italics (** and _ for emphasis are banned; backticked code and glob patterns are fine), no emojis, no marketing adjectives (robust, powerful, seamless), no filler verbs. Never write "leverage" or "utilize" in any form, including hyphenated compounds like "high-leverage".
- No README, CHANGELOG, or process files. Only the single SKILL.md. Keep everything in SKILL.md; add references/ only if truly needed (one level deep, TOC if over 100 lines).

SPRINGER CONTRACT CONTEXT:
- Reference the artifact-plumbing skills by name where the spec implies them: spgr-read-file, spgr-write-file, spgr-read-artifact, spgr-write-artifact, spgr-validate-artifact, spgr-version-artifact, spgr-log-decision, spgr-escalate, spgr-notify-human, spgr-tag-vertical-agent.
- OUTPUT TYPES. (1) ENVELOPE ARTIFACT (a spec, plan, report, or recommendation, for example icp, go-no-go, design-directions, design-system, ci-pipeline as a documented artifact, risk-register, audit-trail-spec, security/compliance audit reports): write via spgr-write-artifact with inline spgr-validate-artifact. (2) SOURCE OR CONFIG output (pipeline YAML, IaC, Dockerfiles, local dev scaffold, mining scripts, generated SBOM file): write files via spgr-write-file, verified by run-tests or CI.
- VALIDATION MODE: most of these artifact types have no registered content schema yet. That is expected. spgr-validate-artifact falls back to envelope-only validation for unregistered types (it still checks the header, confidence map, decision log, and version). So still call spgr-validate-artifact, and add one Notes line stating the output type and that envelope-only validation applies until a content schema is registered. Registered content-schema types are: prd, nfr, user-story, acceptance-criteria, architecture-options, adr, architecture-decision, erd, tech-stack-decision, data-dictionary, system-diagram, infrastructure-diagram, escalation, hil-checkpoint, consultation, test-plan, bug-report, uat-report, code-review, pull-request.
- Discovery and research skills (search-web, competitive-analysis, market-sizing, mine-*) require web access and source citations: every factual claim carries a source. Pain signals need two distinct source categories before being treated as validated. These skills run as part of Phase 1, where no code is written.
- Design skills produce structured specs (directions, IA, wireframes, design system tokens, per-screen specs with all five states, interaction spec, prototype) as markdown artifacts, token-based with no hardcoded style values.
- DevOps skills enforce: no literal secrets in any pipeline or IaC, the ten-minute build rule, tested rollback before a deploy is valid, and semantic versioning. Map these where the spec states them.
- Security and audit skills (run-sast, run-dast, run-dependency-audit, check-license-compliance, generate-sbom, audit-auth-implementation, run-compliance-audit, detect-schema-drift) run scanners and produce findings reports with severity and a blocking gate verdict. Map the spec's exact thresholds.
- Reflect the spec's specific methodology rules. Do not generically restate the domain.

After writing, return the structured report. Set the booleans to true only if you verified each by re-reading your file.`
}

async function buildBatch(names, phaseTitle) {
  return parallel(names.map((name) => () =>
    agent(prompt(name), { label: `build:spgr-${name}`, phase: phaseTitle, schema: REPORT_SCHEMA, agentType: 'general-purpose' })
  ))
}

phase('Discovery and research')
const disc = await buildBatch(DISCOVERY, 'Discovery and research')
phase('Design')
const des = await buildBatch(DESIGN, 'Design')
phase('DevOps')
const ops = await buildBatch(DEVOPS, 'DevOps')
phase('Deferred security, compliance, and misc')
const def = await buildBatch(DEFERRED, 'Deferred security, compliance, and misc')

const all = [...disc, ...des, ...ops, ...def].filter(Boolean)
const total = DISCOVERY.length + DESIGN.length + DEVOPS.length + DEFERRED.length
const failed = all.filter((r) => !(r.frontmatter_ok && r.voice_ok && r.under_500_lines && r.maps_escalation))
log(`built ${all.length}/${total} skills, ${failed.length} self-reported issues`)
return { built: all.length, total, failed, reports: all }
