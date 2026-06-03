---
name: spgr-write-onboarding-guide
description: Write the developer onboarding guide, the document that takes a developer from fresh repository access to a first safe contribution, covering the architecture mental model, local setup, a codebase tour, the development workflow, common gotchas, who-to-ask routing, first-task recommendations, and a first-week onboarding checklist that proves the guide works. Use when the Documentation Agent stands up onboarding for a new project, or when an architecture change, workflow change, or a newly discovered gotcha makes the existing guide stale.
---

# write-onboarding-guide

## Purpose

Write the onboarding guide that compresses the knowledge transfer a new developer would otherwise get through pair programming, repeated questions, and trial and error. Every hour a new developer spends confused about the codebase is an hour they are not productive, and senior developers answer the same questions repeatedly. The guide is written for a developer who is new to this project, not new to programming, so it documents what is specific to this codebase and skips general concepts. The highest-value section is the common gotchas: the non-obvious configuration requirements, counterintuitive test patterns, and historical quirks that trip up experienced developers. The guide also carries a first-week onboarding checklist, so a new developer can verify the guide is accurate by completing real tasks and reporting where it fell short.

## Inputs

| Field | Description |
|-------|-------------|
| `architecture-docs` | Service topology and key design decisions. Read approved ADRs and the system diagram via spgr-read-artifact, and any prose docs via spgr-read-file. |
| `local-dev-setup` | The local development setup produced by scaffold-local-dev-env. Link to it or embed the steps. Read with spgr-read-file. |
| `code-organization` | Module structure, naming conventions, and the important files and directories. Derived by reading the source tree with spgr-read-file and Grep. |
| `development-workflow` | Branching model, PR process, and review expectations. Read from project workflow docs and CONTRIBUTING-equivalent sources with spgr-read-file. |
| `common-gotchas` | Non-obvious behaviors, configuration traps, counterintuitive test patterns, and historical quirks gathered from the codebase, decision logs, and the team. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `onboarding-guide` (source document) | A markdown guide covering the architecture mental model (the top three things to understand first), local environment setup (linked or embedded), a codebase tour (key files, important directories, how to find things), the development workflow (from picking up a story to opening a PR), common gotchas, who-to-ask-about-what routing (which external docs to consult for which concerns, even in a single-developer project), first-task recommendations (good starter areas), and a first-week onboarding checklist. Written with spgr-write-file. |

## Procedure

1. Read the existing onboarding guide with spgr-read-file if one exists. Treat it as the baseline to reconcile against, not a blank slate, so prior wording and accumulated gotchas are preserved.

2. Read the architecture inputs. Pull the confirmed ADRs, tech-stack decision, and system diagram with spgr-read-artifact. If a referenced architecture artifact is missing or still in proposed rather than confirmed state, stop and raise spgr-escalate with the precise list of what is unavailable, since the mental model section must rest on confirmed architecture and not on assumptions.

3. Write the architecture mental model section. State how the system is organized and the top three things a new developer must understand first. Link out to the system diagram and ADRs rather than restating them, so the guide stays current as those artifacts version.

4. Write the local environment setup section. Link to or embed the scaffold-local-dev-env output. Do not duplicate the setup steps in a way that will drift from the source. If the local-dev-setup input is absent, link to where it will live and flag the gap in the who-to-ask section.

5. Write the codebase tour. Name the key files, the important directories, and how to find things, derived from reading the source tree. Keep it to what is non-obvious about this layout, not a generic explanation of the framework's conventions.

6. Write the development workflow section, tracing the path from picking up a story to opening a PR: branch naming, commit discipline, the PR description expectations, and the review gates. Reference the workflow skills by name where they apply (spgr-create-branch, spgr-git-commit, spgr-create-pr) rather than restating their internals.

7. Write the common gotchas section, the highest-value part of the guide. Capture the things that trip up experienced developers: non-obvious configuration requirements, counterintuitive test patterns, and areas with historical quirks. Mine decision logs and prior escalations for the reasoning behind the surprising choices.

8. Write the who-to-ask-about-what section. Route each concern to its owner. In a single-developer project, route to which external docs to consult for which concern, and to the owning vertical agent where a domain has one (for example performance, security, accessibility).

9. Write the first-task recommendations section, naming good starter areas of the codebase where a small, low-risk first change is safe to make.

10. Write the first-week onboarding checklist as a structured task list a new developer completes to verify the guide is working: run the tests, make a small change and open a draft PR, attend or read the architecture review, and any project-specific milestone. Each item is a concrete, checkable task.

11. Write the guide to disk with spgr-write-file, honoring the read-before-write contract.

12. Record the build with spgr-log-decision: what changed since the prior version, which gotchas were added, and any architecture artifact that was unavailable and routed to escalation, so the reasoning is traceable in the same commit.

## Notes

- The output is a source document, verified by a new developer following it during a real onboarding and reporting where they got confused or where information was missing, not by an envelope schema. There is no registered artifact schema for the onboarding guide, so it is written via spgr-write-file and checked by that human follow-through and by CI link checks rather than spgr-validate-artifact.
- Write for a competent developer who is new to this specific project. Do not explain general programming concepts.
- Update the guide in the same change that alters the architecture, the development workflow, or a documented gotcha, so the guide does not drift from the system it describes.
- This skill is owned by the Documentation Agent operating as a vertical consultant. Where the guide needs another agent to confirm a section's accuracy, route the request through spgr-tag-vertical-agent as a consultation rather than editing that agent's artifacts.
