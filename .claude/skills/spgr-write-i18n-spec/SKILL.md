---
name: spgr-write-i18n-spec
description: Produce an i18n-spec envelope artifact that fixes the internationalization architecture before development, covering i18n library and message-format selection, string-key naming convention, plural rules, locale-aware date/number/currency formatting, locale detection and switching, the translation workflow, the missing-string fallback chain, and a pseudo-localization CI step. Use when the i18n Agent must settle the internationalization approach before any string is written, or when product scope adds a target locale or a right-to-left language and the existing i18n architecture must be set or revisited so i18n is built in rather than bolted on later.
---

# write-i18n-spec

## Purpose

Define the internationalization architecture for the project as an i18n-spec artifact, so i18n is designed in before development rather than retrofitted. Retrofitting is expensive: every hard-coded string must be extracted, every date assumption audited, and every layout retested for text expansion. The spec fixes the library, message format, key convention, formatting rules, locale handling, translation workflow, and fallback chain up front. Even projects that do not yet target other markets benefit, because the spec lowers the later cost of adding a locale from a migration to a translation drop-in.

This skill produces the spec only. It does not extract strings, audit right-to-left support, or write a locale-coverage plan. Those are separate i18n skills. When this spec advises a horizontal agent on a section of another artifact (for example a frontend layout constraint or a backend error-message catalog), route that advice through a consultation with spgr-tag-vertical-agent rather than editing the other artifact directly.

## Inputs

| Field | Description |
|-------|-------------|
| `product-scope` | Target locales, right-to-left language requirements, and whether global reach is a stated goal |
| `tech-stack` | Framework i18n support to bind to, for example next-intl, react-i18next, iOS NSLocalizedString, or Android string resources |
| `content-types` | The string surfaces in scope: static UI strings, dynamic user-generated content, server-side error messages, email templates |

Read inputs with spgr-read-file for source documents and spgr-read-artifact for the tech-stack-decision and any prior i18n-spec.

## Outputs

| Artifact | Description |
|----------|-------------|
| `i18n-spec` | Envelope artifact holding the internationalization architecture: library and message-format selection, string-key naming convention, plural-rule support, date/time/number/currency formatting rules, locale detection and override, locale switching behavior, translation workflow, missing-string fallback chain, and the pseudo-localization CI step |

Write with spgr-write-artifact and validate inline with spgr-validate-artifact. Record each architecture choice and its rationale with spgr-log-decision, and set a confidence signal (confirmed, proposed, needs-human-input) per section.

## Procedure

1. Confirm scope. Read product-scope, tech-stack, and content-types. If target locales, right-to-left requirements, or the framework i18n binding are missing or contradictory, stop and raise spgr-escalate with the precise list of what is missing rather than assuming a default locale set or library.
2. Select the i18n library and message format. Bind to the framework's supported library from the tech stack. Specify ICU MessageFormat over simple interpolation, because ICU expresses plural, gender, and select forms that simple interpolation cannot render correctly across languages. Record the choice with spgr-log-decision.
3. Fix the string-key naming convention. Specify a `screen.component.context` hierarchy, for example `auth.login.submit_button`, and state how keys are namespaced across the content types in scope.
4. Specify plural-rule support. Require ICU plural categories so that languages with more than two plural forms render correctly. State how plural keys are authored and tested.
5. Specify formatting rules. Require locale-aware date, time, number, and currency formatting through language built-ins (Intl in JavaScript, NSDateFormatter in Swift, the platform equivalent elsewhere). Prohibit custom string concatenation for these values, because custom formatting is wrong for at least some locale.
6. Specify locale detection and override. Define the detection sources and their precedence, for example the browser Accept-Language header, an explicit user preference, a URL prefix, and a subdomain. Define the override path the user takes to change locale.
7. Specify locale switching behavior. State whether switching reloads the page or applies without reload, and define the switching UX.
8. Define the translation workflow. State how source strings reach translators and return into the codebase, and how the message catalog is versioned.
9. Define the fallback chain. State which locale a missing string falls back to, in order, down to the source locale.
10. Add the pseudo-localization CI step. Specify a CI step that transforms every string into a pseudo-locale, for example `[!! Pséùdô Lôcâlîzâtîôn !!]`, and runs the test suite against it to catch hard-coded strings and layout overflow before real translations exist. State the layout expansion budget the build must accommodate, noting German text runs about 30 percent longer than English and Finnish can run about 60 percent longer, so fixed-width containers with truncation are an i18n bug.
11. Validate and version. Call spgr-validate-artifact on the result. Set the per-section confidence map. If any section needs a human decision (for example the target locale set or the right-to-left commitment), mark it needs-human-input and raise it through spgr-escalate or spgr-notify-human as the trigger warrants. Version the confirmed artifact with spgr-version-artifact.

## Notes

- Output type is an envelope artifact (i18n-spec) written via spgr-write-artifact. The i18n-spec content schema is not registered yet, so spgr-validate-artifact applies envelope-only validation for now, checking the header, confidence map, decision log, and version. The content schema is registered in a later increment.
- Where the spec constrains another agent's work, for example a frontend layout that must absorb text expansion or a backend error catalog that must be externalized, route the recommendation through spgr-tag-vertical-agent as a consultation, not as a direct edit of that agent's artifact.
- The i18n vertical operates as consultant when tagged, as auditor on a scheduled sweep, and as a gate whose sign-off the i18n-spec can require before a release marks its i18n-dependent sections confirmed.
