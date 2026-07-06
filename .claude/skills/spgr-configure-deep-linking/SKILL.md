---
name: spgr-configure-deep-linking
description: Configure mobile deep linking as source code, wiring iOS Universal Links and Android App Links so external links open the correct in-app screen, with a route handler, web fallback, and deep link registry. Use when the Mobile Developer agent sets up deep linking before first launch or before review.
---

# configure-deep-linking

## Purpose

Implement deep linking for one mobile app so links from marketing campaigns, email flows, push notification actions, and onboarding open a specific in-app screen. Configure this before first launch, because retrofitting deep links into an established navigation structure is disruptive. The output is source code (platform link configuration, a route handler, a registry, and tests), verified by spgr-run-tests and CI rather than by an envelope schema.

## Inputs

| Field | Description |
|-------|-------------|
| `navigation-map` | Every routable screen and its parameters, read with spgr-read-file |
| `link-scheme` | The universal link domain and any custom URL scheme |
| `platform-targets` | iOS, Android, or both |
| `acceptance-criteria` | Confirmed Given/When/Then for each deep link route, from spgr-write-acceptance-criteria |

## Outputs

| Artifact | Description |
|----------|-------------|
| iOS link config | Associated Domains entitlement, an `apple-app-site-association` (AASA) file served from the domain, and a Universal Links handler in AppDelegate or SceneDelegate |
| Android link config | Intent filter in AndroidManifest.xml, an `assetlinks.json` Digital Asset Links file, and a link handler |
| Route handler | Parses an incoming link, resolves it against the registry, and navigates to the target screen with parsed parameters |
| Deep link registry | A document mapping every link route to its in-app screen and parameter schema |
| Test matrix | UI tests covering every defined route, XCUITest for iOS and Espresso for Android, wired into CI device-farm runs |

## Procedure

1. Read the navigation map, link scheme, and acceptance criteria with spgr-read-file. If the navigation map omits a routable screen, a parameter schema is undefined, the link domain is missing, or a custom scheme is requested without a stated reason to prefer it over Universal or App Links, stop and raise spgr-escalate with the precise list of what is missing. Do not invent routes or domains.
2. Build the deep link registry first. List every link route with its target screen and parameter schema. This registry is the single source the route handler, the platform config, and the tests all match. Write it with spgr-write-file.
3. Prefer Universal Links (iOS) and App Links (Android) over custom URL schemes, because a custom scheme can be claimed by another installed app. Record this choice and any platform-specific deviation with spgr-log-decision.
4. For each route in scope, write a failing UI test before the configuration or handler code: XCUITest for iOS, Espresso for Android, one scenario per acceptance criterion. Confirm the tests fail with spgr-run-tests before implementing. Build only the routes the acceptance criteria specify.
5. Configure iOS with spgr-write-file: add the Associated Domains entitlement, write the AASA file, and implement the Universal Links handler. The AASA file must be served from the exact link domain over HTTPS with no redirect. State this serving requirement in the registry, because platform validation fails silently when it is not met.
6. Configure Android with spgr-write-file: add the intent filter to AndroidManifest.xml, write `assetlinks.json`, and implement the link handler. The Digital Asset Links file carries the same exact-domain, HTTPS, no-redirect requirement as iOS.
7. Implement the route handler with spgr-write-file. Parse the incoming link, resolve it against the registry, and navigate to the target screen with parsed parameters. Handle the app-not-installed case with a web fallback (an app store redirect or the web equivalent of the screen). Log every deep link event for analytics: source, destination, and success or failure.
8. Run spgr-run-tests until the route tests pass. Wire the UI test matrix into CI as device-farm runs, and note that physical-device validation is required, because the link validation process differs from a simulator and a simulator pass does not confirm a real link opens.
9. Format and lint the changed files clean before handing off. If a route cannot be satisfied within the approved navigation map or link scheme, raise spgr-escalate rather than deviating.

## Notes

- Output is source code (platform config, route handler, registry, and UI tests) verified by spgr-run-tests and CI, not by an envelope schema. The deep link registry is a document written via spgr-write-file. If the registry is later promoted to a registered artifact type, write it via spgr-write-artifact with its schema added in a later increment.
- Test-first is non-negotiable. Write the failing route UI test before any configuration or handler code, and build only the routes the acceptance criteria name (YAGNI). Keep one logical change per commit and reach a clean lint and format before commit.
- The AASA and `assetlinks.json` files must be served from the exact link domain over HTTPS with no redirect, or platform association fails silently. Treat the serving requirement as part of the deliverable, not an afterthought.
- Tag the Mobile Developer agent's analytics dependency with spgr-tag-vertical-agent if the deep link event logging must align with an existing analytics taxonomy.
