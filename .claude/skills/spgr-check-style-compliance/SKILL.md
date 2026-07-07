---
name: spgr-check-style-compliance
description: Produce a style-compliance findings list for a PR diff, covering only style concerns linters cannot catch (semantic naming, comment quality, test naming, project idioms), every entry a non-blocking suggestion. Use when the code-reviewer agent has a diff that passed lint and format and needs the residue of semantic style review.
---

# check-style-compliance

## Purpose

Catch the narrow category of style issues that automated tooling cannot reach, and nothing more. Linters and formatters already enforce mechanical style, so this skill targets only what needs semantic understanding: naming that does not match the project's noun-verb pattern, comments that mislead or restate the code, test names that do not describe behavior, and breaks from project-specific idioms. Every finding is a non-blocking suggestion. Style is never a merge gate once automated tools have passed, because review time is expensive and lint time is cheap.

## Inputs

| Field | Description |
|-------|-------------|
| `pr_diff` | The PR diff under review, read via spgr-read-file. |
| `style_guide` | The project style guide covering naming conventions, comment standards, and test naming patterns, read via spgr-read-file. Skip the check and note the gap if absent. |
| `lint_status` | Confirmation that the linter and formatter already passed on this branch. Read the lint posture via spgr-lint-code and the format state via spgr-format-code if not supplied. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `style-compliance` | A findings list of style-guide violations that automated tooling cannot catch, every entry a non-blocking suggestion with a specific constructive rewrite. |

## Procedure

1. Confirm the linter and formatter have passed for this branch. If they have not, stop and return an escalation via spgr-escalate stating that automated style enforcement must pass before semantic style review begins, because this skill does not duplicate linter rules.
2. Read the PR diff and the project style guide. If no style guide exists, record a single finding that the project has no style guide to check against and end, since there is no contract to measure the diff by.
3. Walk the diff for the non-automatable categories only: semantic naming against the project's naming pattern, comment quality, test naming patterns, and project-specific idioms. Skip any concern a linter rule could catch. For TypeScript or JavaScript, the bar for these categories is the naming conventions and the reviewer-judgment rows of the enforcement split in `.claude/references/typescript-standards.md`, which is the project style guide for that code.
4. For each finding, write a specific constructive suggestion that names the current symbol, the proposed change, and the pattern it aligns to, for example consider renaming handleData to parseUserProfile to match the noun-verb pattern used in adjacent handlers. Do not file vague feedback such as bad naming.
5. Mark every finding non-blocking. Do not raise any finding to blocking and do not gate the merge on style.
6. For any issue that recurs across multiple PRs, do not file it again as a review finding. Instead recommend a new linter rule or plugin to catch it at lint time, and record that recommendation via spgr-log-decision so the recurring class moves out of review.
7. Write the findings list via spgr-write-artifact, then version it via spgr-version-artifact. Validate inline via spgr-validate-artifact.

## Notes

- The style-compliance findings type is not yet in the registered schema registry under schemas/. Write it via spgr-write-artifact with its registered schema added in a later increment, and validate through spgr-validate-artifact against the registry rather than inlining a field list here.
- Every finding is non-blocking by construction. This skill produces zero merge gates. Human review remains for correctness and architecture, not style policing.
- Maintain the living list of recurring non-automatable style issues across runs via spgr-log-decision, and periodically check whether a new linter plugin can absorb an item so it leaves review entirely.
