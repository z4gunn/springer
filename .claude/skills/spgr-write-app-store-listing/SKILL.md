---
name: spgr-write-app-store-listing
description: Produce an app-store-listing artifact carrying App Store Connect and Google Play Console listing content, optimized for discoverability and conversion within each store's character limits and policies. Use when the App Store Agent prepares a submission or revises a listing for new features, markets, or a product-page test.
---

# write-app-store-listing

## Purpose

Write the store-facing listing content for both iOS App Store and Google Play as one app-store-listing envelope artifact. The listing is the product's primary organic-discovery surface, so the content must rank for relevant searches (App Store Optimization) and convert without overpromising. Each store enforces hard character limits and content policies, so this skill produces content that fits within those limits and passes review on the first attempt. The App Store vertical owns this artifact and advises the design and PM agents through consultation rather than editing their artifacts.

## Inputs

| Field | Description |
|-------|-------------|
| `product_description` | Product description and value proposition |
| `features` | Core features and the user benefit of each |
| `target_keywords` | Target keywords from ICP research, ranked by relevance |
| `screenshots` | App screenshots at all required device sizes, or a list of screens to capture |
| `markets` | Markets the release targets, used to set localization scope |

## Outputs

| Artifact | Description |
|----------|-------------|
| `app-store-listing` | Envelope artifact holding per-platform listing content. App Store (iOS): app name (<=30 chars), subtitle (<=30 chars), promotional text (<=170 chars), description (<=4000 chars), keywords field (<=100 chars), screenshot plan per supported device, App Preview video spec. Google Play: title (<=30 chars), short description (<=80 chars), full description (<=4000 chars), feature graphic spec, screenshot plan (phone, tablet), promotional video spec. Plus localization scope and the product-page A/B test plan. |

## Procedure

1. Read each input with spgr-read-file. If a target-keyword list, a value proposition, or screenshots at the required sizes are missing, stop and raise spgr-escalate rather than inventing them. The keyword and screenshot inputs drive ASO ranking and conversion and cannot be assumed.
2. Write the App Store app name and subtitle first, since these carry the most keyword weight in App Store search. Place the primary keyword in the app name when the brand name does not already contain it. Keep the app name and subtitle each within 30 characters.
3. Write the iOS keywords field as a comma-separated, case-insensitive list within 100 characters. Exclude the app name and any word already in the app name, since the algorithm indexes those. Do not pad with spaces after commas, which waste the character budget.
4. Write the App Store description (<=4000 chars) and promotional text (<=170 chars). Note in the artifact that promotional text updates without app review, so reserve it for time-sensitive messaging.
5. Write the Google Play title (<=30 chars), short description (<=80 chars), and full description (<=4000 chars). Map the same value proposition and keywords to Play's fields, since Play indexes the full description text.
6. Plan the screenshots as an ordered story rather than a UI tour. Mark the first screenshot as the highest-priority asset, since most users decide to install or skip before scrolling past it. Specify the required device sizes per platform and the feature graphic for Play.
7. Specify the App Preview video (iOS) and promotional video (Play): orientation, length, and the user flow each shows.
8. Set the localization scope: list which markets require a localized listing and which inherit the default-language listing.
9. Write a product-page A/B test plan: App Store Connect product page optimization and Google Play Console store listing experiments both support testing screenshots and descriptions. Name the elements under test, the variant hypotheses, and the conversion metric each test reads.
10. Screen every element against store content policy before writing the artifact. Reject and rewrite any screenshot that shows a competitor app, is a mockup rather than an actual app screen, or any description that makes an unsubstantiated superlative claim such as "best app ever". If an input forces a policy violation that cannot be rewritten away, raise spgr-escalate with the conflicting input named.
11. Write the artifact with spgr-write-artifact and validate inline with spgr-validate-artifact. Record the keyword strategy and any policy-driven rewrites in the decision log with spgr-log-decision. Version with spgr-version-artifact on revision.
12. Route any recommendation to the design agent (for example a screenshot recapture) or the PM agent through spgr-tag-vertical-agent as a consultation. Do not edit another agent's artifact directly.

## Notes

- Output type is an envelope spec artifact (`app-store-listing`). Its content schema is registered in a later increment, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) for now.
- Hold every field to its store character limit. A field over the limit is a hard failure, not a warning, since the store truncates or rejects it.
- Mark each field's confidence in the artifact: confirmed where the input supports it, proposed where a keyword or copy choice is a judgment call, needs-human-input where a market or legal claim needs human sign-off before submission.
- Submission-readiness verification belongs to spgr-run-submission-checklist, not this skill. This skill produces the content. The checklist gates the submission.
