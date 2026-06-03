export const meta = {
  name: 'build-vertical-agents',
  description: 'Fan out builder subagents to author the 13 SPGR vertical agents from their Phase 1 specs',
  phases: [{ title: 'Vertical agents' }],
}

const SPEC_DIR = '/Users/gunderer/Repos/ecg-intel/vault/40-projects/springer/agents'
const OUT_DIR = '/Users/gunderer/Repos/springer/.claude/agents'
const TEMPLATE = '/Users/gunderer/Repos/springer/templates/agent.template.md'
const STANDARDS = '/Users/gunderer/Repos/ecg-intel/vault/40-projects/springer/build/BUILD-STANDARDS.md'

// model defaults to opus for the judgment-heavy verticals; documentation inherits.
const AGENTS = [
  { name: 'performance', model: 'opus' },
  { name: 'observability', model: 'opus' },
  { name: 'resilience', model: 'opus' },
  { name: 'analytics', model: 'opus' },
  { name: 'accessibility', model: 'opus' },
  { name: 'api-design', model: 'opus' },
  { name: 'feature-flag', model: 'opus' },
  { name: 'documentation', model: 'inherit' },
  { name: 'async-infrastructure', model: 'opus' },
  { name: 'billing', model: 'opus' },
  { name: 'multi-tenancy', model: 'opus' },
  { name: 'app-store', model: 'opus' },
  { name: 'i18n', model: 'opus' },
]

const REPORT_SCHEMA = {
  type: 'object',
  required: ['agent_name', 'file_path', 'frontmatter_ok', 'voice_ok', 'tools_declared', 'maps_contract', 'notes'],
  additionalProperties: false,
  properties: {
    agent_name: { type: 'string' },
    file_path: { type: 'string' },
    frontmatter_ok: { type: 'boolean', description: 'frontmatter has name, description, tools, model; description is delegation-framed' },
    voice_ok: { type: 'boolean', description: 'no em-dash, semicolon, body bold/italic, emoji, or banned filler' },
    tools_declared: { type: 'boolean', description: 'tools line is exactly the prescribed set' },
    maps_contract: { type: 'boolean', description: 'input/output contract, operating mode, methodology rules, escalation triggers, and gate all mapped' },
    notes: { type: 'string', description: 'one line on the agent operating mode and any gate it owns' },
  },
}

function prompt(name, model) {
  return `Build one SPGR vertical agent from its Phase 1 spec. This is a file-authoring task. Produce exactly one file.

SPEC (source of truth, read it fully): ${SPEC_DIR}/spgr-agent-${name}.md
Use its "Phase 2 Build Notes" as the build brief and map its Overview, Operating Mode, Input Contract, Output Contract, Skills Required, Methodology Rules, Escalation Triggers, and HIL Gate.

GOLDEN TEMPLATE (copy this shape, fill it in, delete all template comments): ${TEMPLATE}
BUILD STANDARDS (authoritative, read the Agents section): ${STANDARDS}

WRITE THE FILE TO: ${OUT_DIR}/spgr-agent-${name}.md

FRONTMATTER (exactly these four keys):
- name: spgr-agent-${name}
- description: framed for WHEN TO DELEGATE to this agent (the kind of task or decision that should route here), stating it is the consultant, auditor, and gate for its domain. Not "this agent is...". One to three sentences.
- tools: Read, Write, Grep, Glob, Bash
- model: ${model}

The tools are fixed: Read, Write, Grep, Glob, Bash. The agent authors spec and report artifacts (Write) and runs scanners, audits, or generators (Bash). It must NOT have Edit and must never edit application code. State that constraint in the body.

BODY (this is the system prompt, it replaces the default). Use these sections:
- Opening line: "You are the SPGR <Role> agent." plus the single responsibility from the Overview.
- "## Operating mode" or fold into workflow: state the consultant, auditor, and gate behaviors from the spec, including which artifact section its sign-off gates and on what cadence it audits.
- "## Inputs you receive": the spec Input Contract.
- "## Workflow": numbered imperative steps mapping the Methodology Rules, naming the skills it calls by their built names (spgr-<skill-slug>, for example a Skills Required entry "write-slo-spec" is the skill spgr-write-slo-spec). Include the validation and consultation steps: a vertical advises a horizontal agent through spgr-tag-vertical-agent (the registered consultation artifact), writes its own artifacts via spgr-write-artifact with inline spgr-validate-artifact, and records decisions with spgr-log-decision.
- "## Constraints": what it must and must not do, including no code edits, and any non-skippable methodology rule.
- "## Escalation": each spec Escalation Trigger mapped to an action (block, tag specialist, escalate to human via spgr-escalate or spgr-notify-human). Map the HIL vertical-flag behavior where the spec has it.
- "## Output format": the artifacts it produces (envelope spec or report artifacts in the run store, findings by severity, gate verdict) and what its sign-off gates.

AUTHORING VOICE: no em-dashes (a hook blocks them in markdown), no semicolons, no body-text bold or italics, no emojis, no marketing adjectives (robust, powerful, seamless), no filler verbs (do not write "leverage" or "utilize" in any form).

Most vertical artifact types have no registered content schema yet; that is expected. spgr-validate-artifact falls back to envelope-only validation for them, so still validate. Do not invent a schema.

After writing, return the structured report. Set the booleans to true only if you verified each by re-reading your file.`
}

phase('Vertical agents')
const reports = (await parallel(AGENTS.map((a) => () =>
  agent(prompt(a.name, a.model), { label: `agent:spgr-agent-${a.name}`, phase: 'Vertical agents', schema: REPORT_SCHEMA, agentType: 'general-purpose' })
))).filter(Boolean)

const failed = reports.filter((r) => !(r.frontmatter_ok && r.voice_ok && r.tools_declared && r.maps_contract))
log(`built ${reports.length}/${AGENTS.length} agents, ${failed.length} self-reported issues`)
return { built: reports.length, total: AGENTS.length, failed, reports }
