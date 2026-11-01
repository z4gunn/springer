# Reddit access for discovery mining

Reddit is the richest consumer-frustration source in the forum set and the one closing its free read paths. This file records the closure schedule, the paths in order, and what to record in the decision log, so a thin Reddit yield is read as a platform-policy outcome and the escalation names the stage in effect.

## Closure schedule

Verified by probe on 2026-10-04 and from Reddit's r/modnews announcements of 2026-05-28 and 2026-09-30.

| Path | State | Date |
|------|-------|------|
| Unauthenticated `.json` endpoints | closed, every request returns 403 | late May 2026 |
| RSS feeds (`.rss` on search and listing URLs) | open, no vote or comment counts | announced to end 2026-11-13 |
| Public Data API (OAuth script app, 100 requests a minute) | open to registered apps only | new registrations close 2026-10-31, access ends March 2027 |
| Jina Reader proxy (`r.jina.ai`) | blocked by Reddit | now |

Reddit's stated replacement is Devvit, which runs code on Reddit's servers and does not serve a research reader.

## Paths in order

1. last30days, optional and keyless. Look for the engine at `~/.claude/skills/last30days/scripts/last30days.py` or under the installed plugin directory. Run it per expanded keyword:

   ```bash
   python3 ~/.claude/skills/last30days/scripts/last30days.py "<query>" --emit=json --json-profile=raw
   ```

   Read `source_status.reddit`. When it is `ok`, take `items_by_source.reddit[]` as posts and `items_by_source.reddit[].metadata.top_comments[]` as attributed quotes, each carrying `author`, `date`, `excerpt`, `score`, and a comment permalink in `url`. Excerpts are truncated near 200 characters, so when a quote must be carried whole, fetch the comment permalink and quote from the page. The engine scrapes Reddit's web frontend, which is the surface Reddit is closing, so it degrades without notice. Record `reddit via last30days` in the decision log with the engine version.
2. Apify CLI, optional and paid, switched on by `APIFY_TOKEN`. This is the path that outlives March 2027. Write the input file with the subreddits or search terms and the date window, then:

   ```bash
   apify actors call trudax/reddit-scraper-lite --input-file reddit-input.json --json
   apify datasets get-items <dataset-id> --format json
   ```

   Each item carries the post or comment body, author, date, score, and permalink. Record `reddit via apify <actor>` and the item count in the decision log. A missing Actor is an escalation, not a substitution.
3. WebSearch with `site:reddit.com` through spgr-search-web. This is the floor. It yields titles and snippets with URLs and dates but no vote or comment counts, so engagement weighting in step 6 of the skill falls back to reply count parsed from the snippet or is marked unknown. Record `reddit via websearch, degraded` in the decision log.

Until 2026-11-13 the RSS feed (`https://www.reddit.com/search.rss?q=<query>&sort=top&t=year`, custom User-Agent required) returns titles, authors, dates, and bodies without engagement counts and sits between paths 2 and 3. After that date skip it.

## What the artifact records

- For every Reddit source, the path that produced it, so a reviewer can weigh a websearch snippet against a scored comment.
- A single-source Reddit pain point stays proposed. The two-source rule in the skill is unchanged.
- When no path returns usable results, the escalation in step 10 states the closure stage from the table above and the paths tried.
