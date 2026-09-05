/**
 * linear-sync
 *
 * The single deterministic channel for every Linear read and write the
 * Springer harness performs. Agents never talk to Linear directly: issue
 * fetching, state transitions, comments, and story publication are mechanical
 * operations, so they live here, out of the model, the same way
 * derive-ready-queue.py keeps readiness derivation out of the orchestrator.
 *
 * The repo's typed artifacts under runs/ stay the source of truth. Linear is a
 * regenerable human-facing projection of them (the same relationship
 * run-state.json has to the pdca-cycle log). This script therefore only ever
 * PUSHES repo state to Linear or READS Linear intake; it never treats Linear
 * as the database.
 *
 * Config:   runs/_linear/config.json     (team/project/state/label ids)
 * Registry: runs/_linear/issue-map.json  (Linear issue <-> run/story/PR map;
 *                                         what makes every command idempotent)
 * Auth:     LINEAR_API_KEY from the environment, falling back to the repo
 *           root .env. Personal API keys are sent bare (no Bearer prefix).
 *
 * Usage: npx tsx .claude/skills/spgr-run-harness/scripts/linear-sync.ts <command> [args]
 *
 *   whoami                          verify auth; print viewer and workspace
 *   ensure-labels                   create the agent:* labels if missing and
 *                                   write their ids back into config.json
 *   fetch-ready                     print JSON of agent:ready issues not yet
 *                                   in the issue map (the intake queue)
 *   publish-story --title <t> [--description-file <f>] [--type <label>]
 *                 [--story-id <id>] [--run-id <id>]
 *                                   create a Linear issue for a confirmed
 *                                   story and record the mapping
 *   transition <issue> <state>      move an issue (state by name, e.g. Done)
 *   comment <issue> --body <text> | --body-file <f>
 *   link-pr <issue> <url> [--title <t>]
 *                                   attach a PR to an issue and record it
 *   sync-run <run-dir> [--placements <file>]
 *                                   project a run's story backlog onto the
 *                                   Linear board: publish unpublished
 *                                   stories, reconcile states (idempotent)
 */

import {readFileSync, readdirSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {parseArgs} from 'node:util';

// This file lives at .claude/skills/spgr-run-harness/scripts/, four levels
// below the project root, where runs/ and .env are.
const REPO_ROOT = join(__dirname, '..', '..', '..', '..');
const CONFIG_PATH = join(REPO_ROOT, 'runs', '_linear', 'config.json');
const ISSUE_MAP_PATH = join(REPO_ROOT, 'runs', '_linear', 'issue-map.json');
const LINEAR_ENDPOINT = 'https://api.linear.app/graphql';

const READY_LABEL = 'agent:ready';
const BLOCKED_LABEL = 'agent:blocked';
/** Label name -> Linear label color, for ensure-labels creation only. */
const AGENT_LABEL_COLORS = new Map<string, string>([
  [READY_LABEL, '#0f7938'],
  [BLOCKED_LABEL, '#eb5757'],
]);

interface LinearConfig {
  schema_version: string;
  backlog_provider: string;
  team: {id: string; key: string};
  project: {id: string; name: string};
  states: Record<string, string>;
  labels: Record<string, string | null>;
  wip_board_state_map: Record<string, string>;
  milestones?: Record<string, string>;
  default_milestone?: string;
  intake_assignee_email?: string;
}

function milestoneId(config: LinearConfig, name: string): string {
  const milestones = new Map(Object.entries(config.milestones ?? {}));
  milestones.delete('//');
  const id = milestones.get(name);
  if (!id) {
    fail(
      `unknown milestone "${name}". Known: ` +
        [...milestones.keys()].join(', '),
    );
  }
  return id;
}

/** The default milestone's id, or null when none is configured. */
function defaultMilestoneId(config: LinearConfig): string | null {
  return config.default_milestone
    ? milestoneId(config, config.default_milestone)
    : null;
}

interface IssueMapEntry {
  issue_id: string;
  identifier: string;
  url: string;
  title: string;
  run_id: string | null;
  story_id: string | null;
  branch: string | null;
  pr_url: string | null;
  created_at: string;
}

interface IssueMap {
  schema_version: string;
  entries: IssueMapEntry[];
}

interface IssueNode {
  id: string;
  identifier: string;
  title: string;
  description: string | null;
  priority: number;
  url: string;
  state: {name: string};
  labels: {nodes: Array<{name: string}>};
}

function fail(message: string): never {
  throw new Error(message);
}

function apiKey(): string {
  const fromEnv = process.env.LINEAR_API_KEY;
  if (fromEnv) return fromEnv;
  // Fallback: parse only LINEAR_API_KEY out of the root .env, so the CLI works
  // without a dotenv loader and without importing anything else from that file.
  let envText: string;
  try {
    envText = readFileSync(join(REPO_ROOT, '.env'), 'utf8');
  } catch {
    fail('LINEAR_API_KEY is not set and no .env was found at the repo root');
  }
  const line = envText.split('\n').find(l => l.startsWith('LINEAR_API_KEY='));
  if (!line) fail('LINEAR_API_KEY is not set (env or repo-root .env)');
  const value = line.slice('LINEAR_API_KEY='.length).trim();
  if (!value) fail('LINEAR_API_KEY is empty in .env');
  return value;
}

async function gql<T>(
  query: string,
  variables: Record<string, unknown> = {},
): Promise<T> {
  const response = await fetch(LINEAR_ENDPOINT, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      // Linear personal API keys are sent bare, without a Bearer prefix.
      Authorization: apiKey(),
    },
    body: JSON.stringify({query, variables}),
  });
  if (!response.ok) {
    fail(`Linear API HTTP ${response.status}: ${await response.text()}`);
  }
  const payload = (await response.json()) as {
    data?: T;
    errors?: Array<{message: string}>;
  };
  if (payload.errors?.length) {
    fail(`Linear API error: ${payload.errors.map(e => e.message).join('; ')}`);
  }
  if (payload.data === undefined) fail('Linear API returned no data');
  return payload.data;
}

function readConfig(): LinearConfig {
  try {
    return JSON.parse(readFileSync(CONFIG_PATH, 'utf8')) as LinearConfig;
  } catch (err) {
    fail(`cannot read ${CONFIG_PATH}: ${(err as Error).message}`);
  }
}

function writeConfig(config: LinearConfig): void {
  writeFileSync(CONFIG_PATH, `${JSON.stringify(config, null, 2)}\n`);
}

function readIssueMap(): IssueMap {
  let text: string;
  try {
    text = readFileSync(ISSUE_MAP_PATH, 'utf8');
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === 'ENOENT') {
      // First use: the registry starts empty and is created on first write.
      return {schema_version: 'v1', entries: []};
    }
    fail(`cannot read ${ISSUE_MAP_PATH}: ${(err as Error).message}`);
  }
  try {
    return JSON.parse(text) as IssueMap;
  } catch (err) {
    fail(`cannot parse ${ISSUE_MAP_PATH}: ${(err as Error).message}`);
  }
}

function writeIssueMap(map: IssueMap): void {
  writeFileSync(ISSUE_MAP_PATH, `${JSON.stringify(map, null, 2)}\n`);
}

function stateId(config: LinearConfig, stateName: string): string {
  const states = new Map(Object.entries(config.states));
  const id = states.get(stateName);
  if (!id) {
    fail(
      `unknown state "${stateName}". Known: ${[...states.keys()].join(', ')}`,
    );
  }
  return id;
}

/**
 * Resolve an issue reference to its Linear issue. Accepts a Linear identifier
 * (ABC-12), a UUID, or a Springer story id (STORY-2026-001), the last via the
 * issue map so harness callers never need to know Linear identifiers.
 * Every <issue> argument below accepts any of the three forms.
 */
async function resolveIssue(reference: string): Promise<IssueNode> {
  let lookup = reference;
  const mapped = readIssueMap().entries.find(e => e.story_id === reference);
  if (mapped) {
    lookup = mapped.issue_id;
  } else if (reference.includes('STORY-')) {
    fail(`story ${reference} has no mapped Linear issue`);
  }
  const data = await gql<{issue: IssueNode | null}>(
    `query($id: String!) { issue(id: $id) {
       id identifier title description priority url
       state { name } labels { nodes { name } }
     } }`,
    {id: lookup},
  );
  if (!data.issue) fail(`issue "${reference}" not found`);
  return data.issue;
}

async function cmdWhoami(): Promise<void> {
  const data = await gql<{
    viewer: {name: string; email: string};
    organization: {name: string; urlKey: string};
  }>('{ viewer { name email } organization { name urlKey } }');
  console.log(
    `Authenticated as ${data.viewer.name} <${data.viewer.email}> ` +
      `in workspace "${data.organization.name}" (${data.organization.urlKey})`,
  );
}

async function cmdEnsureLabels(): Promise<void> {
  const config = readConfig();
  const data = await gql<{
    team: {labels: {nodes: Array<{id: string; name: string}>}};
  }>(
    `query($teamId: String!) { team(id: $teamId) {
       labels { nodes { id name } }
     } }`,
    {teamId: config.team.id},
  );
  const existing = new Map(data.team.labels.nodes.map(l => [l.name, l.id]));
  const labels = new Map(Object.entries(config.labels));

  for (const [name, color] of AGENT_LABEL_COLORS) {
    const found = existing.get(name);
    if (found) {
      labels.set(name, found);
      console.log(`label "${name}" already exists (${found})`);
      continue;
    }
    const created = await gql<{
      issueLabelCreate: {issueLabel: {id: string}};
    }>(
      `mutation($input: IssueLabelCreateInput!) {
         issueLabelCreate(input: $input) { issueLabel { id } }
       }`,
      {input: {teamId: config.team.id, name, color}},
    );
    labels.set(name, created.issueLabelCreate.issueLabel.id);
    console.log(
      `created label "${name}" (${created.issueLabelCreate.issueLabel.id})`,
    );
  }

  config.labels = Object.fromEntries(labels);
  writeConfig(config);
  console.log(`label ids recorded in ${CONFIG_PATH}`);
}

async function cmdFetchReady(): Promise<void> {
  const config = readConfig();
  const map = readIssueMap();
  const mapped = new Set(map.entries.map(e => e.issue_id));
  // Two equivalent intake triggers: the agent:ready label, or assignment to
  // the intake assignee (the human assigns an issue to the agent identity to
  // hand it to the PDCA loop). Linear's issue filter ORs at the top level.
  const orFilters: string[] = ['{labels: {some: {name: {eq: $label}}}}'];
  if (config.intake_assignee_email) {
    orFilters.push('{assignee: {email: {eq: $assigneeEmail}}}');
  }
  const variables: Record<string, string> = {
    teamId: config.team.id,
    label: READY_LABEL,
  };
  let varDecls = '$teamId: ID!, $label: String!';
  if (config.intake_assignee_email) {
    varDecls += ', $assigneeEmail: String!';
    variables.assigneeEmail = config.intake_assignee_email;
  }
  const data = await gql<{issues: {nodes: IssueNode[]}}>(
    `query(${varDecls}) {
       issues(
         first: 50,
         filter: {
           team: {id: {eq: $teamId}},
           or: [${orFilters.join(', ')}]
         }
       ) { nodes {
         id identifier title description priority url
         state { name } labels { nodes { name } }
       } }
     }`,
    variables,
  );
  const ready = data.issues.nodes.filter(issue => !mapped.has(issue.id));
  console.log(JSON.stringify(ready, null, 2));
}

async function cmdPublishStory(argv: string[]): Promise<void> {
  const {values} = parseArgs({
    args: argv,
    options: {
      title: {type: 'string'},
      'description-file': {type: 'string'},
      type: {type: 'string'},
      'story-id': {type: 'string'},
      'run-id': {type: 'string'},
      state: {type: 'string'},
    },
  });
  if (!values.title) fail('publish-story requires --title');
  const config = readConfig();

  const map = readIssueMap();
  const storyId = values['story-id'] ?? null;
  if (storyId) {
    const existing = map.entries.find(e => e.story_id === storyId);
    if (existing) {
      console.log(
        `story ${storyId} is already published as ${existing.identifier} ` +
          `(${existing.url}); skipping`,
      );
      return;
    }
  }

  let description = '';
  if (values['description-file']) {
    description = readFileSync(values['description-file'], 'utf8');
  }
  const labelIds: string[] = [];
  if (values.type) {
    const labels = new Map(Object.entries(config.labels));
    const labelId = labels.get(values.type);
    if (!labelId) {
      fail(
        `unknown label "${values.type}". Known: ` +
          [...labels.keys()].join(', '),
      );
    }
    labelIds.push(labelId);
  }

  const title = storyId ? `${storyId}: ${values.title}` : values.title;
  const data = await gql<{
    issueCreate: {
      success: boolean;
      issue: {id: string; identifier: string; url: string};
    };
  }>(
    `mutation($input: IssueCreateInput!) {
       issueCreate(input: $input) {
         success issue { id identifier url }
       }
     }`,
    {
      input: {
        teamId: config.team.id,
        projectId: config.project.id,
        title,
        description,
        labelIds,
        projectMilestoneId: defaultMilestoneId(config),
        stateId: values.state ? stateId(config, values.state) : undefined,
      },
    },
  );
  if (!data.issueCreate.success) fail('issueCreate reported failure');
  const issue = data.issueCreate.issue;

  map.entries.push({
    issue_id: issue.id,
    identifier: issue.identifier,
    url: issue.url,
    title,
    run_id: values['run-id'] ?? null,
    story_id: storyId,
    branch: null,
    pr_url: null,
    created_at: new Date().toISOString(),
  });
  writeIssueMap(map);
  console.log(`${issue.identifier} ${issue.url}`);
}

async function cmdTransition(argv: string[]): Promise<void> {
  const [reference, ...stateWords] = argv;
  const stateName = stateWords.join(' ');
  if (!reference || !stateName) {
    fail('usage: transition <issue> <state name>');
  }
  const config = readConfig();
  const issue = await resolveIssue(reference);
  const targetId = stateId(config, stateName);
  await gql(
    `mutation($id: String!, $stateId: String!) {
       issueUpdate(id: $id, input: {stateId: $stateId}) { success }
     }`,
    {id: issue.id, stateId: targetId},
  );
  console.log(`${issue.identifier}: ${issue.state.name} -> ${stateName}`);
}

async function cmdComment(argv: string[]): Promise<void> {
  const {values, positionals} = parseArgs({
    args: argv,
    allowPositionals: true,
    options: {
      body: {type: 'string'},
      'body-file': {type: 'string'},
    },
  });
  const reference = positionals[0];
  if (!reference) fail('usage: comment <issue> --body <text>|--body-file <f>');
  let body = values.body ?? '';
  if (values['body-file']) body = readFileSync(values['body-file'], 'utf8');
  if (!body) fail('comment requires --body or --body-file');
  const issue = await resolveIssue(reference);
  await gql(
    `mutation($input: CommentCreateInput!) {
       commentCreate(input: $input) { success }
     }`,
    {input: {issueId: issue.id, body}},
  );
  console.log(`commented on ${issue.identifier}`);
}

async function cmdLinkPr(argv: string[]): Promise<void> {
  const {values, positionals} = parseArgs({
    args: argv,
    allowPositionals: true,
    options: {title: {type: 'string'}},
  });
  const [reference, url] = positionals;
  if (!reference || !url) fail('usage: link-pr <issue> <pr-url> [--title <t>]');
  const issue = await resolveIssue(reference);
  await gql(
    `mutation($input: AttachmentCreateInput!) {
       attachmentCreate(input: $input) { success }
     }`,
    {input: {issueId: issue.id, url, title: values.title ?? 'Pull request'}},
  );
  const map = readIssueMap();
  const entry = map.entries.find(e => e.issue_id === issue.id);
  if (entry) {
    entry.pr_url = url;
    writeIssueMap(map);
  }
  console.log(`attached ${url} to ${issue.identifier}`);
}

async function cmdCreateIssue(argv: string[]): Promise<void> {
  const {values} = parseArgs({
    args: argv,
    allowPositionals: false,
    options: {
      title: {type: 'string'},
      body: {type: 'string'},
      'body-file': {type: 'string'},
      label: {type: 'string', multiple: true},
      state: {type: 'string'},
      'blocked-by': {type: 'string', multiple: true},
      milestone: {type: 'string'},
      priority: {type: 'string'},
    },
  });
  const title = values.title;
  if (!title) {
    fail(
      'usage: create-issue --title <t> [--body <text>|--body-file <f>] ' +
        '[--label <name>]... [--state <name>] [--blocked-by <issue>]... ' +
        '[--milestone <name>] [--priority <1-4>]',
    );
  }
  let body = values.body ?? '';
  if (values['body-file']) body = readFileSync(values['body-file'], 'utf8');

  const config = readConfig();

  // Labels resolve by name against the live workspace (team and workspace
  // labels both), not only the handful cached in config.labels, so ad-hoc
  // labels like "Deviation" work without a config edit. Unknown names fail
  // loudly rather than silently shipping an unlabeled issue.
  const labelIds: string[] = [];
  const wanted = values.label ?? [];
  if (wanted.length) {
    const data = await gql<{
      issueLabels: {nodes: Array<{id: string; name: string}>};
    }>('query { issueLabels(first: 250) { nodes { id name } } }', {});
    const byName = new Map(data.issueLabels.nodes.map(l => [l.name, l.id]));
    for (const name of wanted) {
      const id = config.labels[name] ?? byName.get(name);
      if (!id) fail(`label "${name}" not found in the workspace`);
      labelIds.push(id);
    }
  }

  const priority = values.priority ? Number(values.priority) : 0;
  if (Number.isNaN(priority) || priority < 0 || priority > 4) {
    fail('--priority must be 1 (urgent) .. 4 (low)');
  }

  const created = await gql<{
    issueCreate: {
      success: boolean;
      issue: {id: string; identifier: string; url: string};
    };
  }>(
    `mutation($input: IssueCreateInput!) {
       issueCreate(input: $input) {
         success issue { id identifier url }
       }
     }`,
    {
      input: {
        teamId: config.team.id,
        projectId: config.project.id,
        title,
        description: body,
        stateId: stateId(config, values.state ?? 'Backlog'),
        priority,
        labelIds,
        projectMilestoneId: values.milestone
          ? milestoneId(config, values.milestone)
          : defaultMilestoneId(config),
      },
    },
  );
  if (!created.issueCreate.success) fail(`issueCreate failed for "${title}"`);
  const issue = created.issueCreate.issue;
  console.log(`created ${issue.identifier}: ${issue.url}`);

  // "blocked by X" is Linear relation type `blocks` with X as the issueId
  // side. Relations land after creation; a failure here leaves the issue
  // standing, so report each link as it lands for manual repair on error.
  for (const ref of values['blocked-by'] ?? []) {
    const blocker = await resolveIssue(ref);
    await gql(
      `mutation($input: IssueRelationCreateInput!) {
         issueRelationCreate(input: $input) { success }
       }`,
      {
        input: {
          issueId: blocker.id,
          relatedIssueId: issue.id,
          type: 'blocks',
        },
      },
    );
    console.log(`blocked by ${blocker.identifier}`);
  }
}

interface BacklogStory {
  story_id: string;
  epic_id?: string;
  priority?: string;
  title: string;
  as_a?: string;
  i_want?: string;
  so_that?: string;
  depends_on?: string[];
  estimated_size?: string;
}

interface BacklogContent {
  epics?: Array<{epic_id: string; name: string}>;
  backlog_order?: string[];
  /** Ordered entries on a `prioritized-backlog` artifact. */
  backlog?: BacklogStory[];
  /** Legacy shape. Kept so an existing run store still syncs. */
  stories?: BacklogStory[];
}

/** The rollup's ordered entries, whichever field carries them. */
function backlogStories(b: BacklogContent): BacklogStory[] {
  return b.backlog ?? b.stories ?? [];
}

interface AcceptanceCriterion {
  ac_id: string;
  story_ref: string;
  scenario_type?: string;
  given?: string;
  when?: string;
  then?: string;
}

interface StoredArtifact {
  artifact_type?: string;
  timestamp?: string;
  content?: {
    backlog?: BacklogStory[];
    stories?: BacklogStory[];
    criteria?: AcceptanceCriterion[];
  };
}

/** Story priority -> Linear priority (1 Urgent, 2 High, 3 Normal, 4 Low). */
const STORY_PRIORITY_TO_LINEAR = new Map<string, number>([
  ['P1', 2],
  ['P2', 3],
  ['P3', 4],
]);

function loadRunArtifacts(runDir: string): StoredArtifact[] {
  const dir = join(runDir, 'artifacts');
  const artifacts: StoredArtifact[] = [];
  for (const name of readdirSync(dir)) {
    if (!name.endsWith('.json')) continue;
    try {
      artifacts.push(
        JSON.parse(readFileSync(join(dir, name), 'utf8')) as StoredArtifact,
      );
    } catch {
      // Non-artifact or malformed JSON in the store is not this command's
      // problem; spgr-validate-artifact owns store hygiene.
    }
  }
  return artifacts;
}

function buildStoryDescription(
  story: BacklogStory,
  epicName: string | null,
  criteria: AcceptanceCriterion[],
  runDir: string,
): string {
  const lines: string[] = [];
  if (story.as_a && story.i_want && story.so_that) {
    lines.push(
      `**As** ${story.as_a}, **I want** ${story.i_want}, ` +
        `**so that** ${story.so_that}.`,
      '',
    );
  }
  const facts: string[] = [];
  if (epicName) facts.push(`Epic: ${story.epic_id} (${epicName})`);
  if (story.priority) facts.push(`Priority: ${story.priority}`);
  if (story.estimated_size) facts.push(`Size: ${story.estimated_size}`);
  if (story.depends_on?.length) {
    facts.push(`Depends on: ${story.depends_on.join(', ')}`);
  }
  if (facts.length) lines.push(facts.join(' · '), '');
  if (criteria.length) {
    lines.push('### Acceptance criteria', '');
    for (const ac of criteria) {
      lines.push(
        `- **${ac.ac_id}** (${ac.scenario_type ?? 'scenario'}): ` +
          `Given ${ac.given ?? '?'}, when ${ac.when ?? '?'}, ` +
          `then ${ac.then ?? '?'}.`,
      );
    }
    lines.push('');
  }
  lines.push(
    '---',
    `_Projected from the typed artifacts in \`${runDir}\` by ` +
      '`linear-sync.ts`. The repo artifacts are the source of ' +
      'truth; scope edits made here are surfaced to the harness as ' +
      'scope-change gates, not silently absorbed._',
  );
  return lines.join('\n');
}

/**
 * sync-run <run-dir> [--placements <file>]
 *
 * Project a run's confirmed story backlog onto the Linear board. Idempotent:
 * publishes stories with no mapped issue, then reconciles issue states.
 *
 * State authority, per story:
 *   1. the --placements file (story id -> Linear state name), when given;
 *   2. the run-state wip_board column, via config.wip_board_state_map;
 *   3. otherwise: new issues start in Backlog, existing issues are LEFT
 *      ALONE. The absence of a story from the wip_board never demotes its
 *      issue, so an idle board (or a human dragging cards) is never fought.
 */
async function cmdSyncRun(argv: string[]): Promise<void> {
  const {values, positionals} = parseArgs({
    args: argv,
    allowPositionals: true,
    options: {placements: {type: 'string'}},
  });
  const runDir = positionals[0];
  if (!runDir) fail('usage: sync-run <run-dir> [--placements <file>]');
  const config = readConfig();
  const map = readIssueMap();
  const runId = runDir.replace(/\/+$/, '').split('/').pop() ?? runDir;

  const artifacts = loadRunArtifacts(runDir);
  const backlogs = artifacts
    .filter(a =>
      (a.artifact_type === 'prioritized-backlog' && a.content?.backlog) ||
      (a.artifact_type === 'user-story' && a.content?.stories),
    )
    .sort((a, b) => (a.timestamp ?? '').localeCompare(b.timestamp ?? ''));
  const backlogArtifact = backlogs.at(-1);
  if (!backlogArtifact) fail(`no prioritized-backlog artifact in ${runDir}`);
  const backlog = backlogArtifact.content as BacklogContent;
  const epicNames = new Map(
    (backlog.epics ?? []).map(e => [e.epic_id, e.name]),
  );

  // Acceptance criteria may live in one aggregate artifact or per-story
  // artifacts; merge by ac_id with the newest artifact winning.
  const criteriaById = new Map<string, AcceptanceCriterion>();
  for (const a of artifacts
    .filter(a => a.artifact_type === 'acceptance-criteria')
    .sort((a, b) => (a.timestamp ?? '').localeCompare(b.timestamp ?? ''))) {
    for (const ac of a.content?.criteria ?? []) {
      criteriaById.set(ac.ac_id, ac);
    }
  }
  const criteriaByStory = new Map<string, AcceptanceCriterion[]>();
  for (const ac of criteriaById.values()) {
    const list = criteriaByStory.get(ac.story_ref) ?? [];
    list.push(ac);
    criteriaByStory.set(ac.story_ref, list);
  }

  // Desired states: placements file first, then the wip_board.
  const desired = new Map<string, string>();
  let wipBoard: Record<string, string[]> = {};
  try {
    wipBoard =
      (
        JSON.parse(readFileSync(join(runDir, 'run-state.json'), 'utf8')) as {
          content: {wip_board?: Record<string, string[]>};
        }
      ).content.wip_board ?? {};
  } catch {
    // No projection yet; the wip_board is simply not a state source.
  }
  const columnToState = new Map(Object.entries(config.wip_board_state_map));
  for (const [column, storyIds] of Object.entries(wipBoard)) {
    const state = columnToState.get(column);
    if (!state || !Array.isArray(storyIds)) continue;
    for (const storyId of storyIds) desired.set(storyId, state);
  }
  if (values.placements) {
    const placements = JSON.parse(
      readFileSync(values.placements, 'utf8'),
    ) as Record<string, string>;
    for (const [storyId, state] of Object.entries(placements)) {
      stateId(config, state); // validates the state name
      desired.set(storyId, state);
    }
  }

  // One query for the whole project's current board, instead of one per issue.
  const board = await gql<{
    issues: {
      nodes: Array<{
        id: string;
        state: {name: string};
        projectMilestone: {id: string} | null;
      }>;
    };
  }>(
    `query($projectId: ID!) {
       issues(first: 250, filter: {project: {id: {eq: $projectId}}}) {
         nodes { id state { name } projectMilestone { id } }
       }
     }`,
    {projectId: config.project.id},
  );
  const currentState = new Map(
    board.issues.nodes.map(i => [i.id, i.state.name]),
  );
  const currentMilestone = new Map(
    board.issues.nodes.map(i => [i.id, i.projectMilestone?.id ?? null]),
  );
  const defaultMilestone = defaultMilestoneId(config);

  const labels = new Map(Object.entries(config.labels));
  const entries = backlogStories(backlog);
  const order = backlog.backlog_order?.length
    ? backlog.backlog_order
    : entries.map(s => s.story_id);
  const storiesById = new Map(entries.map(s => [s.story_id, s]));
  let created = 0;
  let moved = 0;
  let milestoned = 0;

  for (const storyId of order) {
    const story = storiesById.get(storyId);
    if (!story) continue;
    const target = desired.get(storyId) ?? null;
    const entry = map.entries.find(e => e.story_id === storyId);

    if (!entry) {
      const state = target ?? 'Backlog';
      const featureLabel = labels.get('Feature');
      const data = await gql<{
        issueCreate: {
          success: boolean;
          issue: {id: string; identifier: string; url: string};
        };
      }>(
        `mutation($input: IssueCreateInput!) {
           issueCreate(input: $input) {
             success issue { id identifier url }
           }
         }`,
        {
          input: {
            teamId: config.team.id,
            projectId: config.project.id,
            title: `${storyId}: ${story.title}`,
            description: buildStoryDescription(
              story,
              story.epic_id ? epicNames.get(story.epic_id) ?? null : null,
              criteriaByStory.get(storyId) ?? [],
              runDir,
            ),
            stateId: stateId(config, state),
            priority: STORY_PRIORITY_TO_LINEAR.get(story.priority ?? '') ?? 0,
            labelIds: featureLabel ? [featureLabel] : [],
            projectMilestoneId: defaultMilestone,
          },
        },
      );
      if (!data.issueCreate.success) fail(`issueCreate failed for ${storyId}`);
      map.entries.push({
        issue_id: data.issueCreate.issue.id,
        identifier: data.issueCreate.issue.identifier,
        url: data.issueCreate.issue.url,
        title: `${storyId}: ${story.title}`,
        run_id: runId,
        story_id: storyId,
        branch: null,
        pr_url: null,
        created_at: new Date().toISOString(),
      });
      writeIssueMap(map); // persist per issue so a crash never double-creates
      created += 1;
      console.log(
        `created ${data.issueCreate.issue.identifier} <- ${storyId} [${state}]`,
      );
      continue;
    }

    if (
      defaultMilestone &&
      currentMilestone.has(entry.issue_id) &&
      currentMilestone.get(entry.issue_id) === null
    ) {
      await gql(
        `mutation($id: String!, $milestoneId: String!) {
           issueUpdate(id: $id, input: {projectMilestoneId: $milestoneId}) {
             success
           }
         }`,
        {id: entry.issue_id, milestoneId: defaultMilestone},
      );
      milestoned += 1;
      console.log(
        `milestoned ${entry.identifier} (${storyId}) -> ` +
          `${config.default_milestone}`,
      );
    }

    if (target && currentState.get(entry.issue_id) !== target) {
      await gql(
        `mutation($id: String!, $stateId: String!) {
           issueUpdate(id: $id, input: {stateId: $stateId}) { success }
         }`,
        {id: entry.issue_id, stateId: stateId(config, target)},
      );
      moved += 1;
      console.log(
        `moved ${entry.identifier} (${storyId}) ` +
          `${currentState.get(entry.issue_id) ?? '?'} -> ${target}`,
      );
    }
  }
  const orderSet = new Set(order);
  const unlisted = entries
    .map(s => s.story_id)
    .filter(id => !orderSet.has(id));
  if (unlisted.length) {
    console.log(
      `not published (absent from backlog_order, i.e. dropped): ` +
        unlisted.join(', '),
    );
  }
  console.log(
    `sync-run ${runId}: ${created} created, ${moved} moved, ` +
      `${milestoned} milestoned, ${order.length} stories in backlog`,
  );
}

async function cmdSetMilestone(argv: string[]): Promise<void> {
  const [reference, ...nameWords] = argv;
  const name = nameWords.join(' ');
  if (!reference || !name) fail('usage: set-milestone <issue> <name>');
  const config = readConfig();
  const issue = await resolveIssue(reference);
  await gql(
    `mutation($id: String!, $milestoneId: String!) {
       issueUpdate(id: $id, input: {projectMilestoneId: $milestoneId}) {
         success
       }
     }`,
    {id: issue.id, milestoneId: milestoneId(config, name)},
  );
  console.log(`${issue.identifier} -> milestone "${name}"`);
}

async function main(): Promise<void> {
  const [command, ...rest] = process.argv.slice(2);
  switch (command) {
    case 'whoami':
      return cmdWhoami();
    case 'ensure-labels':
      return cmdEnsureLabels();
    case 'fetch-ready':
      return cmdFetchReady();
    case 'publish-story':
      return cmdPublishStory(rest);
    case 'transition':
      return cmdTransition(rest);
    case 'comment':
      return cmdComment(rest);
    case 'link-pr':
      return cmdLinkPr(rest);
    case 'sync-run':
      return cmdSyncRun(rest);
    case 'set-milestone':
      return cmdSetMilestone(rest);
    case 'create-issue':
      return cmdCreateIssue(rest);
    default:
      fail(
        'unknown command. Commands: whoami, ensure-labels, fetch-ready, ' +
          'publish-story, transition, comment, link-pr, sync-run, ' +
          'set-milestone, create-issue',
      );
  }
}

main().catch((err: unknown) => {
  console.error(`linear-sync: ${(err as Error).message}`);
  process.exitCode = 1;
});
