#!/usr/bin/env node
// Fetch Google Play reviews for one app and emit quotable items.
//
// Deterministic, no model, no key. Google Play has no public review endpoint,
// so this script drives the google-play-scraper package (MIT,
// https://github.com/facundoolano/google-play-scraper), which pages the store's
// own review feed and returns the date, the star score, the thumbs-up count,
// the app version, and a per-review URL. The package is an optional
// dependency: when it is not installed the script prints an install hint and
// exits 2, and spgr-mine-app-store-reviews falls back to web search. Because
// the package returns an empty list for an unknown or mistyped app id rather
// than an error, --verify searches the store for the id first and exits 2
// with a clear message when it is not found.
//
// Usage:
//   node google_play_reviews.mjs <app-id> [--country us] [--lang en]
//        [--sort newest|rating|helpfulness] [--limit N] [--verify]
//        [--fixture <saved-reviews.json>]
//
// Prints one JSON object to stdout:
//   {"source": "google-play", "query": <app-id>, "retrieved_at": ...,
//    "items": [{"url", "date", "author", "title", "text", "engagement": {...}}],
//    "errors": [...]}
//
// Exit codes: 0 items retrieved with no errors, 1 items retrieved with some
// errors (partial), 2 nothing retrieved, package missing, or app id not found.
// --fixture parses a saved array of package review objects (or a {data: [...]}
// page) instead of fetching, so tests never touch the network or the package.

import { readFileSync } from "node:fs";

const SOURCE = "google-play";
const PAGE = 150;

function parseArgs(argv) {
  const args = { country: "us", lang: "en", sort: "newest", limit: 200, verify: false, fixture: null };
  const positional = [];
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--country") args.country = argv[++i];
    else if (a === "--lang") args.lang = argv[++i];
    else if (a === "--sort") args.sort = argv[++i];
    else if (a === "--limit") args.limit = parseInt(argv[++i], 10);
    else if (a === "--verify") args.verify = true;
    else if (a === "--fixture") args.fixture = argv[++i];
    else positional.push(a);
  }
  args.appId = positional[0];
  return args;
}

export function parseReviews(rows) {
  return rows.map((r) => ({
    url: r.url || null,
    review_id: r.id || null,
    date: r.date instanceof Date ? r.date.toISOString() : r.date || null,
    author: r.userName || null,
    title: r.title || null,
    text: r.text || "",
    engagement: {
      rating: r.score ?? null,
      thumbs_up: r.thumbsUp ?? null,
      version: r.version || null,
      reply: r.replyText ? { date: r.replyDate || null, text: r.replyText } : null,
    },
  }));
}

function emit(result) {
  process.stdout.write(JSON.stringify(result, null, 2) + "\n");
  if (result.items.length === 0) return 2;
  return result.errors.length ? 1 : 0;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const result = { source: SOURCE, query: args.appId, country: args.country, sort: args.sort,
    retrieved_at: new Date().toISOString(), items: [], errors: [] };

  if (!args.appId) {
    result.errors.push("app id is required, the package name in the Play URL (for example com.example.app)");
    return emit(result);
  }

  if (args.fixture) {
    const raw = JSON.parse(readFileSync(args.fixture, "utf8"));
    const rows = Array.isArray(raw) ? raw : raw.data || [];
    result.items = parseReviews(rows).slice(0, args.limit);
    return emit(result);
  }

  let gplay;
  try {
    gplay = (await import("google-play-scraper")).default;
  } catch (err) {
    result.errors.push("google-play-scraper is not installed. Run `npm install google-play-scraper` in the project, or let the skill fall back to web search.");
    return emit(result);
  }

  const sortMap = { newest: gplay.sort.NEWEST, rating: gplay.sort.RATING, helpfulness: gplay.sort.HELPFULNESS };
  try {
    if (args.verify) {
      const hits = await gplay.search({ term: args.appId, num: 5, country: args.country, lang: args.lang });
      if (!hits.some((h) => h.appId === args.appId)) {
        result.errors.push(`app id ${args.appId} was not found in a store search. Verify the package name before mining.`);
        return emit(result);
      }
    }
    let token = null;
    while (result.items.length < args.limit) {
      const page = await gplay.reviews({ appId: args.appId, country: args.country, lang: args.lang,
        sort: sortMap[args.sort] || gplay.sort.NEWEST, num: PAGE, paginate: true, nextPaginationToken: token });
      result.items.push(...parseReviews(page.data || []));
      token = page.nextPaginationToken;
      if (!token || !(page.data || []).length) break;
    }
    result.items = result.items.slice(0, args.limit);
  } catch (err) {
    result.errors.push(`${err.name || "Error"}: ${err.message}`);
  }
  return emit(result);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().then((code) => process.exit(code));
}
