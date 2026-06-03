---
name: spgr-run-hig-review
description: Produce a HIG review report that checks an iOS app against Apple's Human Interface Guidelines, recording findings by severity (rejection risk, conformance issue, advisory) with the screen and component affected and a remediation per finding, and returning a PASS or GATE verdict that blocks submission on any rejection-risk violation. Use when the App Store Agent must confirm an iOS build conforms to platform conventions before App Store submission so a HIG violation does not trigger a review rejection, or when the Mobile Developer or QA agent needs HIG conformance checked against the screen inventory before a release proceeds.
---

# run-hig-review

## Purpose

Check an iOS app against Apple's Human Interface Guidelines and catch both the violations that cause App Store review rejection and the ones that make the app feel un-iOS, before submission. Apple enforces HIG conformance through App Review, so a violation found after submission costs days or weeks of resubmission cycle. Operate as the App Store vertical in auditor and gate mode. Set a blocking threshold, score each finding by severity, and return a verdict that blocks the submission gate on any rejection-risk violation. Recommendations to the Mobile Developer flow through a consultation rather than a direct edit of their code or screens.

## Inputs

| Field | Description |
|-------|-------------|
| `screens` | App screenshots or screen recordings covering all flows |
| `xcode_project` | Xcode project path for technical inspection (private API use, dynamic type, keyboard avoidance) |
| `component_inventory` | UIKit and SwiftUI component inventory, including SF Symbols used and their semantic intent |
| `pattern_library` | The living HIG violation pattern library artifact, holding violations Apple has cited in prior reviews |

## Outputs

| Artifact | Description |
|----------|-------------|
| `hig-review` | Review report envelope listing findings by severity (rejection risk, conformance issue, advisory), each with the screen and component affected, the HIG rule cited, and a remediation, plus a PASS or GATE verdict |
| `consultation` | Consultation to the Mobile Developer carrying the remediation set, routed via spgr-tag-vertical-agent |
| `pattern_library` (updated) | New checklist entries appended when App Review cites a violation, so future reviews catch it |

## Procedure

1. Read the inputs with spgr-read-file for screens, the Xcode project, and the component inventory, and spgr-read-artifact for the HIG violation pattern library. If screens or recordings do not cover all flows, or the component inventory is missing, raise spgr-escalate with the precise list of missing flows or inventory and stop. Do not infer conformance on an unseen flow.
2. Check for rejection-risk violations: use of private APIs, non-standard navigation that contradicts the back gesture, tab bar, or sheet presentation conventions, missing keyboard avoidance, broken multitasking, and the App Review patterns recorded in the pattern library. Record each with the screen, the component, the HIG rule, and the remediation.
3. Check SF Symbols usage against Apple's semantic documentation. A system icon used for a purpose inconsistent with its documented meaning is a conformance issue. Record the icon, the screen, and the documented meaning it violates.
4. Check dynamic type support. Confirm every text element scales with the system font size setting. Text that does not scale is a conformance issue. Record the screen and component.
5. Check the remaining platform conventions for conformance issues (non-standard button styles, missing haptic feedback in expected contexts) and capture advisory items that improve the iOS experience without being a violation.
6. Assign a verdict. Apply the blocking threshold: any open rejection-risk finding sets the verdict to GATE and blocks submission. Zero open rejection-risk findings sets the verdict to PASS, with conformance issues and advisories carried as non-blocking. State the threshold in the report.
7. Write the report with spgr-write-artifact and run spgr-validate-artifact inline. Log the verdict with spgr-log-decision.
8. Route the remediation set to the Mobile Developer as a consultation through spgr-tag-vertical-agent. Do not edit the developer's screens or code directly.
9. On a GATE verdict, call spgr-notify-human so the blocking violations reach the submission gate owner.
10. When App Review later cites a violation, append it to the HIG violation pattern library as an explicit checklist item with spgr-version-artifact, so the next review catches it.

## Notes

- Output type: this is an audit/review report envelope artifact (`hig-review`) written via spgr-write-artifact. Its content schema is registered in a later increment, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, version).
- Gate behavior: the verdict blocks the submission gate on any rejection-risk finding. Conformance issues and advisories are non-blocking and do not change a PASS verdict.
- The App Store vertical is an auditor and gate here. A recommendation to a horizontal agent flows through the registered consultation artifact, not a direct edit.
- The HIG review covers the UX and platform-adherence aspects of App Review. Crashes, incomplete functionality, misleading metadata, and privacy violations are handled by other App Store skills and are out of scope for this report.
