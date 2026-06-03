---
name: spgr-synthesize-painpoints
description: Produce a pain-point-taxonomy artifact that merges all UGC mining outputs into one deduplicated, two-level hierarchy of pain points, each scored by frequency and severity, calibrated to confirmed or proposed by source coverage, tagged to user types, and backed by verbatim examples, plus a top-ten quick reference. Use when the Discovery Agent has collected outputs from the mine-* skills and must consolidate them into the single authoritative pain-point set that feeds spgr-write-prd and persona construction, or when the PM Agent needs one reconciled taxonomy instead of overlapping per-source findings.
---

# synthesize-painpoints

## Purpose

Convert a collection of overlapping mining findings into one authoritative pain-point taxonomy. Each mine-* skill emits findings in its own shape. Before those findings can drive product decisions, they must be normalized to a common format, deduplicated by semantic similarity across sources, scored, and organized into a two-level hierarchy. This is the bridge between raw research and the PRD. Completeness here sets the ceiling on completeness for spgr-write-prd and persona work downstream, so every distinct signal must be preserved and reconciled, not dropped.

## Inputs

| Field | Description |
|-------|-------------|
| `mining_outputs` | Array of outputs from any combination of mine-ugc-forums, mine-app-store-reviews, mine-social-media, mine-review-platforms, and spgr-mine-support-data. Read each with spgr-read-artifact. |
| `problem_domain` | The problem space being analyzed, used to anchor the taxonomy categories |
| `user_types` | Distinct user types across all research inputs. Every pain point is tagged to the user types it affects. |
| `dedup_threshold` | Semantic similarity threshold for merging overlapping pain points. Defaults to 0.8. |

## Outputs

| Artifact | Description |
|----------|-------------|
| `pain_point_taxonomy` | Two-level hierarchy (category to specific pain point), each pain point carrying the per-pain-point schema in Notes |
| `source_coverage` | Which pain points appear in which source types, used to calibrate confidence |
| `user_type_mapping` | Which pain points affect which user types, with severity per type |
| `top_ten_pain_points` | The 10 highest composite-score pain points as a quick-reference summary |

## Procedure

1. Read every entry in `mining_outputs` with spgr-read-artifact. Confirm at least one mining output is present and that each carries source citations. If the input array is empty, or a finding has no source, escalate with spgr-escalate rather than synthesizing from incomplete evidence.
2. Normalization pass. Standardize each finding to the common pain-point format. Map each source's native fields onto `name`, `description`, candidate `category`, `user_types_affected`, `source_type`, and `verbatim_examples`. Record the originating `source_type` from the set forums, app_store, social, review_platforms, support.
3. Clustering pass. Group semantically similar pain points across all sources at or above `dedup_threshold`. Merge by meaning, not exact text. Treat "onboarding is confusing", "hard to get started", and "took me 3 hours to set up my first project" as one onboarding_friction pain point. When merging, union the source_types and the user_types_affected, and keep every verbatim example.
4. Synthesis pass. Score each cluster on frequency (high, medium, low) and severity (critical, high, medium, low) as distinct dimensions. Surface both a high-frequency low-severity pain point and a low-frequency high-severity one, since each calls for a different intervention. Set `confidence` from source coverage: a pain point present in two or more distinct source types is confirmed, a pain point present in only one source type is proposed. Record per-pain-point source coverage and per-user-type severity.
5. Taxonomy construction pass. Organize clusters into a two-level hierarchy, top-level categories (for example onboarding, core_workflow, integration, performance, pricing) anchored to `problem_domain`, with specific pain points inside each. Assign a stable `pain_point_id` to every pain point.
6. Rank for `top_ten_pain_points` by composite score `frequency_weight x severity_weight x source_diversity_bonus`. Apply a source diversity bonus of +20 percent when a pain point appears in three or more source types. Take the top 10.
7. Write the assembled taxonomy, source_coverage, user_type_mapping, and top_ten_pain_points as one envelope artifact with spgr-write-artifact, set each section's confidence signal, and validate inline with spgr-validate-artifact. Log the key synthesis choices (the dedup threshold used, any contested merges) with spgr-log-decision. On validation failure, fix the artifact and revalidate before returning.

## Notes

- Output type is an envelope artifact (a research synthesis report). The pain-point-taxonomy type has no registered content schema yet, so spgr-validate-artifact applies envelope-only validation, checking the header, confidence map, decision log, and version. Still call spgr-validate-artifact. Register a content schema later to gain field-level checks.
- Per-pain-point schema: `{ pain_point_id, category, name, description, frequency: "high"|"medium"|"low", severity: "critical"|"high"|"medium"|"low", user_types_affected: [string], source_types: ["forums"|"app_store"|"social"|"review_platforms"|"support"], confidence: "confirmed"|"proposed", verbatim_examples: [{quote, source_type, source_url}] }`.
- Two source categories rule. A pain point reaches confirmed only with two or more distinct source types. A single-source pain point stays proposed. Do not promote a signal past its evidence.
- Preserve every verbatim example with its source_url across merges. These quotes are the evidence base for persona construction and seed the product copy vocabulary, so do not summarize them away.
- Frequency and severity are independent axes. Never collapse them into one rating.
- This skill runs in Phase 1 discovery, where no application code is written. Its only side effects are reading and writing artifacts.
