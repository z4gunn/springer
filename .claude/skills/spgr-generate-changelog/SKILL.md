---
name: spgr-generate-changelog
description: Maintain the project CHANGELOG.md in Keep a Changelog format by parsing conventional commits between the last release tag and HEAD into a draft of release-by-release entries, sorted into Added, Changed, Deprecated, Removed, Fixed, and Security, with breaking changes called out and a migration note, written from the consumer's perspective for the Documentation Agent to review before release. Use when the Documentation Agent maintains the changelog as changes merge to main, or when the DevOps Agent finalizes a release by promoting the Unreleased section to a dated version at version bump and tag time.
---

# generate-changelog

## Purpose

Maintain `CHANGELOG.md`, the curated bridge between git history and human understanding. A `git log` is complete but unsorted, and a reader upgrading a dependency, reviewing release scope, or tracing project history needs the structured record instead. This skill parses conventional commits between the last release tag and HEAD into a draft following the Keep a Changelog format, so the Documentation Agent refines a starting point rather than writing from a blank file. Every entry describes a behavior change a consumer would notice, not an implementation detail.

## Inputs

| Field | Description |
|-------|-------------|
| `commit-history` | Conventional commits between the last release tag and HEAD, read with spgr-read-file or git. The commit type (`feat`, `fix`, and so on) and any `BREAKING CHANGE` footer drive section placement. |
| `api-changelog` | The consumer-facing API changelog from spgr-generate-api-changelog, folded in for any API-touching change so the changelog and the API changelog agree. |
| `breaking-change-list` | The set of breaking changes for the release, each needing a prominent callout and a migration note. |
| `existing-changelog` | The current `CHANGELOG.md`, read with spgr-read-file so the update reconciles against existing entries rather than overwriting them. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `CHANGELOG.md` (source code) | The maintained changelog in Keep a Changelog format. The `## [Unreleased]` section is updated as changes land. At release time it is renamed to `## [X.Y.Z] - YYYY-MM-DD`. Entries are sorted into Added, Changed, Deprecated, Removed, Fixed, and Security, only sections with content are kept, breaking changes are marked prominently with a migration note, and each version links to its full diff on GitHub. Written with spgr-write-file. |

## Procedure

1. Read the existing `CHANGELOG.md` with spgr-read-file. Treat its versions, entries, section headers, and diff links as the baseline to reconcile against, not a blank slate to overwrite. If no changelog exists, start a Keep a Changelog skeleton with an `## [Unreleased]` section.

2. Collect the conventional commits between the last release tag and HEAD. Parse each commit's type and subject. Skip commits that carry no consumer-visible change (for example `chore`, `ci`, `test`, `docs` on internal files, and pure formatting).

3. Map each remaining commit to a Keep a Changelog section by type. `feat` to Added. `fix` to Fixed. A documented behavior change to Changed. A deprecation to Deprecated. A removal to Removed. Any security fix to Security, with a CVE reference when one applies.

4. Rewrite each entry from the perspective of a consumer of this project's API or library. Describe the behavior change, not the code change. "Fixed a bug" is not an entry. "Fixed: user profile updates no longer fail silently when the email address is unchanged" is an entry. Fold in the matching `api-changelog` wording for any API-touching change so the two records agree.

5. For every commit with a `BREAKING CHANGE` footer and every item in `breaking-change-list`, mark the entry prominently and attach a migration note that tells the consumer what to change. A breaking change without a migration note is incomplete.

6. Write the entries into the `## [Unreleased]` section, under section headers in the fixed Keep a Changelog order, dropping any section that has no content. Keep entries concise and grouped by section, not by commit order.

7. At release time only, when invoked by the DevOps Agent at version bump and tag, rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD` with the release version and date, open a fresh empty `## [Unreleased]` section above it, and add or update the GitHub diff link for the new version (and the `[Unreleased]` compare link).

8. If the commit history is empty, the last release tag cannot be resolved, a breaking change in `breaking-change-list` has no migration note, or a security fix cannot be classified, stop and raise spgr-escalate with the precise list of what is missing. Do not invent an entry, a version, or a migration note.

9. Write the reconciled `CHANGELOG.md` to disk with spgr-write-file, honoring the read-before-write contract. Record what was drafted, any commits skipped as non-consumer-visible, and any escalation with spgr-log-decision so the reasoning is traceable in the same commit.

## Notes

- The output is source code (`CHANGELOG.md`), verified by the parse-and-reconcile procedure in this skill and by CI, not by an envelope schema. There is no registered content schema for the changelog yet, so its content-schema registration arrives in a later increment and envelope-only validation does not apply to this file output.
- This skill produces a draft. The Documentation Agent reviews and refines wording before a release is cut. The automation removes transcription, not editorial judgment.
- The `[Unreleased]` section is updated continuously as features merge to main. The rename to a dated version in step 7 happens only at release, triggered by the version bump and tag.
- API-touching changes are recorded both here and in the API changelog from spgr-generate-api-changelog. Reconcile against that record rather than writing a second, divergent description.
