---
name: spgr-create-prototype
description: Produce a clickable prototype artifact that covers the user flows needed for usability testing, with explicit flow coverage, hotspot interactions for every primary navigation path, simulated loading, error, and empty states where the test scenarios require them, a usability testing script, and a findings classification rubric that gates developer handoff. Use when the Design Agent has approved screen specs and defined test scenarios and must validate the design against real users before developer handoff, or when a usability concern needs a testable prototype before code is written.
---

# create-prototype

## Purpose

Produce a clickable prototype artifact that lets a usability test confirm the design solves the user problem before any implementation investment. The prototype is a testing artifact, not a maintained deliverable. It covers only the flows a usability test needs, not every screen. Its job is to surface usability issues while they are still cheap to fix, then feed triaged findings back into the screen specs before developer handoff.

## Inputs

| Field | Description |
|-------|-------------|
| `screen-specs` | Approved screen specs. Read each with spgr-read-artifact. The prototype matches their fidelity and prototypes no screen that lacks an approved spec. |
| `test-scenarios` | The user tasks the prototype must support, defining the flows to prototype and the simulated states that matter. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `prototype` | Envelope artifact written with spgr-write-artifact. Documents flow coverage (the exact flows prototyped), hotspot interactions for every primary navigation path, simulated loading, error, and empty states required by the test scenarios, the usability testing script, and the findings classification rubric and resolution process. |

## Procedure

1. Read the approved screen specs with spgr-read-artifact and the test scenarios. Confirm every flow a test scenario exercises has an approved screen spec behind it. If a required flow references an unapproved or missing screen spec, stop and raise spgr-escalate with the exact missing specs. Do not prototype an unapproved screen.

2. Scope the prototype before building. List the flows to prototype, derived from the test scenarios, and the screens each flow touches. State explicitly which flows are in scope and which are out. The prototype covers the flows usability testing needs, not the full screen set.

3. Specify the hotspot interactions. For every primary navigation path in each in-scope flow, define the hotspot, the source screen, the target screen, and the trigger. Cover each path a test participant would take to complete a task.

4. Specify the simulated states. For each test scenario that depends on a loading, error, or empty state, define how the prototype simulates that state and which screen spec state it maps to. Do not add states the scenarios do not require.

5. Author the usability testing script. For each test scenario, write the participant task wording, the success condition, the screens involved, and the observer prompts. The script is what a facilitator reads in a session, so keep tasks neutral and unleading.

6. Record the findings classification rubric and resolution process in the artifact. Classify every finding as critical, moderate, or minor by the rules in Notes, and state the resolution path for each class so handoff cannot proceed with an open critical finding.

7. Assemble the prototype artifact and write it with spgr-write-artifact. Run spgr-validate-artifact inline. On a validation failure, correct the artifact and revalidate rather than shipping. Version it with spgr-version-artifact and log the scope decision with spgr-log-decision.

8. When usability testing returns findings, triage each against the rubric. A critical finding blocks developer handoff. A moderate finding updates the screen specs before handoff. A minor finding is logged as a post-launch improvement. If any critical finding remains open, raise spgr-escalate to the human and hold handoff.

## Notes

- Output type is an envelope artifact. The `prototype` content type has no registered content schema yet, so spgr-validate-artifact applies envelope-only validation, checking the header, confidence map, decision log, and version. Still call it. Registering a content schema later upgrades the check with no change here.
- Findings classification rubric. Critical: the participant cannot complete a primary task, or takes a wrong path that causes data loss or a dead end. Moderate: the participant completes the task but with confusion, hesitation, or a recoverable error. Minor: a cosmetic or preference issue that does not impede task completion.
- Resolution by class. Critical blocks handoff until the design is reworked and re-tested. Moderate updates the affected screen specs before handoff. Minor is logged for post-launch.
- Keep the artifact token-based and free of hardcoded style values. The prototype references the approved screen specs and design tokens rather than restating visual values.
- This is a Phase 2 design artifact, so no application code is written here. The prototype is retired after usability testing completes, archive it with spgr-archive-artifact rather than maintaining it.
- Tag the Accessibility vertical with spgr-tag-vertical-agent when a flow under test has keyboard or screen-reader implications, so the usability script covers them.
