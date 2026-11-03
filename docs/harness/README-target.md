# Springer

An AI software team that runs on contracts, not trust. Brief in, product out, five decisions in between.

Springer is a harness and a runtime. The runtime is a library of Claude Code agents and skills that model a product and engineering organization: discovery, product management, architecture, design, development, QA, code review, DevOps, and the cross-cutting specialists for auth, security, compliance, accessibility, performance, and the rest. The harness is a daemon on a machine you own that drives those agents through one opinionated workflow, merges their work when it is safe, and asks you only for the decisions that need a person. You work in a terminal UI. Your main job is writing the brief.

## Who this is for

A developer or small team that wants to ship a web SaaS or a React Native app without a product manager, a designer, or a release engineer on staff, and without spending the day answering an agent's questions. You should be comfortable reading a pull request and running a Linux box. You do not need to be a designer. Springer is built to give a non-designer a designed product.

## Why Springer

Most agentic coding tools fail in one of two directions. They over-automate and remove human judgment where it is needed, or they put a person at every handoff and lose the gain that made automation worth it. Springer takes a third position: the way to remove the human bottleneck is not more trust in the model, it is clearer contracts between the roles. Everything below follows from that.

Typed handoffs. Every artifact one role passes to the next (the PRD, the backlog, the architecture decisions, the screen specs, the test plan, the pull request) is a typed, versioned record with required fields and a confidence signal of confirmed, proposed, or needs-human-input. The receiving agent validates it before acting. A downstream agent proceeds without asking when its input is complete, and escalates with a precise list when it is not. Agents do not fill gaps with guesses.

Architecture first. Architecture is the most consequential decision in a project and the most expensive to reverse, so it is the primary human checkpoint. The Architect proposes at least two distinct options with full trade-offs for anything you did not pin, and does not choose. Once you approve, the irreversible decisions (the data model and tenancy boundary, the auth model, billing, vendors) are immutable, and a developer that cannot satisfy a requirement within them escalates rather than deviating.

Design with latitude, held to a bar. The design agent receives the problem and the personas, not wireframes, and produces several distinct directions for you to choose between, structure first and style second. Every direction, token set, and interface pull request is checked against a written design bar and a deterministic detector that names the defaults a generated interface converges on and refuses them. The result reads as designed for this product, and a non-designer gets a designed product.

Evidence, not claims. Every gating command a builder runs writes a receipt with its exit code, the number of tests that ran, and the commit it ran on. A pull request does not reach its merge gate on a failed, stale, or zero-run receipt. The reviewer is handed every change that eases a gate (a skipped test, a loosened check, an edited fixture) and must answer each one. The product is the proof: a user-visible story is done when the real product on real inputs shows what you asked for.

Specialists always on. Auth, security, compliance, accessibility, performance, observability, resilience, and the rest are not phases. Each is a vertical agent dispatched when a change touches its area, consulted when an artifact needs it, and able to block only on a critical finding in its own domain. Billing and multi-tenancy join for a SaaS product, App Store review for a mobile one, internationalization when reach is global.

Minimal, deliberate gates. The only decisions that require you are the brief, the direction review, the scope review, a risky merge, and the production release. An open gate holds only the work that depends on it. Routine pull requests merge on their own. Agents never stop mid-task to ask a question.

Process that fits the product. A landing page does not get the SaaS lifecycle. Springer scales the phase set, the backlog caps, the architecture depth, and the pull request unit to what you are building, and a brief that describes a brochure site runs as one.

A harness that improves under a budget. Every run ends with a retrospective that lists what it learned and which rules it never used. A repeated mistake adds a check a script can run, not a paragraph of instructions, and the harness is measured by one figure: product checks passed per hundred agent dispatches.

Your tools, your machines. Your coding agent subscription, your source host, your notification channels. Staging stays yours: each project deploys to it the way it already does. Continuous integration runs on the machine Springer runs on. There is no cloud CI bill and no vendor between you and your code.

## What you do, in order

1. Run the onboarding once.
2. Open the TUI, create a project, write the brief. The chat line interviews you if you prefer talking to typing. If you only have an idea, Springer researches the market and drafts the brief for you to confirm.
3. Start the run. Springer writes the requirements, proposes architecture options for anything you did not pin, and renders three design directions as clickable mockups.
4. Direction review, one sitting. Answer the intake questions, pick the architecture choices, pick a design direction, write notes on its structure. Springer applies the notes, freezes the structure, builds the design system as code, and writes the screen specs.
5. Scope review, one sitting. Springer proposes an MVP line through the backlog. Move it, answer the open assumptions, submit.
6. Springer builds. The walking skeleton first, then feature by feature. Routine pull requests merge on their own. A risky one waits for you, and you answer it from the TUI or by replying to the notification with a number.
7. Release. Production deploys always wait for you. One click.

Everything between those points is observation. The run screen shows what is in flight, what it costs, and what is waiting.

## Install

Springer runs on an always-on machine: a Mac mini, a NUC, or one of your Linux boxes. It needs Python 3.12, Node 22, pnpm, git, Docker, and Claude Code logged in with your subscription. The GitHub CLI, logged in, is needed only for a project you switch to GitHub pull requests.

```bash
pipx install springer-harness
springer onboard
```

Onboarding is one guided flow. It asks for your coding agent provider and checks its login, your source host, whether you want a tracker projection, which notification channels to use, and which optional tools it found. It installs the daemon as a service and opens the TUI.

Optional tools, each detected and used when present: the Playwright CLI for screenshots, the impeccable engine for the design detector, the ui-ux-pro-max catalog for design directions, Maestro for mobile end-to-end tests, Android emulators on a Linux staging box, a Mac on the farm for iOS simulators.

## The brief

The brief is one file, docs/brief.md in your project, with a short header and prose sections. The TUI edits it. The header carries the facts Springer needs: which surfaces (web, mobile, api, cli), whether there is a backend, whether there are accounts for one or many organizations, whether it charges money, whether it is for you, a team, or the public, where it deploys (cloud or self-hosted), any architecture decisions you want taken as given, and how much you want to be asked.

The sections are the product: the problem, the users, the core flows (each with a trigger, steps, an outcome, and whether it is critical), what you are not building, how you will know it worked, constraints, design preferences, and anything you already have.

Core flows are the part to get right. Each one becomes an epic, the simplest critical flow becomes the first thing built end to end, and the critical flags decide where the MVP line lands.

If you do not know the users or the flows yet, write the Idea section only and choose Run discovery. Springer researches the market, mines reviews and forums, builds personas, sizes the opportunity, and writes the brief sections as proposals with a go or no-go recommendation. You confirm or edit each section before the run starts.

Check brief runs before you can start. It blocks on a flow with no outcome, a user that appears nowhere, or a decision it cannot match, and it warns on thin sections.

## The workflow

Springer follows one path. It is opinionated on purpose, because the path is what lets the agents run without asking.

| Step | What happens | You |
|------|--------------|-----|
| Brief | You write it, or discovery drafts it | Write, confirm, start |
| Requirements | PRD, stories, acceptance criteria, non-functional requirements, definition of done | None |
| Direction review | Architecture options and three design directions, side by side | One sitting: pick, answer, write structure notes |
| Structure pass | Your notes applied to the chosen direction, structure frozen | Confirm only if you gave notes |
| Architecture lock | ADRs for the irreversible decisions, a list of accounts and keys only you can provide | Provide them when asked |
| Design system | Tokens as code, components, patterns, rendered and checked against the design bar | None, or a taste review if you turned variants on |
| Screen specs | Every screen, every state | None |
| Scope review | Backlog with a proposed MVP line and the assumptions made | One sitting: move the line, answer |
| Walking skeleton | The primary flow end to end on staging | None |
| Features | One at a time, test first, reviewed by the specialists the change touches | Risky merges only |
| Release | Promote staging to production, submit to the stores | One click |
| Retrospective | What the run learned, which rules it never used | Promote rule changes if you want them |

Under the default autonomy level you touch the keyboard five times. Under the ask-me-everything level, every gate pauses. Under the only-stop-for-risk level, even the structure pass runs on your written notes alone.

## What safe means

A pull request merges on its own only when the tests it was required to write ran and passed, with the evidence recorded by a script rather than claimed by the agent, the code reviewer approved, the specialists for the areas the change touches found nothing critical, and the change is routine. Routine means it does not touch auth, sessions, permissions, tenancy, a destructive migration, a new dependency, payments, personal data, secrets, uploads, or the build conventions. A change that touches one of those waits for you, and only the work that depends on it waits with it. Everything else keeps going.

Agents do not stop to ask. A reversible decision is taken by default, written down, and shown to you at the next review. An irreversible one never reaches an agent without your answer. A builder that would otherwise ask is restarted with the instruction to take the default and continue.

A generated interface is held to a written design bar and a deterministic detector, so it does not come back as the default kit every model converges on. The design gates stay with you because taste is the one thing a loop does not improve.

## The TUI

Four screens and a chat line.

Projects: every registered project and its status.

Brief: the editor, the facts panel, the interview, the critique.

Backlog: the epic, feature, story tree and the board, the dependency graph, the MVP line, and the risk tag on each item. Editable where you are allowed to act. This is the backlog, with no tracker required.

Run: the active phase, every unit in flight with its agent, model, elapsed time, context used, and cost, the open gates as cards with the recommended option first and the consequences stated, a feed of the routine decisions taken since you last looked, and the controls to cancel, re-dispatch, or pause.

The chat line takes plain requests on every screen: defer billing to the second release, why is this pull request waiting, switch the reviewer model, send gate notifications to Telegram too. Anything that changes scope or configuration asks you to confirm and is logged.

A design review opens your browser on a page the daemon serves, because mockups and comps do not fit in a terminal.

## Bring your own tools

Springer's agents and skills are fixed. What they run on is yours.

| Slot | Choices |
|------|---------|
| Coding agent | Claude Code on your subscription. Other agents can be added as reviewers |
| Source host | Local merges (the default), GitHub (free tier works, Actions optional), GitLab, Forgejo |
| Backlog | Files plus the TUI board, or a one-way projection to Linear, GitHub Projects, or Jira |
| Notifications | Desktop, Slack, Telegram, Discord, email. Reply with a number to answer a gate |
| Deploy target | Cloud (Vercel, Supabase) or self-hosted (one VPS, Compose, Coolify or Dokploy) |
| Design tools | Playwright, impeccable, ui-ux-pro-max, Claude Design, Figma |

Continuous integration runs on the Springer machine. Every gating command writes a receipt with its exit code, test count, and commit, and the harness posts the result to the pull request as a status. There is no cloud CI bill.

## What it builds

A TypeScript monorepo. Next.js for the web app, Expo for the mobile app, shared packages for the design system, feature logic, API, database schema, and types. The stack and deployment defaults are chosen by the deploy profile and anything you pinned in the brief. The generated code follows a strict lint, type, and boundary configuration that the agents cannot loosen, and every screen is built from the design system the human approved.

## Where things live

| Thing | Place |
|-------|-------|
| Your project | Its own git repository with the Springer runtime inside it |
| The brief | docs/brief.md |
| Readable documents | docs/ (requirements, decisions, design, backlog, discovery) |
| Run history | runs/<run-id>/, the typed artifacts and the append-only log |
| The harness | One daemon under ~/.springer serving every project |
| Secrets | The operating system keyring. Builders see test values only |

## Cost

Springer runs on your Claude Code subscription. The harness watches the usage window, slows down as it fills, and sleeps to the reset rather than failing. Mechanical work runs on the smallest model that can do it. The run screen shows what each unit would cost at list price so you can see where the budget goes. Staging runs on hardware you already own.

## Frequently asked questions

Do I have to write the whole brief before anything happens? No. Start with the problem and one flow, start the run, and the interview and the intake questions find the rest. Or start from an idea and let discovery draft it.

What if I know exactly what stack I want? Pin it in the brief. Springer treats pinned decisions as given and only proposes options for what you left open.

What if I disagree with a design direction? Pick the closest one and write structure notes. If none fit, say so at the review and Springer generates three more.

Can I use my existing repository? Yes. Adopt it, and the default lane becomes polish: one issue in your words becomes one reviewed pull request.

What happens when a build fails? The failure is classified first. A platform glitch is retried, a context overflow gets a narrower brief, a real defect gets two bounded attempts with a fresh agent, and anything still open is adjudicated and shown to you.

Can I watch it work? Yes. The run screen streams every session. You can also leave it running overnight and read the digest in the morning.

Does it ever push to production without me? No.

## Status

The runtime (27 agents, 202 skills, schemas, references, evals) is complete and has driven projects from the in-session harness. The standalone harness daemon and the TUI are under construction on the harness branch. The build plan and the state model are in the design notes alongside this file.

## License

MIT.
