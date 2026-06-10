---
name: spgr-bump-version
description: Increment the project version following semantic versioning and update every version reference across the codebase atomically (package manifests, mobile version string and build number, API headers, docs), then land it as a dedicated `chore(release): bump version to X.Y.Z` commit. Use when the DevOps Agent prepares a release and needs the version raised consistently with the bump type derived from the CHANGELOG.md unreleased section, or when a pre-release build (TestFlight or Firebase) needs a valid prerelease version.
---

# bump-version

## Purpose

Raise the project version and update all version references in one operation so the binary, the package manifest, and the docs never disagree. The bump type is not chosen by hand. Derive it from the unreleased section of CHANGELOG.md against semver rules, update every registered version-reference file, then commit the change on its own. The version-reference file list is fixed at project init, so this skill reads that list rather than scanning the tree each run.

## Inputs

| Field | Description |
|-------|-------------|
| `current_version` | The current version string in semver form (for example `1.3.2`). |
| `release_type` | Optional override of `major`, `minor`, `patch`, or `prerelease`. Omit to derive from the changelog. |
| `version_reference_files` | The list of files holding version references, established at project init. |
| `changelog_path` | Path to CHANGELOG.md, parsed for the unreleased section. |
| `is_mobile` | Whether the project carries a mobile version string plus a build number. |

## Outputs

| Artifact | Description |
|----------|-------------|
| Updated version references | Every file in `version_reference_files` set to the new version string, written via spgr-write-file. |
| Mobile build number | When `is_mobile`, the monotonic build-number integer incremented alongside the semver string. |
| Release commit | A dedicated commit `chore(release): bump version to X.Y.Z`, never bundled with feature changes. |

## Procedure

1. Read the changelog via spgr-read-file and parse the unreleased section. Map entry categories to a bump type: any breaking or removed change derives `major`, a new backward-compatible feature derives `minor`, a bug fix alone derives `patch`. If `release_type` is supplied, use it but record the derived type in the decision log so an override is visible.
2. Compute the new version from `current_version` and the bump type per semver. For a prerelease, produce a valid prerelease identifier (for example `1.4.0-beta.1`) and use it for TestFlight or Firebase distribution builds rather than a production tag.
3. Read each file in `version_reference_files` via spgr-read-file and confirm the located version string matches `current_version` before replacing it. A mismatch means the reference list is stale or the project drifted, so escalate via spgr-escalate rather than overwriting an unexpected value.
4. Write the new version into every reference file via spgr-write-file. When `is_mobile`, increment the build-number integer in the same operation so the user-visible string and the build number move together.
5. Stage only the version-reference files and create the dedicated commit `chore(release): bump version to X.Y.Z`. Do not include feature or source changes in this commit, so the history separates release churn from feature work.
6. Verify the commit through spgr-run-tests or CI. Record the bump type, derived-versus-overridden source, and resulting version with spgr-log-decision.
7. Escalate via spgr-escalate when the changelog has no unreleased entries, when entry categories conflict so no single bump type follows, when a reference file does not contain the expected current version, or when the computed version already exists as a tag.

## Notes

- Output type is SOURCE or CONFIG. This skill edits version-reference files in the codebase and lands a dedicated commit. It does not emit an envelope artifact, so spgr-validate-artifact does not apply. Verification is by spgr-run-tests or CI on the resulting commit.
- Semver mapping: breaking API change to `major`, new backward-compatible feature to `minor`, bug fix to `patch`. The type follows the changelog content, not a manual pick.
- Mobile carries two version concepts. The user-visible semver string and the monotonically increasing build-number integer update in the same operation.
- The version bump is always its own commit, never combined with feature changes.
