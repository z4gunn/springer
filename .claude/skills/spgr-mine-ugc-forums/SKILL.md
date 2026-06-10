---
name: spgr-mine-ugc-forums
description: Produce a forum pain-point analysis artifact by mining Reddit, Hacker News, Stack Overflow, Quora, and niche forums for authentic user frustration expressed in natural language, grouped into pain-point clusters by theme with verbatim quotes, engagement-weighted frequency signals, a per-platform breakdown, cited source URLs, and the exact user vocabulary for copywriting. Use when the Discovery Agent needs unfiltered evidence of a problem from public forums during Phase 1 discovery, or when the PM agent needs forum-grounded pain signals and user language before writing requirements.
---

# mine-ugc-forums

## Purpose

Product teams overestimate how well they understand user problems. Public forum posts bypass this. Users describing frustrations in public are unfiltered, specific, and representative of the wider population who shares the problem but never spoke to a researcher. The words users reach for ("I keep having to", "there is no way to", "why can't it just") are the words the product copy and onboarding should use. This skill captures both the signal and the language as a cited Phase 1 discovery artifact.

This skill runs in Phase 1, where no code is written. It is a discovery research output and requires web access. Every factual claim carries a source. A pain point is treated as validated only when two distinct source categories support it, per the discovery evidence rule.

## Inputs

| Field | Description |
|-------|-------------|
| `problem_domain` | The core problem space to research, for example "scheduling for freelancers" or "B2B expense reporting" |
| `target_user_type` | The user type to look for, for example "solo freelancers" or "finance managers at 50-person companies" |
| `keyword_set` | Array of keywords and phrases to search. The skill expands these with related terms before searching |
| `date_filter` | Date range for results. Defaults to the last 24 months |
| `platforms` | Optional subset of platforms to search. Defaults to all: `reddit`, `hackernews`, `stackoverflow`, `quora`, `niche` |

## Outputs

| Artifact | Description |
|----------|-------------|
| `pain_points` | Pain points grouped into clusters by theme, each with a description, an engagement-weighted frequency estimate, a severity, and verbatim quotes |
| `verbatim_quotes` | The best direct user language per pain point, quoted exactly, each tied to a source URL, date, and engagement score |
| `frequency_signals` | Estimated frequency per theme, weighted by engagement rather than raw post count |
| `platform_breakdown` | Per-platform counts showing which themes surfaced where |
| `user_vocabulary` | The specific words and phrases users use for this problem, to feed directly to copywriting |
| `sources` | All source URLs with platform, post date, and engagement count |

## Procedure

1. Expand the keyword set before searching. Add synonyms, related terms, and competitor brand names to maximize coverage. Record the expanded set so the search pass is reproducible.

2. Run a per-platform search pass with spgr-search-web using `search_context: market`. Construct platform-specific queries with site operators: `site:reddit.com`, `site:news.ycombinator.com`, `site:stackoverflow.com`, `site:quora.com`, and the relevant niche-forum domains. Honor the `platforms` subset if one was given, otherwise search all five. Apply the date filter, defaulting to the last 24 months, since older posts may describe problems competitors have already solved.

3. Search across all selected platforms, not one. Different communities surface different pain. Reddit shows consumer-level frustration, Hacker News surfaces technical and founder perspectives, Stack Overflow reveals implementation-level friction, Quora surfaces questions from people who never found a solution. For B2B or vertical products, weight niche forums, which often yield higher-quality signals than general platforms.

4. Capture exact user language. Do not paraphrase a verbatim quote. The literal words reveal emotional register and cognitive friction that a polished paraphrase loses. Record each quote with its source URL, post date, and engagement score (upvotes, replies, or platform equivalent).

5. Apply the dedup rule before counting. Multiple posts from the same thread count as one data point for frequency. Replies within a thread are supporting evidence for the parent post's pain point, not separate data points.

6. Run the aggregation and theming pass. Group findings into pain-point clusters by semantic similarity. For each cluster write a description and assign a severity. Estimate frequency weighted by engagement, not raw post count, since a high-upvote, high-reply post indicates the pain resonates broadly rather than with one user.

7. Validate the evidence threshold per pain point. A pain point is validated only when two distinct source categories support it, for example two different platforms, or two unrelated threads on the same platform. Mark a pain point backed by a single source as proposed, not confirmed, in the confidence map. Do not promote a single-source signal to validated.

8. Build the platform breakdown and the user_vocabulary list. The vocabulary is the deduplicated set of the specific recurring phrases users reach for, drawn from the verbatim quotes.

9. Write the analysis as an envelope artifact with spgr-write-artifact, carrying the header, confidence map, decision log, and version. Run spgr-validate-artifact inline. Record any consequential theming or weighting choice with spgr-log-decision.

10. Escalate rather than fill gaps. If web access is unavailable, if a requested platform returns no usable results, or if the search yields too few sources to validate any pain point, stop and raise the gap to the Discovery Agent with spgr-escalate. Do not synthesize forum data from other sources, and do not present an unvalidated signal as confirmed.

## Notes

- Output type is a forum pain-point analysis envelope artifact. Its content schema is not registered yet, so envelope-only validation applies through spgr-validate-artifact until a content schema is registered. The envelope header, confidence map, decision log, and version are still checked.
- Engagement weighting sets frequency, not raw post count, per step 6.
- The two-source rule is a hard validation gate, per step 7. A single-source pain point stays proposed in the confidence map.
- Quotes are verbatim. Paraphrasing a quote is a defect, per step 4.
