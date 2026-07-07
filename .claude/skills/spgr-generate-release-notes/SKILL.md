---
name: spgr-generate-release-notes
description: Produce user-facing release notes that translate the technical changelog into customer-benefit language across the in-app what's-new panel, email announcement, store notes, and help-center article. Use when the Documentation Agent prepares a release, or when a developer or PM agent needs customer-facing notes from the confirmed changelog.
---

# generate-release-notes

## Purpose

Write release notes for users, not for developers. The changelog records every technical change for contributors. Release notes are the customer-facing translation of that record, carrying only what a user can act on: features they can now use, changes that alter an existing workflow, and fixes to problems they reported. The contract is audience separation. A release note must never expose an internal refactor, a dependency upgrade, or a developer-tooling change, and it must lead with the benefit a user gets rather than the mechanism that delivers it.

This skill is owned by the Documentation Agent operating as a consultant to the release flow. The notes are content files, one per channel, written with spgr-write-file, then wrapped in a release-notes envelope artifact via spgr-write-artifact so the release record is traceable and version-tracked.

## Inputs

| Field | Description |
|-------|-------------|
| `changelog` | The confirmed changelog entry for the release, read with spgr-read-artifact, the source list of what changed |
| `prd-features` | User-facing feature descriptions from the PRD, read with spgr-read-artifact, the source of benefit language |
| `workflow-changes` | Known breaking changes or workflow changes that affect existing users |
| `target-channels` | Which channels to produce: in-app, email, app-store, help-center, or a subset |
| `ui-locales` | The set of locales the product UI ships in, used to scope translation |

## Outputs

| Artifact | Description |
|----------|-------------|
| In-app what's-new | 3 to 5 bullets, feature-focused, benefit-led, written as a content file per spgr-write-file |
| Email announcement | Subject line, 2 to 3 feature highlights with screenshot placeholders, link to full notes |
| App Store notes | Highest-value changes within the 4000-character App Store budget |
| Google Play notes | Highest-value changes within the 500-character Google Play budget |
| Help-center article | Full documentation for each newly released feature |
| Release-notes envelope | One envelope artifact via spgr-write-artifact listing the channels produced, the locales, and the source changelog version |

## Procedure

1. Read the changelog with spgr-read-artifact and the user-facing feature descriptions from the PRD. Read the workflow-changes input. These three are the only sources. Do not invent a change that is not in the changelog.

2. Filter the changelog to user-relevant entries. Drop every internal refactor, dependency upgrade, build-tooling change, and developer-only fix. Keep new user-visible features, workflow-altering changes, and fixes to a commonly reported user experience.

3. If the filter leaves nothing user-relevant, or if a target channel is requested with no qualifying content, stop and raise spgr-escalate with the precise gap (for example, app-store notes requested but every change is internal). Do not pad the notes with non-user material to fill a channel.

4. Rewrite each kept entry in benefit-led language. Lead with what the user can now do and why it helps, not with the feature name. Prefer "Export your reports to PDF for easy sharing with stakeholders" over "Added PDF export." For a kept bug fix, name the resolved frustration, for example "Fixed: search results now include items added in the last 24 hours."

5. Produce each requested channel to its constraint:
   - In-app what's-new: 3 to 5 bullets, ranked by user value, the highest-value change first.
   - Email: a subject line, 2 to 3 highlights with screenshot placeholders, and a link to the full notes.
   - App Store: prioritize changes into the 4000-character budget. Include at least one compelling reason to update, since this text is read by a user deciding whether to install the update.
   - Google Play: prioritize into the tighter 500-character budget, same update-reason requirement.
   - Help-center: full feature documentation for each new feature.

6. For each locale in `ui-locales` beyond the default, produce a translated copy of every requested channel so release notes ship in the same locales as the product UI. Where a locale lacks a translation source, raise spgr-escalate naming the missing locale rather than shipping an untranslated note in its place.

7. Write each channel content file with spgr-write-file. Then write the release-notes envelope with spgr-write-artifact and run spgr-validate-artifact inline. Record the channels produced, the locales, and the source changelog version in the envelope.

8. If the changelog and the PRD disagree on whether a feature is user-facing, or a workflow-change input contradicts the changelog, stop and raise spgr-escalate with both sources cited rather than choosing one.

## Notes

- Output type: this is SOURCE content (per-channel note files via spgr-write-file) wrapped in an envelope artifact (the release-notes record via spgr-write-artifact). The release-notes content schema is not registered yet, so spgr-validate-artifact applies envelope-only validation for now, checking the header, confidence map, decision log, and version. Its content schema is registered in a later increment.
- The benefit-language rewrite is a judgment call. Record the kept-versus-dropped decision and the channel-prioritization rationale with spgr-log-decision so a reviewer can see why an internal change was excluded.
- This skill advises the release flow as a consultant. It does not edit the changelog or the PRD. Where a feature in the PRD lacks a corresponding changelog entry, route the gap back through spgr-tag-vertical-agent or spgr-escalate rather than describing a feature the changelog does not confirm shipped.
- Localization scope follows the product UI locales, not a fixed list. A new UI locale added after a release changes the scope of the next release's notes.
