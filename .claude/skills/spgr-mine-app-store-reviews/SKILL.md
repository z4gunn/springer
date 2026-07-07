---
name: spgr-mine-app-store-reviews
description: Produce an app-store-review analysis artifact from App Store and Google Play reviews of competitor or category apps, surfacing complaint and praise themes, feature-gap signals, and sentiment trend. Use when the Discovery agent mines competitor reviews for the pain-point taxonomy, or when the PM agent needs review-grounded competitor evidence.
---

# mine-app-store-reviews

## Purpose

App store reviews come from real users who installed an app and felt strongly enough to write. The 1-3 star reviews reveal what breaks trust and triggers uninstall. The 4-5 star reviews reveal what makes a product sticky. Both signals feed the pain-point taxonomy and the feature backlog. This skill converts unstructured review text into a thematic, evidence-grounded analysis the Discovery agent and PM agent can act on.

This is a Phase 1 discovery research output. No code is written. Every factual claim carries a source, and a pain signal is treated as validated only when it appears across two distinct source categories, for example a recurring review theme corroborated by a sentiment dip after a dated update. The analysis is a consultant input to the PM backlog. It does not edit the backlog directly. Recommendations flow through a consultation registered with spgr-tag-vertical-agent.

## Inputs

| Field | Description |
|-------|-------------|
| `app_name` | Name of the app, or a direct App Store or Google Play URL |
| `platform` | One or both of `ios`, `android` |
| `date_filter` | Date range for reviews. Defaults to the last 12 months |
| `review_count_target` | Target number of reviews to analyze. Defaults to 200 |
| `focus` | One of `pain-points` (prioritize low-star), `retention-drivers` (prioritize high-star), `balanced`. Defaults to `balanced` |

## Outputs

| Artifact | Description |
|----------|-------------|
| `complaint_themes` | Recurring complaints from 1-3 star reviews, grouped by theme with frequency, sentiment, and representative dated quotes |
| `praise_themes` | Recurring praise from 4-5 star reviews, grouped by theme with frequency and quotes |
| `feature_gap_signals` | Explicit feature requests in review text, sorted by mention count, with example quotes |
| `sentiment_trend` | Whether sentiment improved, degraded, or held steady over the range, with the evidence behind the read |
| `rating_distribution` | Count of reviews at each star level 1 through 5 |
| `sources` | App store name, app ID, review count analyzed, and date range |

## Procedure

1. Resolve the app to a canonical store listing. If `app_name` is a name rather than a URL, use spgr-search-web to find the App Store and Google Play listing URLs for each requested platform. Confirm the listing matches the intended app before retrieving reviews, since same-name apps are common.

2. Retrieve reviews with web access, preferring a dedicated app store review API and falling back to fetching review pages. Honor `date_filter`, defaulting to the last 12 months. Pull toward `review_count_target`, defaulting to 200. If the available review volume is too low to support thematic grouping, for example fewer than 30 usable reviews, stop and record this as a discovery-coverage gap, then escalate with spgr-escalate. Do not synthesize reviews or infer themes from listing copy.

3. Apply `focus`. Under `pain-points` weight retrieval and analysis toward 1-3 star reviews. Under `retention-drivers` weight toward 4-5 star. Under `balanced` sample across the star scale. Treat 3-star reviews as high-value in every mode, since they come from users who want to like the product but hit specific friction.

4. Batch the reviews into chunks. Run a thematic clustering pass per chunk, then aggregate themes across all chunks. Cluster by meaning, not by wording. Reviews mentioning "crashes", "keeps crashing", and "app crashes constantly" belong to one `stability` theme. Group by theme, not by rating, because a thematic read is more actionable than a per-star count.

5. Build the outputs. Compute `rating_distribution` across the star scale. Form `complaint_themes` from 1-3 star clusters and `praise_themes` from 4-5 star clusters, each carrying frequency, a sentiment read, and dated representative quotes. Extract `feature_gap_signals` as explicit asks written in reviews, ranked by mention count with example quotes. Treat these asks as direct backlog inputs, since users rarely write reviews asking for a feature they would not use.

6. Compute `sentiment_trend` over the date range as improved, degraded, or held steady. Tie movement to dated evidence. A drop in average rating following a dated competitor update reveals what that update broke, and a rise reveals what it fixed.

7. When both platforms are analyzed, compare themes across iOS and Android. Mark each theme as platform-specific or universal, for example iOS notification bugs or Android back-gesture handling versus a stability complaint present on both. Cross-platform agreement strengthens a signal.

8. Apply the two-source rule before marking any pain signal validated. A complaint theme is validated only when a second distinct source category corroborates it, for example a recurring review theme plus a sentiment dip after a dated update, or the same theme present on both platforms. Mark single-source themes as proposed in the confidence map, not confirmed.

9. Capture developer-response signal as a secondary read. Absent developer responses indicate support-quality weakness, and responses that misread the complaint indicate a product-user communication gap. Record this alongside the affected complaint themes, not as a standalone theme.

10. Write the analysis as an envelope artifact with spgr-write-artifact, carrying the header, confidence map, decision log, sources, and version. Run spgr-validate-artifact inline. Record any consequential analysis choice with spgr-log-decision.

11. Register the recommendation to the PM agent through spgr-tag-vertical-agent as a consultation. Do not edit the backlog artifact directly.

## Notes

- Output type is an app-store-review analysis envelope artifact. It has no registered content schema yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered.
- Every factual claim carries a source. A pain signal needs two distinct source categories before it is treated as validated, per step 8. Single-source themes ship as proposed.
- Group by theme, not by rating. The star count is a filter, not the unit of analysis.
- Low review volume is a discovery-coverage gap to escalate, not a silent skip. Escalate rather than inferring themes from too few reviews or from listing copy.
