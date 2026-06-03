---
name: spgr-run-submission-checklist
description: Produce a pre-submission checklist report that verifies a release build against the App Store and Google Play technical, content, and policy requirements before the binary is submitted, with a pass or fail status per item across iOS and Android, the common rejection causes checked explicitly, and a READY or BLOCKED verdict that gates submission on any failed required item. Use when the App Store Agent must confirm a release build is submission-ready before it goes to Apple or Google review, or when the Mobile Developer or DevOps agent needs the submission posture verified against the listing, the privacy manifest, and the platform-console configuration before a release proceeds.
---

# run-submission-checklist

## Purpose

App Store review takes one to three days for Apple and one to seven days for Google. A rejected submission burns that time and slips the release date, and most rejections are preventable. Run the pre-submission checklist as a gate so the common rejection causes are caught before submission rather than after.

Operate in gate mode. Check every required item across both platforms, record a pass or fail per item with evidence, and return a binary verdict. BLOCKED on any failed required item. READY only when every required item for the target platform passes. Do not edit the listing, the manifest, or any other agent's artifact. Where a fix belongs to another agent, route it through a consultation with spgr-tag-vertical-agent rather than changing their work directly.

## Inputs

| Field | Description |
|-------|-------------|
| `release-build` | Release archive under audit, IPA for iOS or signed AAB for Android |
| `listing-content` | App Store or Google Play listing content from the listing artifact |
| `privacy-manifest` | Privacy manifest artifact (iOS) and Data Safety form state (Android) |
| `design-review-clearance` | HIG review clearance (iOS) and Material review clearance (Android) |
| `console-config` | App Store Connect or Google Play Console configuration for the release |
| `target-platform` | `ios`, `android`, or both, selecting which checklist sections apply |

## Outputs

| Artifact | Description |
|----------|-------------|
| `submission-checklist-report` | Audit report envelope carrying per-item pass or fail status with evidence, organized by platform section, plus a READY or BLOCKED verdict. Written via spgr-write-artifact and validated inline with spgr-validate-artifact |

## Procedure

1. Read the inputs. Pull the build, listing, privacy manifest, design-review clearance, and console configuration with spgr-read-artifact, and read the build archive and any pipeline validation logs with spgr-read-file. If a required input for the target platform is missing or contradictory, raise spgr-escalate with the precise list of what is missing and stop. Do not assume a default and do not fill the gap.

2. Confirm automated technical validation ran in the release pipeline. iOS runs `xcrun altool --validate-app` (or the Xcode Organizer validate-app step) and Android runs `bundletool` validation. Read the pipeline result. If validation did not run or did not pass, record a fail and route the fix to the DevOps agent through spgr-tag-vertical-agent.

3. Run the iOS checklist when the target platform includes iOS. Record a pass or fail with evidence for each item. Archive validates with no warnings. Privacy manifest present and validates. All required entitlements declared. No private API usage. Screenshots uploaded for every required device class. App Review notes written. Test account credentials present in the review notes when the app requires login. Age rating set from the content questionnaire and matching the actual content. HIG review cleared.

4. Run the Android checklist when the target platform includes Android. Record a pass or fail with evidence for each item. AAB signed with the release key. Target SDK level meets the current Google Play minimum for the submission date. Data Safety form complete and submitted. Content rating questionnaire complete. All required screenshots uploaded. Material review cleared.

5. Run the cross-platform checklist for every target platform. App version number incremented above the last submission. Release notes written. No placeholder content anywhere in the listing or build. Test account credentials provided when the app requires login.

6. Apply the gate. Set the verdict to BLOCKED if any required item failed, and list each blocking item with the specific reason and the owning agent. Set the verdict to READY only when every required item for the target platform passed. The age-rating accuracy check, the login test-credential check, and the Android target-SDK check are policy-violation causes, so a fail on any of them is always blocking.

7. Write the report with spgr-write-artifact and validate it inline with spgr-validate-artifact. Record the verdict and its driver with spgr-log-decision. If the verdict is BLOCKED, notify the requesting agent through the report and tag each owning agent with spgr-tag-vertical-agent so the blocking items are routed for fix.

## Notes

- Output type is an audit report (run-* findings) written as an envelope artifact. Its content schema is registered in a later increment, so envelope-only validation applies for now, which still checks the header, confidence map, decision log, and version.
- A failed required item carries the `needs-human-input` or `proposed` confidence signal as appropriate. A READY verdict is `confirmed` only after spgr-validate-artifact passes.
- This skill is a gate, not an editor. It never modifies the listing, the privacy manifest, the build, or another agent's artifact. Remediation always flows to the owning agent through spgr-tag-vertical-agent.
- The Android target-SDK minimum advances annually, so resolve it against the submission date rather than against a fixed value.
