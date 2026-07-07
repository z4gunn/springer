---
name: spgr-write-contributing-guide
description: Generate the project CONTRIBUTING.md, the contract for how contributions are reported, branched, committed, reviewed, and merged, plus a PR template checklist that surfaces its requirements. Use when the Documentation Agent stands up the contribution contract, or when the PR process, code standards, or merge requirements change.
---

# write-contributing-guide

## Purpose

Produce the CONTRIBUTING.md that states contribution expectations up front, so a new contributor can report a bug, propose a feature, branch, commit, open a PR, and get it merged without guessing at the process. The cost of an absent or vague guide is PRs that arrive in the wrong form and contributors who feel corrected after the fact rather than informed before it. As a Documentation vertical output this is a source file, not an envelope artifact: write the files via spgr-write-file and prove them with CI, then record the consultation back to the human or owning agent.

Calibrate every section to the contributor audience. An open-source library opens contribution to strangers and needs a Code of Conduct, a discussion-first feature path, and a stated first-review SLA. An internal product repository assumes a known team and can be terser on conduct and reporting. Read the audience from the project before writing, and do not ship a generic template.

## Inputs

| Field | Description |
|-------|-------------|
| `pr-process` | Branch naming, commit convention (Conventional Commits), PR template sections |
| `code-standards` | Testing requirements, linting, formatting expectations |
| `review-process` | Who reviews, response-time expectations, what a contributor should expect |
| `issue-process` | How bugs and features are reported, required information per report |
| `governance` | Who can merge, required approvals, the release process |
| `contributor-audience` | Open-source external contributors or internal team, which sets the calibration |
| `dev-setup-source` | The local development instructions to link to or embed (for example the README setup section) |

## Outputs

| Artifact | Description |
|----------|-------------|
| `CONTRIBUTING.md` | The contribution contract, written via spgr-write-file |
| `.github/PULL_REQUEST_TEMPLATE.md` | PR checklist that mirrors the guide's PR and merge requirements, written via spgr-write-file |
| `consultation` | Recommendation routed to the owning agent or human via spgr-tag-vertical-agent, with the file paths and any blocking gaps |

## Procedure

1. Read the inputs. Pull the PR process, code standards, review process, issue process, and governance from the project. Use spgr-read-artifact for any upstream artifact and spgr-read-file for existing config (README, lint config, CI workflow, commit hooks). Determine the contributor audience and let it set the depth of the Code of Conduct and reporting sections.
2. If a required input is missing or contradictory (for example no commit convention is set, no reviewer is named, or the release process is undefined), stop and raise spgr-escalate with the precise list of what is missing. Do not invent a process or fill the gap with a default.
3. Write CONTRIBUTING.md covering, in order: Code of Conduct (a reference to a CoC file or a brief statement), how to report bugs (the issue template and the exact information required), how to propose features (discussion-first versus PR-first, chosen from the issue process), development setup (link to or embed the dev-setup source rather than duplicating it), branch naming and commit conventions (reference Conventional Commits), PR requirements, the review process, and merge requirements.
4. State PR and merge requirements specifically, not vaguely. Replace "all tests must pass" with the concrete rule, for example "new features require unit tests and at least one integration test, CI must be green before review is requested, and the PR needs N approving reviews with no unresolved comments before merge." Pull the exact thresholds from the code-standards and governance inputs.
5. Set review expectations in time. State a first-review SLA drawn from the review process (for example "typical first review within 2 business days") so contributors do not re-ping immediately. State who reviews and what the contributor should expect at each round.
6. Write `.github/PULL_REQUEST_TEMPLATE.md` so the guide's PR requirements appear in the PR creation form. Mirror the CONTRIBUTING.md PR and merge requirements as a checklist (tests added, CI green, linked issue, conventional commit title, no unresolved comments). Keep the two in sync: the template is the enforcement surface for the guide's contract.
7. Verify both files render and the template is picked up. Confirm Markdown is well formed and the PR template path is exactly `.github/PULL_REQUEST_TEMPLATE.md`. Run spgr-run-tests or the CI docs job if one exists. Re-read for authoring voice before handing off.
8. Route the result through a consultation with spgr-tag-vertical-agent to the owning agent or human, listing the written file paths and any deferred decision. Log the calibration choice and any non-obvious process decision with spgr-log-decision so it is traceable.

## Notes

- Output type: source/config (CONTRIBUTING.md plus the PR template), not an envelope artifact. There is no content schema for this output. Verification is by spgr-run-tests or CI, and the recommendation is delivered through the consultation artifact via spgr-tag-vertical-agent, which spgr-validate-artifact validates in full against the registered consultation content schema.
- Do not duplicate the local development setup. Link to or embed the dev-setup source so the setup steps live in one place and stay current.
- The PR template and the CONTRIBUTING.md PR requirements are one contract in two files. When one changes, change both in the same commit.
- Keep contribution policy advisory to other agents. Where merge governance touches another agent's domain (for example the code-reviewer's approval rules), route the recommendation through the consultation rather than editing that agent's artifact.
