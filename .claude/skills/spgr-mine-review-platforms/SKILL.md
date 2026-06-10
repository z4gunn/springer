---
name: spgr-mine-review-platforms
description: Produce a review-platform analysis artifact from G2, Capterra, Trustpilot, and Product Hunt reviews of a competitor or category, surfacing top pros and cons, switching reasons, buyer-persona signals, feature comparisons, and a per-platform breakdown of review count and average rating, every claim carrying a source. Use when the Discovery agent needs buyer-level evidence on why customers choose, stay with, or leave a competing product before scoping a market, or when the PM agent needs switching reasons and feature-comparison language to feed the competitive matrix.
---

# mine-review-platforms

## Purpose

Review platforms capture a different audience than UGC forums or social media. G2 and Capterra reviews come from decision-makers who evaluated and purchased software, so their language reflects buying criteria rather than usage alone. The highest-value output is switching reasons. They reveal the exact threshold at which a paying customer chose to leave, which is the most direct signal of what a competing product must do to win that customer. This skill is a discovery research output. It runs in Phase 1, writes no code, and every factual claim it states carries a source.

## Inputs

| Field | Description |
|-------|-------------|
| `competitor_name` | Name of the competitor or product to analyze |
| `product_category` | Category to analyze when no specific competitor is given, for example "project management software" |
| `platforms` | Optional subset. Defaults to all of `g2`, `capterra`, `trustpilot`, `producthunt` |
| `date_filter` | Date range to include. Defaults to the last 18 months |
| `review_count_target` | Target reviews to analyze per platform. Defaults to 100 |

## Outputs

| Artifact | Description |
|----------|-------------|
| `top_pros` | Most frequently cited positive attributes, each with frequency and representative quotes |
| `top_cons` | Most frequently cited negative attributes, each with frequency and representative quotes |
| `switching_reasons` | Why reviewers switched from or to this product, with direction, reason, frequency, and a representative quote |
| `buyer_persona_signals` | Company size, role, and industry patterns parsed from reviewer profiles |
| `feature_comparisons` | Features reviewers compare against named competitors, with comparison direction |
| `platform_breakdown` | Review count and average rating per platform |
| `sources` | Platform names, product IDs, review counts analyzed, and date ranges per platform |

## Procedure

1. Resolve the input. Require either `competitor_name` or `product_category`. If neither is present, stop and escalate through spgr-escalate with a precise list of what is missing. Do not guess a target. Apply the defaults for `platforms`, `date_filter`, and `review_count_target` when not supplied.

2. Run a per-platform search and extraction pass over each platform in `platforms`. Use spgr-search-web with a site-scoped query per platform: `site:g2.com`, `site:capterra.com`, `site:trustpilot.com`, `site:producthunt.com`. Fetch individual review pages with WebFetch for the URLs the search returns. Honor `date_filter` and stop a platform pass at `review_count_target`.

3. Respect platform terms. Do not bulk-scrape review text in a way that violates a platform's terms of service. Where full page access is unavailable, work from public search result snippets and summarization rather than forcing a scrape. Record which platforms were summarized versus fully read in `sources`.

4. Extract per-platform content. Pull positive and negative attributes with a mention count and a small set of representative quotes each. Pull feature-comparison language, the wording of the form "compared to X, this does Y better or worse", and record the named competitor and the comparison direction. This language is direct competitive intelligence for the competitive matrix.

5. Extract switching reasons as the priority signal. Separate them by direction. Capture why reviewers switched from this product to a competitor, and why reviewers switched to this product from something else. Record reason, frequency, and a representative quote per entry.

6. Parse buyer-persona signals systematically. G2 and Capterra reviewer profiles include company size and role. Parse these into company-size ranges, common roles, and common industries, building a buyer demographic profile alongside the content analysis. This is direct ICP validation data.

7. Run the cross-platform aggregation and theme analysis pass. Merge attributes and switching reasons across platforms, deduplicate near-identical themes, and rank by frequency. Compute `platform_breakdown` with review count and average rating per platform.

8. Reconcile rating discrepancies. If the same product shows materially different average ratings across platforms, investigate the gap and record the likely cause, since it often reflects different user segments reviewing on different platforms. Note that platform skew is expected: Trustpilot leans consumer and surfaces service and support issues, and Product Hunt leans early adopters and enthusiasts at launch. Weight findings accordingly rather than treating all platforms as one population.

9. Attribute every claim to a source. A pain signal or switching reason is treated as validated only when it appears in two distinct source categories, for example two different platforms or two independent reviewer cohorts. Mark a single-source signal as proposed rather than confirmed in the confidence map.

10. Write the analysis as an envelope artifact with spgr-write-artifact, carrying the header, confidence map, decision log, and version. Run spgr-validate-artifact inline. Record any consequential analysis choice with spgr-log-decision. Register the result to the PM agent as a consultation through spgr-tag-vertical-agent rather than editing any downstream artifact directly.

## Notes

- Output type is a review-platform analysis envelope artifact. No content schema is registered for this type yet, so spgr-validate-artifact applies envelope-only validation, checking the header, confidence map, decision log, and version until a content schema is registered.
- Switching reasons are the priority extraction, per step 5. From-direction reasons reveal what would let a competing product win the customer.
- Two distinct source categories are required before a pain signal or switching reason counts as validated, per step 9. A single-source signal is proposed, not confirmed.
- Platform skew is a feature of the data, not noise. Buyer-level signal concentrates on G2 and Capterra, service-quality signal on Trustpilot, and early-adopter signal on Product Hunt.
