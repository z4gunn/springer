#!/usr/bin/env python3
"""Search public Bluesky posts and emit quotable items.

Deterministic, no model, stdlib only, no key. The public AppView endpoint
app.bsky.feed.searchPosts (https://docs.bsky.app/docs/api/app-bsky-feed-search-posts)
answers without authentication when a User-Agent is set, and returns the post
text, the creation date, and like, reply, repost, and quote counts, so
spgr-mine-social-media gets engagement-weighted posts with a URL instead of
search-engine snippets. Without authentication the endpoint serves one page
of at most 100 posts per query and answers every cursor page with 403
(probed 2026-10-04), so this script makes one request per query and the skill
widens coverage by varying the query, not by paging. The author handle is
used only to build the post URL and is written to the output because the URL
needs it. The skill's no-PII rule applies downstream: the artifact references
the URL and never the author.

Usage:
    bsky_search.py <query> [--sort top|latest] [--since YYYY-MM-DD]
                   [--limit N] [--fixture <saved-response.json>]

Prints one JSON object to stdout:
    {"source": "bluesky", "query": ..., "retrieved_at": ..., "items": [
        {"url", "date", "author", "title", "text", "engagement": {...}}],
     "errors": [...]}

Exit codes: 0 items retrieved with no errors, 1 items retrieved with some
errors (partial), 2 nothing retrieved. A --limit above the public cap is
recorded in "notes", not "errors". --fixture parses a saved response instead
of fetching, so tests never touch the network.
"""

import argparse
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SOURCE = "bluesky"
ENDPOINT = "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts"
USER_AGENT = "springer-mining/1.0 (+https://github.com/z4gunn/springer)"
PAGE_SIZE = 100
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


def post_url(uri, handle):
    """at://did/app.bsky.feed.post/rkey becomes https://bsky.app/profile/<handle>/post/<rkey>."""
    rkey = uri.rsplit("/", 1)[-1] if uri else ""
    return f"https://bsky.app/profile/{handle}/post/{rkey}"


def parse_posts(payload):
    """Map searchPosts results to the shared item shape."""
    items = []
    for post in payload.get("posts", []):
        author = post.get("author") or {}
        record = post.get("record") or {}
        handle = author.get("handle") or author.get("did") or ""
        items.append({
            "url": post_url(post.get("uri", ""), handle),
            "date": record.get("createdAt") or post.get("indexedAt"),
            "author": handle,
            "title": None,
            "text": record.get("text", ""),
            "engagement": {
                "likes": post.get("likeCount", 0),
                "replies": post.get("replyCount", 0),
                "reposts": post.get("repostCount", 0),
                "quotes": post.get("quoteCount", 0),
            },
        })
    return items


def build_url(query, sort, since, limit):
    params = {"q": query, "sort": sort, "limit": min(limit, PAGE_SIZE)}
    if since:
        params["since"] = f"{since}T00:00:00Z"
    return f"{ENDPOINT}?{urllib.parse.urlencode(params)}"


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("query")
    ap.add_argument("--sort", default="top", choices=["top", "latest"])
    ap.add_argument("--since", default=None, help="YYYY-MM-DD, inclusive lower bound")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--fixture", default=None, help="parse this saved response instead of fetching")
    args = ap.parse_args(argv[1:])

    errors = []
    notes = []
    items = []
    if args.limit > PAGE_SIZE:
        notes.append(f"public search serves one page of {PAGE_SIZE} per query without auth, "
                     f"limit {args.limit} capped. Vary the query to widen coverage.")
    if args.fixture:
        with open(args.fixture, encoding="utf-8") as fh:
            items = parse_posts(json.load(fh))[: args.limit]
    else:
        payload = fetch_json(build_url(args.query, args.sort, args.since, args.limit), errors)
        if payload is not None:
            items = parse_posts(payload)[: args.limit]

    result = {"source": SOURCE, "query": args.query, "sort": args.sort, "since": args.since,
              "page_cap": PAGE_SIZE, "retrieved_at": now_iso(), "items": items,
              "errors": errors, "notes": notes}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not items:
        return 2
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
