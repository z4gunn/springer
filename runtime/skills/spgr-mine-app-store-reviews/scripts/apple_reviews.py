#!/usr/bin/env python3
"""Fetch App Store customer reviews for one app and emit quotable items.

Deterministic, no model, stdlib only, no key. Two public endpoints are tried
in order, because each has a limit the other does not. The customer-reviews
RSS feed (https://itunes.apple.com/{cc}/rss/customerreviews/id={id}/sortBy={sort}/page={n}/json)
returns 50 reviews per page with the version string and the helpful-vote
counts, and stops at page 10, so 500 reviews per country per sort is its cap.
When the target is above that cap, or the feed comes back empty (it has gone
dark for stretches), the catalog endpoint
(https://apps.apple.com/api/apps/v1/catalog/{cc}/apps/{id}/reviews) is paged
through its cursor. It needs a browser User-Agent and an Origin header, and
it omits the version and the vote counts, so items from it carry fewer
engagement fields and say which endpoint they came from.

Usage:
    apple_reviews.py <app-id> [--country us] [--sort mostRecent|mostHelpful]
                     [--limit N] [--fixture <saved-response.json>]

Prints one JSON object to stdout:
    {"source": "apple-app-store", "query": <app-id>, "retrieved_at": ...,
     "items": [{"url", "date", "author", "title", "text", "engagement": {...}}],
     "errors": [...]}

Exit codes: 0 items retrieved with no errors, 1 items retrieved with some
errors (partial), 2 nothing retrieved. --fixture parses a saved response of
either endpoint instead of fetching, so tests never touch the network.
"""

import argparse
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.request

SOURCE = "apple-app-store"
RSS = "https://itunes.apple.com/{cc}/rss/customerreviews/id={app_id}/sortBy={sort}/page={page}/json"
RSS_PAGES = 10
CATALOG = "https://apps.apple.com/api/apps/v1/catalog/{cc}/apps/{app_id}/reviews?platform=iphone&offset={offset}&limit={limit}"
CATALOG_HOST = "https://apps.apple.com"
CATALOG_PAGE = 20
RSS_AGENT = "springer-mining/1.0 (+https://github.com/z4gunn/springer)"
BROWSER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                 "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
RETRIES = 4


def now_iso():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_json(url, headers, errors):
    """GET a JSON document with exponential backoff on 429 and 5xx. Returns
    the parsed body or None, appending the reason to errors on failure."""
    delay = 1.0
    for attempt in range(RETRIES):
        req = urllib.request.Request(url, headers=headers)
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


def label(obj, key):
    value = (obj or {}).get(key)
    if isinstance(value, dict):
        return value.get("label")
    return value


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_rss(payload, app_id, country):
    """Map RSS feed entries to the shared item shape."""
    feed = payload.get("feed") or {}
    entries = feed.get("entry") or []
    if isinstance(entries, dict):
        entries = [entries]
    items = []
    for entry in entries:
        review_id = label(entry, "id")
        link = ((entry.get("link") or {}).get("attributes") or {}).get("href")
        items.append({
            "url": link or f"https://apps.apple.com/{country}/app/id{app_id}?see-all=reviews",
            "review_id": review_id,
            "date": label(entry, "updated"),
            "author": label(entry.get("author"), "name"),
            "title": label(entry, "title"),
            "text": label(entry, "content") or "",
            "engagement": {
                "rating": to_int(label(entry, "im:rating")),
                "version": label(entry, "im:version"),
                "vote_sum": to_int(label(entry, "im:voteSum")),
                "vote_count": to_int(label(entry, "im:voteCount")),
            },
            "endpoint": "rss",
        })
    return items


def parse_catalog(payload, app_id, country):
    """Map catalog user-reviews to the shared item shape."""
    items = []
    for row in payload.get("data") or []:
        attrs = row.get("attributes") or {}
        items.append({
            "url": f"https://apps.apple.com/{country}/app/id{app_id}?see-all=reviews",
            "review_id": row.get("id"),
            "date": attrs.get("date"),
            "author": attrs.get("userName"),
            "title": attrs.get("title"),
            "text": attrs.get("review") or "",
            "engagement": {"rating": attrs.get("rating"), "is_edited": attrs.get("isEdited")},
            "endpoint": "catalog",
        })
    return items


def parse_any(payload, app_id, country):
    if "feed" in payload:
        return parse_rss(payload, app_id, country)
    return parse_catalog(payload, app_id, country)


def fetch_rss(app_id, country, sort, limit, errors):
    items = []
    for page in range(1, RSS_PAGES + 1):
        url = RSS.format(cc=country, app_id=app_id, sort=sort, page=page)
        payload = fetch_json(url, {"User-Agent": RSS_AGENT, "Accept": "application/json"}, errors)
        if payload is None:
            break
        batch = parse_rss(payload, app_id, country)
        if not batch:
            break
        items.extend(batch)
        if len(items) >= limit:
            break
    return items


def fetch_catalog(app_id, country, limit, seen, errors):
    items = []
    offset = 0
    headers = {"User-Agent": BROWSER_AGENT, "Accept": "application/json", "Origin": CATALOG_HOST,
               "Referer": f"{CATALOG_HOST}/"}
    while len(items) < limit:
        url = CATALOG.format(cc=country, app_id=app_id, offset=offset, limit=CATALOG_PAGE)
        payload = fetch_json(url, headers, errors)
        if payload is None:
            break
        batch = [it for it in parse_catalog(payload, app_id, country) if it["review_id"] not in seen]
        for it in batch:
            seen.add(it["review_id"])
        items.extend(batch)
        nxt = payload.get("next")
        if not payload.get("data") or not nxt:
            break
        offset += CATALOG_PAGE
    return items


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("app_id", help="numeric App Store id, the digits after 'id' in the listing URL")
    ap.add_argument("--country", default="us")
    ap.add_argument("--sort", default="mostRecent", choices=["mostRecent", "mostHelpful"])
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--fixture", default=None, help="parse this saved response instead of fetching")
    args = ap.parse_args(argv[1:])

    errors = []
    items = []
    if args.fixture:
        with open(args.fixture, encoding="utf-8") as fh:
            items = parse_any(json.load(fh), args.app_id, args.country)[: args.limit]
    else:
        items = fetch_rss(args.app_id, args.country, args.sort, args.limit, errors)
        if len(items) < args.limit:
            seen = {it["review_id"] for it in items}
            items.extend(fetch_catalog(args.app_id, args.country, args.limit - len(items), seen, errors))
        items = items[: args.limit]

    result = {"source": SOURCE, "query": args.app_id, "country": args.country, "sort": args.sort,
              "rss_cap": RSS_PAGES * 50, "retrieved_at": now_iso(), "items": items, "errors": errors}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not items:
        return 2
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
