---
name: spgr-write-mobile-build-pipeline
description: Write the CI/CD pipeline configuration for iOS and Android builds as source code, covering secrets-injected code signing, platform test runners, archive and bundle generation, multi-channel distribution to TestFlight, Firebase App Distribution, App Store, or Play Store, screenshot capture for visual regression, and optional device-farm UI test matrices. Use when the DevOps agent stands up or updates a mobile project's build and release pipeline, or when the Mobile Developer agent supplies build scheme and test target names and needs the signing and distribution mechanics encoded correctly.
---

# write-mobile-build-pipeline

## Purpose

Produce the mobile build and release pipeline as committed configuration. Mobile pipelines are harder than web pipelines because they carry code signing certificates and provisioning profiles on iOS, keystore management on Android, platform-specific test runners, binary archive generation, and multi-channel distribution. A broken signing configuration silently produces a build that passes CI but cannot install on a device, so the signing and distribution mechanics must be encoded once and correctly rather than re-derived per project. Scope is the pipeline definition only. The app source, test code, and the secrets themselves are out of scope.

## Inputs

| Field | Description |
|-------|-------------|
| `platforms` | iOS, Android, or both. Determines which signing and build paths the pipeline includes. |
| `ci_platform` | GitHub Actions, Bitrise, CircleCI, or equivalent. Sets the config file format and syntax. |
| `distribution_channels` | The target channels: TestFlight, Firebase App Distribution, App Store, Play Store. Determines the CD distribution steps. |
| `signing_credentials` | Secrets-manager references for iOS certificates and provisioning profiles, the Android keystore, and keystore and key passwords. References only, never literal credentials. |
| `build_schemes` | iOS build scheme names and Android build variants, supplied by the Mobile Developer agent. |
| `test_targets` | Unit, snapshot, and UI test target or task names per platform. |

## Outputs

| Artifact | Description |
|----------|-------------|
| CI pipeline config | Runs lint, unit tests, snapshot tests, and a build verification on every pull request. Written via spgr-write-file. |
| CD pipeline config | Archive and bundle generation, code signing, and distribution to the configured channels. Written via spgr-write-file. |
| Signing and secrets config | Fastlane match or equivalent certificate config and the CI secrets mappings that inject signing credentials at build time. Written via spgr-write-file. |
| Screenshot capture step | Captures simulator and emulator screenshots during CI and retains them as build artifacts for visual regression comparison. Written via spgr-write-file. |

## Procedure

1. Read any existing pipeline config, Fastlane setup, and project build files with spgr-read-file before writing, to match the established conventions and avoid clobbering unread files. Resolve the build scheme and test target names from the Mobile Developer agent's inputs rather than guessing them.

2. Write the CI pipeline that runs on every pull request: lint, unit tests, snapshot tests, and a build verification compile. Confirm the CI test scope against spgr-write-acceptance-criteria for the stories under test so the suite tracks the completion contract. Run the tests through spgr-run-tests so a failure or coverage-floor breach exits non-zero and blocks the merge.

3. Configure iOS code signing through Fastlane match or an equivalent certificate-management approach. Pull certificates and provisioning profiles from a dedicated certificates store or secrets manager at build time. Never store signing certificates in the application repository, even encrypted.

4. Configure Android signing to inject the keystore and the keystore and key passwords from the CI secrets store. Confirm no keystore password is echoed to the build log. Mask every signing secret in CI output.

5. Automate build numbering so it is monotonically increasing. Two builds that share a version string must carry distinct, increasing build numbers so distribution tools can tell them apart. Never ship two builds with the same build number.

6. Write the CD pipeline: generate the iOS archive and the Android app bundle, sign each with the injected credentials, then distribute to each configured channel (TestFlight, Firebase App Distribution, App Store, Play Store). Set a build-artifact retention policy and record the version and build number for each release.

7. Add a screenshot capture step that records simulator and emulator screenshots during CI and retains them as build artifacts for visual regression comparison.

8. When the distribution targets a production release and the inputs request it, add a device-farm step that runs the UI test suite across a matrix of real devices before the release proceeds.

9. Optimize build time aggressively: cache dependencies, cache iOS derived data, and enable the Gradle build cache on Android. A mobile CI build over 20 minutes creates an unacceptable feedback cycle, so escalate via spgr-escalate to trim scope or split the pipeline rather than shipping a slow gate.

10. Write each config file with spgr-write-file, then run the pipeline to confirm it produces an installable, correctly signed build for each platform. If a required input is missing or contradictory (for example a distribution channel is requested with no matching signing credential reference, or a build scheme name is absent), stop and raise spgr-escalate with the precise list of what is missing rather than guessing a certificate, keystore, or scheme. If a signing or secrets-handling choice touches the security domain, tag the Security agent with spgr-tag-vertical-agent before finalizing. Record any consequential signing, distribution, or numbering choice with spgr-log-decision.

## Notes

- The output is source code (pipeline config, signing config, and CI steps), verified by a successful signed build and by spgr-run-tests and CI rather than by an envelope schema.
- Signing credentials are always secrets-manager references. Never write a certificate, provisioning profile, or keystore password into the repository or a config file, even encrypted.
- Build numbers are monotonically increasing and unique per version string. The numbering automation is the single source of build numbers, not a manually edited field.
- Build-time caching and the 20-minute build-time ceiling are pipeline concerns wired into the config, not steps a developer runs by hand on each change.
