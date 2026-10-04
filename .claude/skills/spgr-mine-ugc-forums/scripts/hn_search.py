#!/usr/bin/env python3
"""Search Hacker News through the Algolia API and emit quotable items.

Deterministic, no model, stdlib only, no key. The Algolia HN index
(https://hn.algolia.com/api) is the one forum endpoint in the discovery set
that has stayed open for a decade, so spgr-mine-ugc-forums calls this instead
of a site-scoped web search. Each hit comes back with the author, the date,
the points or comment count, and a permalink, which is exactly the
quote-with-source contract the mining skills require.

Usage:
    hn_search.py <query> [--tags story|comment] [--since YYYY-MM-DD]
                 [--limit N] [--fixture <saved-response.json>]

Prints one JSON object to stdout:
    {"source": "hackernews", "query": ..., "retrieved_at": ..., "items": [
        {"url", "date", "author", "title", "text", "engagement": {...}}],
     "errors": [...]}

Exit codes: 0 items retrieved with no errors, 1 items retrieved with some
errors (partial), 2 nothing retrieved. --fixture parses a saved response
instead of fetching, so tests never touch the network.
"""

import argparse
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SOURCE = "hackernews"
ENDPOINT = "https://hn.algolia.com/api/v1/search"
USER_AGENT = "springer-mining/1.0 (+https://github.com/z4gunn/springer)"
PAGE_SIZE = 50
RETRIES = 4


def now_iso():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_json(url, errors):
    """GET a JSON document with exponential backoff on 429 and 5xx. Returns
    the parsed body or None, appending the reason to errors on failure."""
    delay = 1.0
    for attempt in range(RETRIES):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429 or exc.code >= 500:
                if attempt < RETRIES - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
            errors.append(f"HTTP {exc.code} for {url}")
            return None
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            if attempt < RETRIES - 1:
                time.sleep(delay)
                delay *= 2
                continue
            errors.append(f"{exc.__class__.__name__} for {url}: {exc}")
            return None
    return None


def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"<p>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def parse_hits(payload):
    """Map Algolia hits to the shared item shape."""
    items = []
    for hit in payload.get("hits", []):
        object_id = hit.get("objectID")
        is_comment = hit.get("comment_text") is not None
        engagement = {}
        if hit.get("points") is not None:
            engagement["points"] = hit["points"]
        if hit.get("num_comments") is not None:
            engagement["num_comments"] = hit["num_comments"]
        items.append({
            "url": f"https://news.ycombinator.com/item?id={object_id}",
            "date": hit.get("created_at"),
            "author": hit.get("author"),
            "title": hit.get("title") or hit.get("story_title"),
            "text": strip_html(hit.get("comment_text") or hit.get("story_text") or ""),
            "engagement": engagement,
            "kind": "comment" if is_comment else "story",
            "story_id": hit.get("story_id") or (None if is_comment else object_id),
            "external_url": hit.get("url"),
        })
    return items


def build_url(query, tags, since, page):
    params = {"query": query, "tags": tags, "hitsPerPage": PAGE_SIZE, "page": page}
    if since:
        epoch = int(dt.datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp())
        params["numericFilters"] = f"created_at_i>{epoch}"
    return f"{ENDPOINT}?{urllib.parse.urlencode(params)}"


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("query")
    ap.add_argument("--tags", default="comment", choices=["story", "comment"])
    ap.add_argument("--since", default=None, help="YYYY-MM-DD, inclusive lower bound")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--fixture", default=None, help="parse this saved response instead of fetching")
    args = ap.parse_args(argv[1:])

    errors = []
    items = []
    if args.fixture:
        with open(args.fixture, encoding="utf-8") as fh:
            items = parse_hits(json.load(fh))[: args.limit]
    else:
        page = 0
        while len(items) < args.limit:
            payload = fetch_json(build_url(args.query, args.tags, args.since, page), errors)
            if payload is None:
                break
            batch = parse_hits(payload)
            items.extend(batch)
            page += 1
            if not batch or page >= payload.get("nbPages", 0):
                break
        items = items[: args.limit]

    result = {"source": SOURCE, "query": args.query, "tags": args.tags, "since": args.since,
              "retrieved_at": now_iso(), "items": items, "errors": errors}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not items:
        return 2
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
