export const meta = {
  name: 'build-vertical-skills',
  description: 'Fan out builder subagents to author the 62 SPGR vertical skills (perf, observability, resilience, analytics, a11y, API, flags, docs, async, billing, tenancy, app-store, i18n)',
  phases: [
    { title: 'Perf, Observability, Resilience' },
    { title: 'Analytics, Accessibility, API' },
    { title: 'Flags, Docs, Async' },
    { title: 'Billing, Tenancy, App Store, i18n' },
  ],
}

const SPEC_DIR = process.env.SPGR_SPEC_DIR ?? 'specs/skills'
const OUT_DIR = '.claude/skills'
const TEMPLATE = 'templates/SKILL.template.md'
const STANDARDS = process.env.SPGR_BUILD_STANDARDS ?? 'specs/BUILD-STANDARDS.md'

const A = [
  'analyze-query-plan', 'write-caching-strategy', 'write-load-test-plan', 'identify-bottleneck',
  'write-performance-budget', 'write-logging-schema', 'write-metric-definitions', 'write-slo-spec',
  'write-alert-runbook', 'audit-observability-coverage', 'configure-monitoring', 'configure-alerting',
  'write-resilience-spec', 'write-error-standards', 'write-error-ux-spec', 'audit-resilience-coverage',
]
const B = [
  'write-event-taxonomy', 'write-instrumentation-spec', 'define-funnel', 'audit-instrumentation-coverage',
  'write-ab-test-spec', 'mine-support-data', 'check-wcag-compliance', 'write-aria-spec',
  'audit-keyboard-navigation', 'check-color-contrast', 'write-accessibility-annotations',
  'review-api-consistency', 'write-api-versioning-strategy', 'generate-api-changelog', 'write-api-design-standards',
]
const C = [
  'define-feature-flag', 'write-rollout-plan', 'write-entitlement-map', 'audit-flag-debt',
  'generate-api-docs', 'generate-sdk', 'generate-readme', 'generate-changelog', 'generate-release-notes',
  'write-onboarding-guide', 'write-contributing-guide', 'audit-dx-friction', 'write-async-job-spec',
  'audit-async-coverage',
]
const D = [
  'write-billing-spec', 'write-metering-events', 'write-dunning-policy', 'write-webhook-spec',
  'audit-billing-accuracy', 'audit-tenant-isolation', 'check-rate-limit-consistency',
  'write-tenant-provisioning-spec', 'run-hig-review', 'run-material-review', 'write-privacy-manifest',
  'write-app-store-listing', 'run-submission-checklist', 'write-i18n-spec', 'audit-string-externalization',
  'check-rtl-support', 'write-locale-coverage-plan',
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
    notes: { type: 'string', description: 'one line on the output type (envelope artifact, report, or source/config) and validation mode' },
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
- AUTHORING VOICE (a hook blocks em-dashes in markdown, so do not write them): no em-dashes (use a comma, period, or regular hyphen), no semicolons, no body-text bold or italics (do not use ** or _ for emphasis; backticked code and glob patterns are fine), no emojis, no marketing adjectives (robust, powerful, seamless), no filler verbs. Do not write the word "leverage" or "utilize" in any form.
- No README, CHANGELOG, or process files. Only the single SKILL.md. Keep everything in SKILL.md; add references/ only if truly needed (one level deep, TOC if over 100 lines).

SPRINGER CONTRACT CONTEXT:
- This skill is owned by a vertical specialist agent (performance, observability, resilience, analytics, accessibility, API design, feature flag, documentation, async infrastructure, billing, multi-tenancy, app-store, or i18n). Vertical agents operate as consultant, auditor, and gate. Reference the artifact-plumbing skills by name where the spec implies them: spgr-read-file, spgr-write-file, spgr-read-artifact, spgr-write-artifact, spgr-validate-artifact, spgr-version-artifact, spgr-log-decision, spgr-escalate, spgr-notify-human, spgr-tag-vertical-agent.
- A vertical's recommendation to a horizontal agent flows through the registered consultation artifact (spgr-tag-vertical-agent). Where the spec says the vertical advises or signs off on another agent's artifact section, route that through a consultation rather than editing the other artifact directly.
- THREE KINDS OF OUTPUT. (1) A spec or policy ENVELOPE ARTIFACT (for example performance-budget, slo-spec, event-taxonomy, billing-spec, i18n-spec, resilience-spec): write via spgr-write-artifact with inline spgr-validate-artifact. (2) An AUDIT or REVIEW REPORT (audit-*, check-*, review-*, run-* findings): also an envelope artifact written via spgr-write-artifact, carrying findings by severity and a pass or gate verdict. (3) SOURCE OR CONFIG output (configure-monitoring, configure-alerting, generate-sdk, generate-readme, scaffolds): write files via spgr-write-file, verified by run-tests or CI.
- VALIDATION MODE: most vertical artifact types do not have a registered content schema yet. That is expected. spgr-validate-artifact falls back to envelope-only validation for unregistered types (it still checks the header, confidence map, decision log, and version). So still call spgr-validate-artifact, and add one Notes line stating the output type and that its content schema is registered in a later increment (envelope-only validation applies for now). The registered content-schema types right now are: prd, nfr, user-story, acceptance-criteria, architecture-options, adr, architecture-decision, erd, tech-stack-decision, data-dictionary, system-diagram, infrastructure-diagram, escalation, hil-checkpoint, consultation, test-plan, bug-report, uat-report, code-review, pull-request.
- Reflect the spec's specific methodology rules and the consultant/auditor/gate operating mode. Audit and check skills set a blocking threshold and gate behavior; map those exactly. Do not generically restate the domain.

After writing, return the structured report. Set the booleans to true only if you verified each by re-reading your file.`
}

async function buildBatch(names, phaseTitle) {
  return parallel(names.map((name) => () =>
    agent(prompt(name), { label: `build:spgr-${name}`, phase: phaseTitle, schema: REPORT_SCHEMA, agentType: 'general-purpose' })
  ))
}

phase('Perf, Observability, Resilience')
const a = await buildBatch(A, 'Perf, Observability, Resilience')
phase('Analytics, Accessibility, API')
const b = await buildBatch(B, 'Analytics, Accessibility, API')
phase('Flags, Docs, Async')
const c = await buildBatch(C, 'Flags, Docs, Async')
phase('Billing, Tenancy, App Store, i18n')
const d = await buildBatch(D, 'Billing, Tenancy, App Store, i18n')

const all = [...a, ...b, ...c, ...d].filter(Boolean)
const total = A.length + B.length + C.length + D.length
const failed = all.filter((r) => !(r.frontmatter_ok && r.voice_ok && r.under_500_lines && r.maps_escalation))
log(`built ${all.length}/${total} skills, ${failed.length} self-reported issues`)
return { built: all.length, total, failed, reports: all }
