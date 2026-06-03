---
name: spgr-search-web
description: Produce a web-search findings artifact with a prose summary, a deduplicated source list, verbatim key quotes, and an explicit gaps list, every factual claim carrying a source URL. Use when the Discovery, PM, Architect, Security, Compliance, or a developer agent needs current external intelligence (competitor pricing, third-party API documentation, market conditions, emerging technical patterns) that training data cannot ground, and downstream artifacts will cite the result.
---

# search-web

## Purpose

Ground a downstream artifact in current, citable external intelligence rather than stale training-data recall. This skill runs in Phase 1 discovery, so it writes no code. It returns a findings artifact where every claim is traceable to a source URL, so a receiving agent can verify each claim and so pain signals can later be validated against two distinct source categories. Surface what the search could not answer as a gaps list rather than filling it with assumption.

## Inputs

| Field | Description |
|-------|-------------|
| `query` | Natural-language or keyword search query |
| `search_context` | One of `competitive`, `documentation`, `market`, `technical`, `news`, `pricing`. Shapes result ranking and query expansion |
| `date_filter` | Optional ISO date range. Defaults to the last 12 months for `competitive` queries |
| `num_results` | Target number of sources to surface. Defaults to 10 |

## Outputs

| Artifact | Description |
|----------|-------------|
| `findings_summary` | Prose summary of key findings, two to four sentences per source |
| `sources` | Ordered list of source objects, each with `title`, `url`, `domain`, `date_retrieved`, `relevance_note` |
| `key_quotes` | Verbatim excerpts most relevant to the query, each tagged with its `source_url` |
| `gaps` | What the search could not answer, surfaced as escalation candidates |

## Procedure

1. Read the query and `search_context`. For a `competitive` context, expand the query to also cover pricing, reviews, and changelog pages before searching. Apply `date_filter`, defaulting to the last 12 months when the context is `competitive`.
2. Run the search with WebSearch. Fetch full-page content with WebFetch only when a result snippet is too thin to summarize or quote accurately. Use the largest persisted file read or write through spgr-read-file and spgr-write-file if intermediate content must be staged.
3. On a rate-limit or transient failure, back off exponentially and retry. Cache results by query hash for the session so a repeated query does not re-call the search API.
4. Deduplicate sources by domain. Hash the domain of each result URL and keep the single highest-ranked result per domain. Strip tracker parameters (`utm_*`, `ref=`, and similar) from every URL before recording it.
5. Build `findings_summary`, `sources`, and `key_quotes`. Flag any source older than 18 months as `[POTENTIALLY STALE]` in its `relevance_note`. For paywalled content, do not summarize the body. Record the URL, note the paywall, and add the item to `gaps` for human follow-up.
6. List every question the search could not answer in `gaps`. If `gaps` includes a claim that downstream work treats as a validated pain signal, note that it rests on a single source category and that a second distinct category is required before it counts as validated.
7. Write the artifact with spgr-write-artifact and run spgr-validate-artifact inline. If validation fails, fix the artifact and revalidate before returning. Record the search-engine choice and any fallback in the decision log with spgr-log-decision.
8. Escalate with spgr-escalate when the query is contradictory or too vague to search, when both search providers are unavailable after backoff, or when the result set is empty for a query the caller treated as answerable. State precisely what is missing rather than returning a thin or assumed result.

## Notes

- Output type is an envelope artifact (a research findings report). No content schema is registered for this type yet, so spgr-validate-artifact applies envelope-only validation, checking the header, confidence map, decision log, and version. Validation is still mandatory on every run.
- Every factual claim in `findings_summary` and every entry in `key_quotes` carries a source URL. A finding without a recordable source does not go in the summary, it goes in `gaps`.
- Mark a claim validated only when two distinct source categories support it. A single category yields a `proposed` confidence signal, not `confirmed`.
- Underlying engine is WebSearch with WebFetch for full-page reads. If one provider is rate-limited, fall back to the other before escalating.
- Version each revision with spgr-version-artifact. When the result feeds a vertical concern, tag the owning agent with spgr-tag-vertical-agent, and notify the human with spgr-notify-human only when escalation requires a decision.
