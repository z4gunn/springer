---
name: spgr-configure-push-notifications
description: Implement end-to-end mobile push notification infrastructure as source code, covering APNs and FCM credentials, device token lifecycle, all app-state handlers, tap-to-deep-link routing, preferences, and delivery monitoring. Use when the Mobile Developer agent picks up a push notification story with confirmed requirements.
---

# configure-push-notifications

## Purpose

Build the full mobile push delivery chain so a notification produced on the backend reaches a real device, is handled in every app state, and routes to the correct screen on tap. Push bugs are invisible until users stop receiving notifications, so the chain is built test-first and confirmed end to end in staging before it is allowed to merge. Implement only the notification types, categories, and deep links named in the requirements (YAGNI), build per-category preferences and delivery monitoring from the start because both are costly to retrofit, and keep one logical change per commit.

## Inputs

| Field | Description |
|-------|-------------|
| `notification_requirements` | Notification types, content, action buttons, and deep link payloads to support |
| `platform_targets` | iOS, Android, or both |
| `acceptance_criteria` | Confirmed criteria for the push story, read via spgr-read-artifact, that the tests must cover |
| `architecture_constraints` | Approved tech stack and mobile platform decisions, read via spgr-read-artifact |

Read each input with spgr-read-artifact or spgr-read-file before building. If notification requirements, platform targets, or acceptance criteria are missing or contradictory, stop and raise spgr-escalate with the precise list of what is missing rather than assuming defaults.

## Outputs

All outputs are source code written via spgr-write-file.

| Artifact | Description |
|----------|-------------|
| iOS push config | APNs token-based auth (p8 key) or certificate configuration, push entitlement, UNUserNotificationCenter setup |
| Android push config | FCM project configuration, google-services.json integration, FirebaseMessagingService implementation |
| Token registration flow | Registration on grant, refresh on rotation, de-registration on sign-out, backend deactivation on invalid-token errors |
| State handlers | Foreground in-app display, background system notification, terminated tap-wakes-app handling |
| Tap handler | Deep link routing from the notification payload to the target screen |
| Notification preferences | Per-category opt-in and opt-out, wired from the start |
| Delivery monitoring | Tokens registered vs notifications delivered vs opened, instrumented from launch |
| Staging delivery test | An end-to-end test confirming delivery to a real device on a real network |

## Procedure

1. Read and validate the inputs. Confirm acceptance criteria, notification requirements, and platform targets are present. Escalate on any gap before writing code.
2. Write the failing tests first. Use spgr-write-acceptance-test to turn the confirmed criteria into failing tests, one scenario per criterion, covering token registration, each of the three app states, tap routing, and per-category preference filtering. Confirm they fail with spgr-run-tests before any implementation.
3. Configure platform credentials per target. iOS: APNs p8 key or certificate, the push entitlement, and UNUserNotificationCenter. Android: FCM project, google-services.json, and FirebaseMessagingService. Inject credentials from configuration, never hardcode them. Do not commit p8 keys, certificates, or google-services secrets.
4. Implement the permission request at a contextually relevant moment, gated behind a value explanation, not on first launch. Prompting before the user understands the app's value is the primary cause of low grant rates.
5. Implement token registration. Register on grant, send the token to the backend, handle APNs and FCM refresh events and update the backend immediately, and de-register on sign-out. When the provider reports a token as invalid or expired, deactivate it on the backend.
6. Implement the three state handlers. Foreground displays the notification in-app, background shows the system notification, terminated wakes the app on tap. Implement the tap handler to route each deep link payload to its target screen.
7. Implement per-category notification preferences so a user can opt in or out per category, and filter delivery accordingly.
8. Instrument delivery monitoring from launch, recording tokens registered, notifications delivered, and notifications opened.
9. Run the full suite with spgr-run-tests and confirm every test now passes. Run the staging delivery test against a real device on a real network and confirm end-to-end delivery before sign-off. If staging delivery fails, do not mark the story done, file the failure with spgr-write-bug-report.
10. Format and lint clean before commit. Tag the mobile push decisions touching auth, compliance, or analytics to the relevant specialist with spgr-tag-vertical-agent, and record consequential choices with spgr-log-decision.

## Notes

- The output is source code verified by spgr-run-tests, the staging delivery test, and CI rather than by an envelope schema.
- Keep one logical change per commit and reach zero lint and format violations before each commit.
- Token-level personal data and notification content may carry compliance and privacy constraints. Tag the Compliance and Auth verticals with spgr-tag-vertical-agent when device tokens or message payloads touch their domains, and escalate with spgr-escalate if a constraint conflicts with the requirements.
