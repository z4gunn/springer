---
name: spgr-competitive-analysis
description: Produce a competitive-analysis artifact comparing direct competitors, indirect alternatives, and the status-quo option across a fixed matrix of dimensions, with a pricing comparison, a positioning map, and the specific differentiation gaps the product could credibly own, every data point source-cited with a retrieval date. Use when the Discovery Agent needs competitive context before a go/no-go recommendation, or when the PM Agent needs the competitive matrix to ground differentiation strategy in evidence rather than aspiration.
---

# competitive-analysis

## Purpose

Produce the competitive-analysis artifact the Discovery Agent needs before any go/no-go call, and that the PM Agent uses to make differentiation concrete. The contract matters because pricing and feature sets change often, so every claim carries a source and a retrieval date, and the matrix stays strictly factual while opinion is confined to the gaps section. This is a Phase 1 research skill. It requires web access and writes no code.

## Inputs

| Field | Description |
|-------|-------------|
| `target_market` | The market or category being analyzed, for example "B2B invoice automation for small teams" |
| `problem_space` | The core problem being solved, which shapes which competitors are relevant |
| `geography` | Geographic scope for pricing and market-availability data |
| `competitor_hints` | Optional list of known competitor names to ensure coverage |
| `depth` | One of `surface` (overview pass), `standard` (full matrix), or `deep` (pricing pages, changelogs, review-platform data) |

## Outputs

| Artifact | Description |
|----------|-------------|
| `competitor_matrix` | Competitor by feature-dimension table with present, absent, or partial ratings |
| `pricing_comparison` | Pricing tiers, models, and public list prices per competitor |
| `positioning_map` | A 2x2 or narrative analysis showing where each competitor sits on the key dimensions |
| `differentiation_gaps` | Specific gaps in features, pricing, UX, or audience that the product could credibly own |
| `sources` | All source URLs with retrieval dates |

The artifact body is `{ target_market, problem_space, competitors: [{name, type, use_case, key_features, pricing, target_audience, weaknesses, positioning, source_urls}], differentiation_gaps: [{gap, description, evidence}], positioning_map, sources: [{url, date_retrieved}] }`.

## Procedure

1. Validate the input. Confirm `target_market`, `problem_space`, `geography`, and `depth` are present and that `depth` is one of `surface`, `standard`, or `deep`. If any required field is missing or contradictory, stop and call spgr-escalate with the precise list of what is missing. Do not fill gaps with assumptions.

2. Run the discovery pass. Use spgr-search-web to identify all relevant competitors across three categories: direct competitors (same problem, same audience), indirect alternatives (different solution, same problem), and the do-nothing option (status-quo tools such as spreadsheets or email). Fold in any `competitor_hints`. Apply the dedup rule: treat an acquired product and its parent company as separate entries when both are actively marketed.

3. Run the deep-dive pass per competitor. For each entry, capture name, founding year, funding stage if public, primary use case, key features, pricing, target audience, known weaknesses, and a one-line positioning statement. Source weaknesses from spgr-mine-support-data and review-platform data rather than relying on competitor marketing pages alone. When mobile competitors exist, mine app-store reviews as a weakness source.

4. Fill the matrix against the standard dimension set: feature coverage, pricing model, pricing tier, target user size, mobile support, API availability, integrations count, onboarding friction, support quality, and known churn drivers. Rate each cell present, absent, or partial. Keep the matrix factual with no editorializing.

5. Attach a source and a retrieval date to every data point. Treat a competitor weakness as validated only when two distinct source categories support it, for example a review platform and a support-data mining pass. Do not treat a single-source pain signal as validated.

6. Build the positioning map and write `differentiation_gaps`. Confine all analysis and opinion to the gaps section, each gap backed by evidence drawn from the matrix and the cited sources.

7. Write the artifact via spgr-write-artifact with inline spgr-validate-artifact. On a validation failure, correct the artifact and revalidate before returning. Record the analytical calls in spgr-log-decision and version the result with spgr-version-artifact.

## Notes

- Output type is an envelope research artifact. The `competitive-analysis` type has no registered content schema, so spgr-validate-artifact applies envelope-only validation, checking the header, confidence map, decision log, and version, until a content schema is registered.
- File reads and writes route through spgr-read-file and spgr-write-file. Reading an existing artifact routes through spgr-read-artifact.
- Set a per-claim confidence in the confidence map. A two-source-validated weakness is confirmed. A single-source signal is proposed. A gap that needs a human market call is needs-human-input.
- This skill does not select or recommend a build decision. It supplies the competitive evidence the Discovery and PM agents consume.
