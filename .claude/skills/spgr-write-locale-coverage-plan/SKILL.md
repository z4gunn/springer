---
name: spgr-write-locale-coverage-plan
description: Produce a locale-coverage-plan artifact that fixes which locales the product supports, in tiered priority order, with per-locale coverage thresholds, a translation workflow, and a new-string process. Use when the i18n Agent must set the target localization state, or when a market change requires the supported-locale set re-decided.
---

# write-locale-coverage-plan

## Purpose

Locale coverage degrades silently. New features ship strings in English first, translations lag, and a locale ends up partially translated, which shows English fallbacks mid-product and reads worse than a fully-English product. Produce the locale-coverage-plan artifact that names the supported locales, tiers them by launch commitment, sets the coverage threshold below which a locale ships only as partially supported, and defines the workflow and monitoring that catch coverage gaps before users see them. This is an i18n vertical artifact. It advises horizontal agents through a consultation rather than editing their artifacts directly.

## Inputs

| Field | Description |
|-------|-------------|
| `target-market-geography` | The markets the product is sold in, used to derive candidate locales |
| `icp-languages` | User research data on what languages the target ICP speaks |
| `localization-resources` | Available translation capacity (vendor, community, or in-house) per locale |
| `localization-platform` | The string-sync platform in use (Phrase, Lokalise, Crowdin) if selected |

## Outputs

| Artifact | Description |
|----------|-------------|
| `locale-coverage-plan` | Envelope artifact carrying supported locales in tiered priority order, a per-locale coverage threshold, the translation workflow, coverage monitoring, and the new-string process with per-tier SLAs |

## Procedure

1. Read the inputs with spgr-read-file and spgr-read-artifact. If any input artifact is missing, use spgr-read-artifact to locate it.
2. Derive candidate locales from target market geography and ICP languages. For each candidate, confirm localization-resource availability. Escalate any candidate market that has no translation capacity rather than silently dropping it.
3. Tier the supported locales. Tier 1 must be complete at launch, Tier 2 complete within 60 days, Tier 3 best-effort. Assign professional human translation to every Tier 1 locale. Permit machine translation only for Tier 3 locales where market size does not justify professional cost.
4. Set the translation-coverage threshold, defaulting to 95 percent of user-visible strings translated. Record that a locale above the threshold is supported, and a locale where more than 5 percent of strings fall back to English is partially supported, not supported. State that this distinction must be surfaced in the locale-selection UI.
5. Define the translation workflow integrated into the development cycle. New source-English keys push to the localization platform automatically on add, approved translations pull back into the codebase automatically, and new strings are translatable within one sprint of being written, not batched quarterly.
6. Define coverage monitoring, naming the missing-key reports and coverage dashboard that surface gaps, and the new-string process with a translation-turnaround SLA per tier.
7. Write the plan with spgr-write-artifact and run spgr-validate-artifact inline. Record each tier and threshold decision with spgr-log-decision.
8. Where the plan constrains a horizontal agent (for example the locale-selection UI distinction owned by the Frontend Developer, or the per-sprint translation step owned by the backend or DevOps cycle), route that recommendation through spgr-tag-vertical-agent as a consultation. Do not edit the other agent's artifact directly.
9. If validation fails, or inputs conflict (for example an ICP language with no resourced translation path), or a market change invalidates the existing tiering, stop and raise spgr-escalate with the precise list of what is missing or contradictory. Do not fill gaps with assumptions.

## Notes

- Output type: spec or policy envelope artifact (`locale-coverage-plan`). Its content schema is registered in a later increment, so spgr-validate-artifact applies envelope-only validation for now (header, confidence map, decision log, and version).
- Mark a locale tiering or threshold decision as `proposed` until localization resources for that tier are confirmed, then `confirmed`. Mark any unresourced candidate locale as `needs-human-input`.
- Version a revised plan with spgr-version-artifact. A change to the supported-locale set or to a tier commitment is a scope change and is routed through spgr-escalate.
