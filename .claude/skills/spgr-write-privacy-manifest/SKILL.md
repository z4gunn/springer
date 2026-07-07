---
name: spgr-write-privacy-manifest
description: Produce the iOS Privacy Manifest (PrivacyInfo.xcprivacy) declaring tracking status, tracking domains, collected data types with purposes, and every Required Reason API with its approved reason code. Use when the App Store Agent prepares an iOS submission, or when a new SDK or Required Reason API requires the manifest regenerated.
---

# write-privacy-manifest

## Purpose

Write the `PrivacyInfo.xcprivacy` file for an iOS app. Apple requires a Privacy Manifest for every app and third-party SDK from Xcode 15 onward, and a missing or inaccurate manifest causes App Store rejection. The manifest declares tracking status, tracking domains, collected data types with usage purposes, and every Required Reason API used with its approved reason code. The App Store Agent owns this output. The Compliance Agent supplies the data classification that drives the collected-data-type declarations through a consultation, and is not edited directly.

This is source output. Write the `.xcprivacy` file with spgr-write-file and verify it in CI, rather than emitting an envelope artifact.

## Inputs

| Field | Description |
|-------|-------------|
| App entitlements and capabilities | The app's declared entitlements, read with spgr-read-file from the project. |
| Third-party SDK inventory | Each included SDK and its own Privacy Manifest, where one exists. |
| Data collection inventory | The data-classification artifact from the Compliance Agent, read with spgr-read-artifact, mapping each collected field to a sensitivity tier. |
| Required Reason API usage | The Required Reason APIs the app calls (`NSUserDefaults`, file timestamp, system boot time, disk space, active keyboard APIs), with the approved Apple reason code for each. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `PrivacyInfo.xcprivacy` | The Privacy Manifest property list, with `NSPrivacyTracking`, `NSPrivacyTrackingDomains`, `NSPrivacyCollectedDataTypes`, and `NSPrivacyAccessedAPITypes`. |
| CI validation step | A `xcodebuild -generatePrivacyReport` step that fails the build when the generated report does not match the declared data types. |

## Procedure

1. Read the data-classification artifact with spgr-read-artifact and the project entitlements and SDK inventory with spgr-read-file. If the data classification is missing or stale, raise a consultation to the Compliance Agent with spgr-tag-vertical-agent rather than guessing the collected data types.
2. Set `NSPrivacyTracking`. Declare `YES` only when the app tracks as defined by App Tracking Transparency, and confirm the ATT prompt is shown before tracking begins. When the app does not track, set it explicitly to `NO`. Never leave it unset.
3. List every tracking network domain in `NSPrivacyTrackingDomains`. This list is required to be non-empty when tracking is `YES` and is omitted when tracking is `NO`.
4. Build `NSPrivacyCollectedDataTypes` from the data-classification inventory. For each collected type, declare its usage purposes, whether it is linked to the user's identity, and whether it is used for tracking. Map each entry to a field in the classification so no collected field is omitted.
5. Build `NSPrivacyAccessedAPITypes`. For each Required Reason API the app calls, declare an approved reason code from Apple's documentation. An API used without a reason, or with the wrong reason, is a rejection risk and is treated as a blocking gap.
6. For each third-party SDK, confirm the SDK ships its own Privacy Manifest so Xcode can aggregate it into the app Privacy Report. When an SDK has no manifest, escalate with spgr-escalate so the SDK author is contacted or the SDK is replaced, and do not declare on the SDK's behalf.
7. Write the `PrivacyInfo.xcprivacy` file with spgr-write-file at the app target root.
8. Add the CI validation step that runs `xcodebuild -generatePrivacyReport` and validates the generated report against the declared data types. The build fails when the report and the manifest disagree.
9. Log the manifest decision and the reason-code choices with spgr-log-decision. Record any unresolved gap (missing SDK manifest, undeclared Required Reason API, missing data classification) as a blocking item before the manifest is treated as confirmed.

## Notes

- Output type: source file (`PrivacyInfo.xcprivacy`) plus a CI verification step, written with spgr-write-file and verified by CI. It is not an envelope artifact, so it does not carry a content schema. The consultation back to the Compliance Agent is the registered artifact, validated in full by spgr-validate-artifact against the registered consultation content schema.
- A collected data type with no source field in the data classification, a Required Reason API with no approved reason code, or an SDK with no Privacy Manifest is a blocking gap. Do not ship the manifest until each is resolved or escalated.
- `NSPrivacyTracking` is never left unset. The default of an unanswered tracking question is a rejection risk, so declare `YES` or `NO` explicitly.
