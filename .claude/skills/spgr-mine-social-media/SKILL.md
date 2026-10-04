---
name: spgr-mine-social-media
description: Produce a social-media signal artifact from public posts on Twitter/X, LinkedIn, Facebook Groups, and Bluesky, capturing engagement-weighted pain-point themes, emotional tone, and switching signals. Use when the Discovery agent needs real-time sentiment on a problem space, or when the PM agent needs tone evidence for positioning.
---

# mine-social-media

## Purpose

Social media is the most temporally current and emotionally expressive discovery source. A user who posts about a problem is broadcasting it because the frustration is high enough to share publicly, and high-engagement posts signal that the frustration is widely held. This skill captures not just what people want but how urgently and in what emotional register they want it, which is the input positioning and messaging decisions need. It runs as a Discovery consultant output during Phase 1, where no code is written. Every factual claim carries a source. A pain signal is treated as validated only after it appears in a second distinct source category, so this skill's output is one input to that test, not the whole of it.

## Inputs

| Field | Description |
|-------|-------------|
| `problem_domain` | The core problem space to monitor |
| `product_names` | Known product or brand names to include in searches, competitors or incumbents |
| `hashtag_keyword_set` | Hashtags and keywords to search across platforms |
| `platforms` | Optional subset. Defaults to all four: `twitter`, `linkedin`, `facebook_groups`, `bluesky` |
| `date_filter` | Date range. Defaults to the last 6 months, a shorter window than forums due to the faster decay rate of social content |
| `engagement_threshold` | Minimum likes plus replies for a post to be included. Defaults to 5, which filters noise |

## Outputs

| Artifact | Description |
|----------|-------------|
| `pain_points` | Pain-point themes with engagement-weighted mention count, aggregate tone, the platforms each appears on, and representative posts |
| `representative_posts` | High-engagement posts per theme with engagement metrics and URLs |
| `tone_distribution` | Count of posts in each emotional register: `frustrated`, `resigned`, `actively_switching`, `curious`, `satisfied` |
| `platform_breakdown` | Mention count per platform, showing which platforms are most active for this problem space |
| `switching_signals` | Posts where a user asks for an alternative or announces a switch, with direction and date |
| `sources` | Post URLs with platform, date, and engagement metrics |

## Procedure

1. Confirm web access and the input fields. If `problem_domain` or `hashtag_keyword_set` is missing, or web access is unavailable, stop and raise a structured escalation with spgr-escalate rather than searching on assumptions.

2. Select platforms. Default to all four. Match platform to market when the domain is clear: LinkedIn for B2B problems, Twitter/X and Bluesky for technical and startup communities, Facebook Groups for consumer and SMB markets. Record platform selection rationale with spgr-log-decision.

3. Run a per-platform keyword search pass. For Bluesky run the bundled script, which queries the public AppView search with no key and returns each post with its date, text, like, reply, repost, and quote counts, and URL:

   ```bash
   python3 .claude/skills/spgr-mine-social-media/scripts/bsky_search.py "<query>" --sort top --since <YYYY-MM-DD> --limit 100
   ```

   The public endpoint serves one page of at most 100 posts per query and refuses every cursor, so widen coverage by running it once per keyword, hashtag, and product name rather than by paging. For Twitter/X there is no free read path: the official API has no free tier and cookie-based clients risk the account. Mine X only through the Apify CLI when `APIFY_TOKEN` is set, with an input file of search terms and the date window:

   ```bash
   apify actors call apidojo/tweet-scraper --input-file x-input.json --json
   apify datasets get-items <dataset-id> --format json
   ```

   When the token is absent, omit X, record `x omitted, no free path` with spgr-log-decision, and say so in `platform_breakdown`. For LinkedIn and Facebook Groups use spgr-search-web with a platform-specific site filter (`site:linkedin.com`, `site:facebook.com/groups`), querying the `hashtag_keyword_set` and each entry in `product_names`. Apply `date_filter`.

4. Filter by engagement. Drop any post below `engagement_threshold` (likes plus replies). Capture each kept post as a source with URL, platform, date, likes, replies, and a short excerpt.

5. Deduplicate. A retweet or share of the same post counts as one data point, not many. Fold the engagement of every share into the engagement score of the original post, so a widely reshared post scores higher without inflating the mention count.

6. Strip personally identifiable information. Reference the post URL only. Do not record the author name, handle, or profile in any output field. The Bluesky script emits the handle because the post URL is built from it, so drop the `author` field when carrying an item into the artifact. Verify this on a sample before proceeding.

7. Run the clustering and tone pass. Cluster the kept posts into pain-point themes by semantic similarity. Classify the tone of each post into one of `frustrated`, `resigned`, `actively_switching`, `curious`, `satisfied` using a structured prompt. Aggregate to a theme-level tone by majority class.

8. Weight frequency by engagement, not raw mention count. A theme carried by a few high-engagement posts resonates more than a theme of many low-engagement posts. Record the engagement-weighted mention count per theme alongside which platforms it appears on.

9. Extract switching signals. Flag posts that ask "what is the best alternative to X" or announce "I switched from X to Y because". Record each with the URL, excerpt, a `direction` (the from and to where stated), and the date. Treat switching signals as the highest-value social signal because they name who is leaving, why, and what they wanted instead.

10. Build the platform breakdown and tone distribution. Count mentions per platform and posts per tone class across all kept posts.

11. Write the result as an envelope artifact with spgr-write-artifact, carrying the header, confidence map, decision log, and version. Run spgr-validate-artifact inline. Register the output to the Discovery agent, and to the PM agent when switching or tone signals bear on positioning, through spgr-tag-vertical-agent as a consultation.

## Notes

- Output type is a social-media signal envelope artifact. Its content schema is not registered yet, so spgr-validate-artifact applies envelope-only validation (header, confidence map, decision log, version) until a content schema is registered.
- Mark each pain-point theme as a proposed signal in the confidence map, not confirmed. Confirmation requires a second distinct source category, which is established outside this skill.
- Tone is load-bearing, not decoration. A space full of `resigned` users has accepted the pain as normal. A space full of `actively_switching` users is already in market for an alternative.
- No personally identifiable information from any post may appear in the output. Reference the URL, never the author.
- The Bluesky script is deterministic and runs with no model. Dispatch it at the deterministic tier. The Apify CLI is an optional paid tool in the same class as excalidraw: the skill runs without it, and X is then omitted with a decision-log line rather than approximated.
- Search payload schema per theme: `{theme, mention_count, tone, platforms: [string], posts: [{url, platform, date, likes, replies, excerpt}]}`, with top-level `switching_signals`, `platform_breakdown`, and `tone_distribution` per the spec output contract.
